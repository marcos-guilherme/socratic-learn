from __future__ import annotations

import ipaddress
import os
import socket
import ssl
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from unittest import mock

from socratic_learn.errors import SourceError
from socratic_learn.sources.http import (
    MAX_RAW_BYTES,
    MAX_REDIRECTS,
    SOCKET_TIMEOUT_SECONDS,
    canonicalize_url,
    fetch_url,
)
from socratic_learn.sources.model import FetchedBytes

TEST_HOST = "93.184.216.34"


def _public_resolver(host: str, _port: int) -> list[str]:
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        return [TEST_HOST]


def _resolver_for(*addresses: str) -> Callable[[str, int], list[str]]:
    def resolve(_host: str, _port: int) -> list[str]:
        return list(addresses)

    return resolve


class _HeaderRecordingMixin:
    received_headers: dict[str, str] | None = None


class CanonicalizeUrlTests(unittest.TestCase):
    def test_http_default_port_and_query_redaction(self) -> None:
        retrieval, display = canonicalize_url("HTTP://Example.COM/article?token=secret#frag")
        self.assertEqual("http://example.com/article?token=secret", retrieval)
        self.assertEqual("http://example.com/article", display)

    def test_https_omits_default_port_keeps_non_default(self) -> None:
        retrieval, display = canonicalize_url("https://example.com:8443/x")
        self.assertEqual("https://example.com:8443/x", retrieval)
        self.assertEqual("https://example.com:8443/x", display)

    def test_idna_host_and_percent_path_normalization(self) -> None:
        retrieval, display = canonicalize_url("http://bücher.example/%61rticle")
        self.assertIn("xn--", retrieval)
        self.assertEqual(retrieval, display)

    def test_rejects_user_information(self) -> None:
        with self.assertRaises(SourceError):
            canonicalize_url("http://user:pass@example.com/")

    def test_rejects_unsupported_scheme_and_malformed_port(self) -> None:
        with self.assertRaises(SourceError):
            canonicalize_url("ftp://example.com/")
        with self.assertRaises(SourceError):
            canonicalize_url("http://example.com:99999/")

    def test_rejects_control_characters(self) -> None:
        with self.assertRaises(SourceError):
            canonicalize_url("http://example.com/a\x00b")


class CanonicalizeIpv6Tests(unittest.TestCase):
    def test_compresses_ipv6_literal_with_bracketed_netloc(self) -> None:
        retrieval, display = canonicalize_url("http://[2001:DB8:0:0:0:0:0:1]/doc?k=1")
        self.assertEqual("http://[2001:db8::1]/doc?k=1", retrieval)
        self.assertEqual("http://[2001:db8::1]/doc", display)

    def test_preserves_non_default_ipv6_port(self) -> None:
        retrieval, display = canonicalize_url("https://[2001:db8::1]:8443/x")
        self.assertEqual("https://[2001:db8::1]:8443/x", retrieval)
        self.assertEqual("https://[2001:db8::1]:8443/x", display)

    def test_rejects_scoped_and_malformed_ipv6_literals(self) -> None:
        with self.assertRaises(SourceError):
            canonicalize_url("http://[fe80::1%25eth0]/")
        with self.assertRaises(SourceError):
            canonicalize_url("http://[not-an-ip]/")
        with self.assertRaises(SourceError):
            canonicalize_url("http://[::gggg]/")

    def test_ipv4_literal_host_without_brackets(self) -> None:
        retrieval, display = canonicalize_url(f"http://{TEST_HOST}/x")
        self.assertEqual(f"http://{TEST_HOST}/x", retrieval)
        self.assertEqual(retrieval, display)


class _TestHandler(BaseHTTPRequestHandler):
    payload: bytes = b"<html><body>Evidence paragraph. " + b"word " * 50 + b"</body></html>"
    status: int = 200
    headers: dict[str, str] = {"Content-Type": "text/html; charset=utf-8"}
    next_location: str | None = None

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        if isinstance(self.server, _RecordingServer):
            _RecordingServer.last_headers = {key: value for key, value in self.headers.items()}
        body = type(self).payload
        headers = dict(type(self).headers)
        status = type(self).status
        location = type(self).next_location
        if location is not None:
            headers["Location"] = location
            status = 302
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if status != 302 or body:
            self.wfile.write(body)


class _RecordingServer(ThreadingHTTPServer):
    last_headers: dict[str, str] | None = None


class _HttpTestCase(unittest.TestCase):
    server: ThreadingHTTPServer
    port: int
    thread: threading.Thread

    def start_server(self, handler: type[BaseHTTPRequestHandler] = _TestHandler) -> None:
        self.server = _RecordingServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        if hasattr(self, "server"):
            self.server.shutdown()
            self.server.server_close()

    def retrieval_url(self, path: str = "/article", query: str = "") -> str:
        suffix = f"?{query}" if query else ""
        return f"http://{TEST_HOST}:{self.port}{path}{suffix}"

    def fetch(
        self,
        url: str,
        *,
        allow_private_network: bool = False,
        resolver: Callable[[str, int], list[str]] | None = None,
        connect_host: str = "127.0.0.1",
    ) -> FetchedBytes:
        def connection_factory(host: str, port: int, scheme: str, timeout: float):
            import http.client

            if scheme == "https":
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                connection = http.client.HTTPSConnection(
                    connect_host, port, timeout=timeout, context=context
                )
            else:
                connection = http.client.HTTPConnection(connect_host, port, timeout=timeout)

            original_connect = connection.connect

            def connect_with_public_peer() -> None:
                original_connect()
                inner = connection.sock

                class _PeerSpoofingSocket:
                    def __init__(self, wrapped: object) -> None:
                        self._wrapped = wrapped

                    def getpeername(self) -> tuple[str, int]:
                        return (TEST_HOST, port)

                    def __getattr__(self, name: str) -> object:
                        return getattr(self._wrapped, name)

                connection.sock = _PeerSpoofingSocket(inner)

            connection.connect = connect_with_public_peer  # type: ignore[method-assign]
            return connection

        resolved = resolver or _public_resolver
        return fetch_url(
            url,
            allow_private_network=allow_private_network,
            user_agent="Socratic-Learn/test",
            resolver=resolved,
            connection_factory=connection_factory,
        )


class FetchUrlHappyPathTests(_HttpTestCase):
    def test_fetches_html_and_redacts_query_in_response(self) -> None:
        self.start_server()
        fetched = self.fetch(self.retrieval_url(query="token=secret"))
        self.assertIsInstance(fetched, FetchedBytes)
        self.assertIn(b"Evidence", fetched.raw)
        self.assertEqual("text/html", fetched.media_type)
        self.assertIn("token=secret", fetched.canonical_url)
        self.assertEqual(f"http://{TEST_HOST}:{self.port}/article", fetched.display_origin)


class AddressPolicyTests(unittest.TestCase):
    def test_blocks_private_ipv4(self) -> None:
        blocked = ("10.0.0.1", "192.168.0.1", "127.0.0.1", "169.254.0.1", "224.0.0.1", "0.0.0.0")
        for address in blocked:
            with self.subTest(address=address):
                with self.assertRaises(SourceError) as context:
                    fetch_url(
                        f"http://{TEST_HOST}/",
                        allow_private_network=False,
                        user_agent="Socratic-Learn/test",
                        resolver=_resolver_for(address),
                        connection_factory=lambda *_args: unittest.mock.Mock(),
                    )
                self.assertIn(TEST_HOST, str(context.exception))
                self.assertNotIn("?", str(context.exception))

    def test_blocks_private_ipv6_and_any_blocked_answer_rejects(self) -> None:
        blocked = ("::1", "fc00::1", "fe80::1", "::", "ff01::1")
        for address in blocked:
            with self.subTest(address=address):
                with self.assertRaises(SourceError):
                    fetch_url(
                        f"http://{TEST_HOST}/",
                        allow_private_network=False,
                        user_agent="Socratic-Learn/test",
                        resolver=_resolver_for(address),
                        connection_factory=lambda *_args: unittest.mock.Mock(),
                    )
        with self.assertRaises(SourceError):
            fetch_url(
                f"http://{TEST_HOST}/",
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for(TEST_HOST, "10.0.0.1"),
                connection_factory=lambda *_args: unittest.mock.Mock(),
            )

    def test_private_opt_in_allows_blocked_resolver(self) -> None:
        class _ImmediateHandler(_TestHandler):
            payload = b"%PDF-1.4 minimal"

        server = ThreadingHTTPServer(("127.0.0.1", 0), _ImmediateHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def connection_factory(host: str, port_: int, scheme: str, timeout: float):
                import http.client

                return http.client.HTTPConnection("127.0.0.1", port_, timeout=timeout)

            fetched = fetch_url(
                f"http://{TEST_HOST}:{port}/",
                allow_private_network=True,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for("127.0.0.1"),
                connection_factory=connection_factory,
            )
            self.assertIsInstance(fetched, FetchedBytes)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class PolicyOrderingTests(unittest.TestCase):
    def test_pre_resolution_blocks_before_connection_factory(self) -> None:
        factory = mock.Mock()
        with self.assertRaises(SourceError):
            fetch_url(
                f"http://{TEST_HOST}/",
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for("10.0.0.1"),
                connection_factory=factory,
            )
        factory.assert_not_called()

    def test_fetch_ipv6_literal_display_applies_address_policy(self) -> None:
        with self.assertRaises(SourceError) as context:
            fetch_url(
                "http://[2001:db8::1]/article",
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for("10.0.0.1"),
                connection_factory=lambda *_args: mock.Mock(),
            )
        message = str(context.exception)
        self.assertIn("http://[2001:db8::1]/article", message)
        self.assertNotIn("10.0.0.1", message)


class PeerRecheckTests(_HttpTestCase):
    def test_rejects_connected_peer_outside_policy(self) -> None:
        self.start_server()

        class _PeeringConnection:
            sock: object

            def __init__(self, *, port: int) -> None:
                self.sock = mock.Mock()
                self.sock.getpeername.return_value = ("10.0.0.1", port)

            def connect(self) -> None:
                return

            def close(self) -> None:
                return

            def request(self, *_args, **_kwargs) -> None:
                raise AssertionError("request must not be sent when peer check fails")

            def getresponse(self):
                raise AssertionError("unreachable")

        with self.assertRaises(SourceError) as context:
            fetch_url(
                self.retrieval_url(),
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_public_resolver,
                connection_factory=lambda _h, port, _s, _t: _PeeringConnection(port=port),
            )
        self.assertIn("blocked network destination", str(context.exception))
        self.assertIn(f"http://{TEST_HOST}:{self.port}/article", str(context.exception))

    def test_peer_check_runs_after_connect_and_before_request(self) -> None:
        events: list[str] = []

        class _OrderedConnection:
            def __init__(self, *, port: int) -> None:
                self._port = port

            def connect(self) -> None:
                events.append("connect")

            @property
            def sock(self) -> mock.Mock:
                peer = mock.Mock()
                peer.getpeername.return_value = ("10.0.0.1", self._port)
                return peer

            def close(self) -> None:
                return

            def request(self, *_args: object, **_kwargs: object) -> None:
                events.append("request")

            def getresponse(self) -> None:
                raise AssertionError("unreachable")

        with self.assertRaises(SourceError):
            fetch_url(
                f"http://{TEST_HOST}/",
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for(TEST_HOST),
                connection_factory=lambda _h, port, _s, _t: _OrderedConnection(port=port),
            )
        self.assertEqual(["connect"], events)


class RedirectTests(_HttpTestCase):
    def test_follows_five_redirects_rejects_sixth(self) -> None:
        self.start_server()

        class _RedirectHandler(_TestHandler):
            redirect_count = 0

            def do_GET(self) -> None:
                _RedirectHandler.redirect_count += 1
                if _RedirectHandler.redirect_count <= MAX_REDIRECTS:
                    self.send_response(302)
                    self.send_header("Location", f"/hop{_RedirectHandler.redirect_count}")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(self.payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        fetched = self.fetch(self.retrieval_url("/start"))
        self.assertIn(b"Evidence", fetched.raw)

        _RedirectHandler.redirect_count = 0

        class _TooManyHandler(_TestHandler):
            redirect_count = 0

            def do_GET(self) -> None:
                _TooManyHandler.redirect_count += 1
                self.send_response(302)
                self.send_header("Location", f"/hop{_TooManyHandler.redirect_count}")
                self.end_headers()

        self.tearDown()
        self.start_server(_TooManyHandler)
        with self.assertRaises(SourceError):
            self.fetch(self.retrieval_url("/start"))

    def test_rejects_public_to_private_redirect(self) -> None:
        self.start_server()

        class _PrivateRedirectHandler(_TestHandler):
            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", "http://10.0.0.1/private")
                self.end_headers()

        self.tearDown()
        self.start_server(_PrivateRedirectHandler)
        with self.assertRaises(SourceError) as context:
            self.fetch(self.retrieval_url())
        self.assertNotIn("10.0.0.1", str(context.exception))


class TransportPolicyTests(_HttpTestCase):
    def test_disables_proxy_env_and_sends_safe_headers(self) -> None:
        self.start_server()
        _RecordingServer.last_headers = {}
        with mock.patch.dict(os.environ, {"HTTP_PROXY": "http://evil.example:9", "HTTPS_PROXY": "http://evil.example:9"}):
            self.fetch(self.retrieval_url())
        headers = _RecordingServer.last_headers or {}
        lowered = {key.lower(): value for key, value in headers.items()}
        self.assertEqual("identity", lowered.get("accept-encoding"))
        self.assertNotIn("cookie", lowered)
        self.assertNotIn("authorization", lowered)
        self.assertEqual("Socratic-Learn/test", lowered.get("user-agent"))

    def test_rejects_non_identity_content_encoding(self) -> None:
        class _GzipHandler(_TestHandler):
            headers = {
                "Content-Type": "text/html",
                "Content-Encoding": "gzip",
            }

        self.tearDown()
        self.start_server(_GzipHandler)
        with self.assertRaises(SourceError):
            self.fetch(self.retrieval_url())

    def test_enforces_response_size_boundary(self) -> None:
        class _LargeHandler(_TestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"x" * MAX_RAW_BYTES)

        self.tearDown()
        self.start_server(_LargeHandler)
        fetched = self.fetch(self.retrieval_url())
        self.assertEqual(MAX_RAW_BYTES, len(fetched.raw))

        class _TooLargeHandler(_TestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"x" * (MAX_RAW_BYTES + 1))

        self.tearDown()
        self.start_server(_TooLargeHandler)
        with self.assertRaises(SourceError):
            self.fetch(self.retrieval_url())


class MediaTypeTests(_HttpTestCase):
    def test_accepts_declared_html_xhtml_and_pdf(self) -> None:
        for content_type, expected in (
            ("text/html", "text/html"),
            ("application/xhtml+xml", "text/html"),
            ("application/pdf", "application/pdf"),
        ):
            with self.subTest(content_type=content_type):

                class _TypedHandler(_TestHandler):
                    payload = b"%PDF-1.4\n" if content_type.endswith("pdf") else _TestHandler.payload
                    headers = {"Content-Type": content_type}

                self.tearDown()
                self.start_server(_TypedHandler)
                fetched = self.fetch(self.retrieval_url())
                self.assertEqual(expected, fetched.media_type)

    def test_sniffs_missing_or_octet_stream_signatures(self) -> None:
        cases = (
            (b"%PDF-1.4\n", "application/pdf"),
            (b"<!DOCTYPE html><html><body>" + b"x" * 120 + b"</body></html>", "text/html"),
            (b"<HTML><body>" + b"x" * 120 + b"</body></html>", "text/html"),
        )
        for body, expected in cases:
            with self.subTest(expected=expected):

                class _SniffHandler(_TestHandler):
                    payload = body
                    headers = {"Content-Type": "application/octet-stream"}

                self.tearDown()
                self.start_server(_SniffHandler)
                fetched = self.fetch(self.retrieval_url())
                self.assertEqual(expected, fetched.media_type)

    def test_rejects_unrecognized_media_and_signature(self) -> None:
        class _BinaryHandler(_TestHandler):
            payload = b"\x00" * 64
            headers = {"Content-Type": "image/png"}

        self.tearDown()
        self.start_server(_BinaryHandler)
        with self.assertRaises(SourceError) as context:
            self.fetch(self.retrieval_url())
        self.assertIn(f"http://{TEST_HOST}:{self.port}/article", str(context.exception))
        self.assertNotIn("?", str(context.exception))


class ConstantsTests(unittest.TestCase):
    def test_exports_bounded_constants(self) -> None:
        self.assertEqual(20 * 1024 * 1024, MAX_RAW_BYTES)
        self.assertEqual(20, SOCKET_TIMEOUT_SECONDS)
        self.assertEqual(5, MAX_REDIRECTS)


class TransportExceptionTests(unittest.TestCase):
    def _url(self, query: str = "apikey=supersecret") -> str:
        return f"http://{TEST_HOST}/article?{query}"

    def test_dns_failure_uses_operation_label_and_redacted_origin(self) -> None:
        def failing_resolver(_host: str, _port: int) -> list[str]:
            raise socket.gaierror(8, "name resolution leak apikey=supersecret")

        with self.assertRaises(SourceError) as context:
            fetch_url(
                self._url(),
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=failing_resolver,
                connection_factory=lambda *_args: mock.Mock(),
            )
        message = str(context.exception)
        self.assertIn("dns resolution failed", message)
        self.assertIn(f"http://{TEST_HOST}/article", message)
        self.assertNotIn("apikey", message)
        self.assertNotIn("supersecret", message)
        self.assertNotIn("name resolution leak", message)

    def test_re_raises_existing_source_error_unchanged(self) -> None:
        original = SourceError("blocked network destination for sentinel")

        def resolver(_host: str, _port: int) -> list[str]:
            raise original

        with self.assertRaises(SourceError) as context:
            fetch_url(
                self._url(),
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=resolver,
                connection_factory=lambda *_args: mock.Mock(),
            )
        self.assertIs(context.exception, original)

    def test_connect_timeout_maps_to_sanitized_network_error(self) -> None:
        class _TimeoutConnection:
            sock = None

            def connect(self) -> None:
                raise TimeoutError("timed out with secret=apikey")

            def close(self) -> None:
                return

        with self.assertRaises(SourceError) as context:
            fetch_url(
                self._url(),
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for(TEST_HOST),
                connection_factory=lambda *_args: _TimeoutConnection(),
            )
        message = str(context.exception)
        self.assertIn("network connect failed", message)
        self.assertIn(f"http://{TEST_HOST}/article", message)
        self.assertNotIn("apikey", message)
        self.assertNotIn("secret=", message)

    def test_response_read_failure_maps_to_sanitized_error(self) -> None:
        class _ReadFailResponse:
            status = 200

            def read(self, _size: int) -> bytes:
                raise OSError("read failed secret=supersecret")

            def getheader(self, _name: str) -> None:
                return None

        class _ReadFailConnection:
            def __init__(self) -> None:
                self.sock = mock.Mock()
                self.sock.getpeername.return_value = (TEST_HOST, 80)

            def connect(self) -> None:
                return

            def request(self, *_args: object, **_kwargs: object) -> None:
                return

            def getresponse(self) -> _ReadFailResponse:
                return _ReadFailResponse()

            def close(self) -> None:
                return

        with self.assertRaises(SourceError) as context:
            fetch_url(
                self._url(),
                allow_private_network=False,
                user_agent="Socratic-Learn/test",
                resolver=_resolver_for(TEST_HOST),
                connection_factory=lambda *_args: _ReadFailConnection(),
            )
        message = str(context.exception)
        self.assertIn("response read failed", message)
        self.assertNotIn("supersecret", message)
        self.assertNotIn("read failed secret", message)


class SanitizedErrorTests(_HttpTestCase):
    def test_error_keeps_display_origin_without_query_secret(self) -> None:
        class _FailHandler(_TestHandler):
            headers = {"Content-Type": "image/png"}
            payload = b"not-valid"

        self.tearDown()
        self.start_server(_FailHandler)
        with self.assertRaises(SourceError) as context:
            self.fetch(self.retrieval_url(query="apikey=supersecret"))
        message = str(context.exception)
        self.assertIn(f"http://{TEST_HOST}:{self.port}/article", message)
        self.assertNotIn("apikey", message)
        self.assertNotIn("supersecret", message)


if __name__ == "__main__":
    unittest.main()
