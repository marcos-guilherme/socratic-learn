"""Bounded HTTP/HTTPS retrieval for article URL sources."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from collections.abc import Callable
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

from socratic_learn.errors import SourceError
from socratic_learn.sources.model import FetchedBytes

MAX_RAW_BYTES = 20 * 1024 * 1024
SOCKET_TIMEOUT_SECONDS = 20
MAX_REDIRECTS = 5

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

ConnectionFactory = Callable[[str, int, str, float], http.client.HTTPConnection]
Resolver = Callable[[str, int], list[str]]


def _is_blocked_address(address: ipaddress._BaseAddress, *, allow_private_network: bool) -> bool:
    if allow_private_network:
        return address.is_multicast or address.is_unspecified
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _parse_ip(value: str) -> ipaddress._BaseAddress:
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return ipaddress.ip_address(value)


def _validate_addresses(
    addresses: list[str],
    *,
    display_origin: str,
    allow_private_network: bool,
) -> None:
    if not addresses:
        raise SourceError(
            f"could not resolve {display_origin}",
            remediation="Verify the hostname and try another URL.",
        )
    for item in addresses:
        try:
            parsed = _parse_ip(item)
        except ValueError:
            raise SourceError(
                f"rejected address for {display_origin}",
                remediation="Verify the hostname and try another URL.",
            ) from None
        if _is_blocked_address(parsed, allow_private_network=allow_private_network):
            raise SourceError(
                f"blocked network destination for {display_origin}",
                remediation="Use a public URL or enable private-network access.",
            )


def _encode_host(host: str) -> str:
    if host.startswith("["):
        inner = host[1:-1]
        try:
            ip = ipaddress.ip_address(inner)
        except ValueError as error:
            raise SourceError("invalid URL host") from error
        return f"[{ip.compressed}]"
    try:
        return host.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise SourceError("invalid URL host") from error


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    segments = path.split("/")
    normalized: list[str] = []
    for index, segment in enumerate(segments):
        if index == 0 and segment == "":
            normalized.append("")
            continue
        normalized.append(quote(unquote(segment), safe=""))
    result = "/".join(normalized)
    if path.endswith("/") and not result.endswith("/"):
        result += "/"
    return result or "/"


def _canonical_port(scheme: str, port: int | None) -> int:
    default = _DEFAULT_PORTS[scheme]
    if port is None:
        return default
    if port < 1 or port > 65535:
        raise SourceError("invalid URL port")
    return port


def canonicalize_url(url: str) -> tuple[str, str]:
    if _CONTROL_CHARS.search(url):
        raise SourceError("malformed URL")
    try:
        parts = urlsplit(url.strip())
    except ValueError as error:
        raise SourceError("malformed URL") from error
    if not parts.scheme or not parts.hostname:
        raise SourceError("malformed URL")
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise SourceError("only HTTP and HTTPS URLs are supported")
    if parts.username is not None or parts.password is not None:
        raise SourceError("URL credentials are not allowed")
    host = _encode_host(parts.hostname)
    try:
        parsed_port = parts.port
    except ValueError as error:
        raise SourceError("invalid URL port") from error
    port = _canonical_port(scheme, parsed_port)
    path = _normalize_path(parts.path or "/")
    query = parts.query
    default_port = _DEFAULT_PORTS[scheme]
    host_part = f"{host}:{port}" if port != default_port else host
    retrieval = urlunsplit((scheme, host_part, path, query, ""))
    display = urlunsplit((scheme, host_part, path, "", ""))
    return retrieval, display


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise SourceError("could not resolve host") from error
    addresses: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addresses.append(sockaddr[0])
    return list(dict.fromkeys(addresses))


def _default_connection_factory(host: str, port: int, scheme: str, timeout: float) -> http.client.HTTPConnection:
    if scheme == "https":
        return http.client.HTTPSConnection(
            host,
            port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _request_path(retrieval_url: str) -> str:
    parts = urlsplit(retrieval_url)
    path = parts.path or "/"
    if parts.query:
        return f"{path}?{parts.query}"
    return path


def _classify_media_type(content_type: str | None, body: bytes, *, display_origin: str) -> str:
    header = (content_type or "").split(";", 1)[0].strip().lower()
    if header == "text/html":
        return "text/html"
    if header == "application/xhtml+xml":
        return "text/html"
    if header == "application/pdf":
        return "application/pdf"
    if header in {"", "application/octet-stream"}:
        sniff = body[:1024]
        lowered = sniff.lower()
        if b"%pdf-" in lowered:
            return "application/pdf"
        if b"<html" in lowered or b"<!doctype html" in lowered:
            return "text/html"
    raise SourceError(
        f"unsupported media type for {display_origin}",
        remediation="Provide HTML or PDF content.",
    )


def _read_bounded_body(response: http.client.HTTPResponse, *, display_origin: str) -> bytes:
    content_encoding = response.getheader("Content-Encoding")
    if content_encoding and content_encoding.strip().lower() != "identity":
        raise SourceError(
            f"compressed response rejected for {display_origin}",
            remediation="Provide an uncompressed source URL.",
        )
    body = bytearray()
    while True:
        chunk = response.read(65536)
        if not chunk:
            break
        if len(body) + len(chunk) > MAX_RAW_BYTES:
            raise SourceError(
                f"response too large for {display_origin}",
                remediation="Choose a smaller source URL.",
            )
        body.extend(chunk)
    return bytes(body)


def _peer_address(connection: http.client.HTTPConnection) -> str:
    sock = connection.sock
    if sock is None:
        raise SourceError("connection failed before peer validation")
    return sock.getpeername()[0]


def fetch_url(
    url: str,
    *,
    allow_private_network: bool,
    user_agent: str,
    resolver: Resolver | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> FetchedBytes:
    resolve = resolver or _default_resolver
    connect = connection_factory or _default_connection_factory
    current_url = url
    redirects = 0
    retrieval_url, display_origin = canonicalize_url(current_url)
    initial_display_origin = display_origin

    while True:
        parts = urlsplit(retrieval_url)
        scheme = parts.scheme
        hostname = parts.hostname
        if hostname is None:
            raise SourceError("malformed URL")
        port = _canonical_port(scheme, parts.port)

        addresses = resolve(hostname, port)
        _validate_addresses(
            addresses,
            display_origin=initial_display_origin,
            allow_private_network=allow_private_network,
        )

        connection = connect(hostname, port, scheme, SOCKET_TIMEOUT_SECONDS)
        try:
            connection.connect()
            peer = _peer_address(connection)
            _validate_addresses(
                [peer],
                display_origin=initial_display_origin,
                allow_private_network=allow_private_network,
            )

            headers = {
                "User-Agent": user_agent,
                "Accept-Encoding": "identity",
                "Host": parts.netloc.split("@")[-1],
            }
            connection.request("GET", _request_path(retrieval_url), headers=headers)
            response = connection.getresponse()

            if response.status in _REDIRECT_STATUSES:
                location = response.getheader("Location")
                response.read()
                connection.close()
                if location is None:
                    raise SourceError(
                        f"redirect missing location for {initial_display_origin}",
                        remediation="Verify the URL and try again.",
                    )
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise SourceError(
                        f"too many redirects for {initial_display_origin}",
                        remediation="Verify the URL and try again.",
                    )
                next_url = urljoin(retrieval_url, location)
                retrieval_url, display_origin = canonicalize_url(next_url)
                continue

            if response.status < 200 or response.status >= 300:
                response.read()
                raise SourceError(
                    f"HTTP request failed for {initial_display_origin}",
                    remediation="Verify the URL and try again.",
                )

            raw = _read_bounded_body(response, display_origin=initial_display_origin)
            media_type = _classify_media_type(
                response.getheader("Content-Type"),
                raw,
                display_origin=initial_display_origin,
            )
            return FetchedBytes(
                raw=raw,
                canonical_url=retrieval_url,
                display_origin=display_origin,
                media_type=media_type,
            )
        finally:
            if connection.sock is not None:
                connection.close()
