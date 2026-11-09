from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.cli import main, parse_read_arguments, parse_source_origin
from socratic_learn.config import LauncherConfig
from socratic_learn.errors import SourceError, UsageError
from socratic_learn.hosts import ADAPTERS, DetectedHost
from socratic_learn.launcher import LaunchOptions
from socratic_learn.sources.model import SourceRequest
from socratic_learn.workspace import LearningWorkspace


class ParseSourceOriginTests(unittest.TestCase):
    def test_http_and_https_become_url_sources(self) -> None:
        http = parse_source_origin("http://example.com/article")
        https = parse_source_origin("HTTPS://Example.COM/x")
        self.assertEqual(
            SourceRequest("http://example.com/article", "url"),
            http,
        )
        self.assertEqual(
            SourceRequest("HTTPS://Example.COM/x", "url"),
            https,
        )

    def test_local_token_becomes_local_pdf(self) -> None:
        self.assertEqual(
            SourceRequest("paper.pdf", "local_pdf"),
            parse_source_origin("paper.pdf"),
        )

    def test_unsupported_url_scheme_raises_source_error(self) -> None:
        with self.assertRaises(SourceError) as raised:
            parse_source_origin("ftp://example.com/doc")
        self.assertEqual(6, raised.exception.exit_code)

    def test_allow_private_network_propagates_to_url_source(self) -> None:
        request = parse_source_origin(
            "http://localhost/article",
            allow_private_network=True,
        )
        self.assertTrue(request.allow_private_network)


class ParseReadArgumentsTests(unittest.TestCase):
    def test_url_source_and_goal_after_read(self) -> None:
        options = parse_read_arguments(
            ["read", "https://example.com/a", "evaluate", "evidence"],
            cwd=Path("C:/work"),
        )
        self.assertEqual(
            LaunchOptions(
                "evaluate evidence",
                None,
                False,
                Path("C:/work"),
                SourceRequest("https://example.com/a", "url"),
            ),
            options,
        )

    def test_local_pdf_and_options_before_read(self) -> None:
        options = parse_read_arguments(
            ["--agent", "pi", "--here", "read", "article.pdf"],
        )
        self.assertEqual(
            LaunchOptions(
                None,
                "pi",
                True,
                Path.cwd(),
                SourceRequest("article.pdf", "local_pdf"),
            ),
            options,
        )

    def test_global_read_options_after_read(self) -> None:
        options = parse_read_arguments(
            [
                "read",
                "--agent",
                "claude",
                "--allow-private-network",
                "http://127.0.0.1/x",
            ],
        )
        self.assertEqual("claude", options.agent)
        self.assertTrue(options.source.allow_private_network)

    def test_dash_source_requires_double_dash(self) -> None:
        options = parse_read_arguments(
            ["read", "--", "-secret.pdf", "my goal"],
        )
        self.assertEqual(
            SourceRequest("-secret.pdf", "local_pdf"),
            options.source,
        )
        self.assertEqual("my goal", options.goal)

    def test_agent_equals_form(self) -> None:
        options = parse_read_arguments(
            ["read", "--agent=antigravity", "doc.pdf"],
        )
        self.assertEqual("antigravity", options.agent)

    def test_missing_source_is_usage_error(self) -> None:
        with self.assertRaises(UsageError):
            parse_read_arguments(["read"])

    def test_options_after_source_token(self) -> None:
        options = parse_read_arguments(
            [
                "read",
                "article.pdf",
                "--here",
                "--agent",
                "claude",
                "--allow-private-network",
                "evaluate",
                "claims",
            ],
        )
        self.assertTrue(options.here)
        self.assertEqual("claude", options.agent)
        self.assertEqual("evaluate claims", options.goal)
        self.assertTrue(options.source.allow_private_network)
        self.assertEqual("article.pdf", options.source.origin)
        self.assertEqual("local_pdf", options.source.kind)

    def test_url_options_after_source_without_goal(self) -> None:
        options = parse_read_arguments(
            [
                "read",
                "https://example.com/doc",
                "--allow-private-network",
                "--agent",
                "pi",
            ],
        )
        self.assertEqual("pi", options.agent)
        self.assertIsNone(options.goal)
        self.assertTrue(options.source.allow_private_network)

    def test_read_mode_rejects_abbreviated_agent_option(self) -> None:
        with self.assertRaises(UsageError) as raised:
            parse_read_arguments(["read", "--ag", "pi", "doc.pdf"])
        self.assertIn("--ag", str(raised.exception))


class ReadConsoleDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        banner_patcher = mock.patch("socratic_learn.cli.write_banner")
        self.write_banner = banner_patcher.start()
        self.addCleanup(banner_patcher.stop)

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_read_dispatches_source_request(self, run: mock.Mock) -> None:
        pdf = Path(__file__).resolve().parents[0] / "fixtures/sources/minimal-text.pdf"
        self.assertEqual(
            0,
            main(
                [
                    "read",
                    "--agent",
                    "pi",
                    str(pdf),
                    "explain",
                    "evidence",
                ]
            ),
        )
        run.assert_called_once()
        options = run.call_args.args[0]
        self.assertIsInstance(options.source, SourceRequest)
        self.assertEqual("local_pdf", options.source.kind)
        self.assertEqual("explain evidence", options.goal)
        self.write_banner.assert_called_once_with(sys.stdout, os.environ)

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_learn_read_critically_stays_normal_goal(self, run: mock.Mock) -> None:
        self.assertEqual(0, main(["learn", "read", "critically"]))
        run.assert_called_once_with(
            LaunchOptions("read critically", None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_read_critically_uses_reserved_read_mode(self, run: mock.Mock) -> None:
        self.assertEqual(0, main(["read", "critically"]))
        options = run.call_args.args[0]
        self.assertEqual(SourceRequest("critically", "local_pdf"), options.source)
        self.assertIsNone(options.goal)

    def test_administrative_module_entry_stays_unchanged(self) -> None:
        from socratic_learn.__main__ import main as module_main

        with mock.patch(
            "socratic_learn.__main__._dispatch_doctor",
            return_value=0,
        ) as doctor:
            self.assertEqual(0, module_main(["doctor", "."]))
        doctor.assert_called_once()
        self.write_banner.assert_not_called()

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_allow_private_network_outside_read_is_rejected(
        self,
        run: mock.Mock,
    ) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["--allow-private-network", "algebra"])
        self.assertEqual(2, exit_code)
        run.assert_not_called()
        self.write_banner.assert_not_called()

    def test_read_mode_main_rejects_abbreviated_agent_option(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = main(["read", "--ag", "pi", "doc.pdf"])
        self.assertEqual(2, exit_code)
        self.assertIn("--ag", stderr.getvalue())
        self.write_banner.assert_not_called()

    def test_ingestion_source_error_exits_six_without_spawn(self) -> None:
        spawn = mock.Mock(side_effect=AssertionError("must not spawn"))
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            records = home / "records"
            records.mkdir()
            protocol = home / "protocol.md"
            protocol.write_text("protocol\n", encoding="utf-8")
            prepared = LearningWorkspace(home, protocol, records)
            with (
                mock.patch(
                    "socratic_learn.launcher.detect_hosts",
                    return_value={"pi": DetectedHost(ADAPTERS["pi"], "pi")},
                ),
                mock.patch(
                    "socratic_learn.launcher.load_config",
                    return_value=LauncherConfig(default_agent="pi"),
                ),
                mock.patch(
                    "socratic_learn.launcher.prepare_personal_workspace",
                    return_value=prepared,
                ),
                mock.patch(
                    "socratic_learn.launcher.ingest_source",
                    side_effect=SourceError("ingestion failed"),
                ),
                mock.patch("socratic_learn.launcher.subprocess.run", spawn),
            ):
                with contextlib.redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "read",
                            "--agent",
                            "pi",
                            "article.pdf",
                            "study",
                        ],
                    )
        self.assertEqual(6, exit_code)
        lines = [line for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual(1, len(lines))
        self.assertTrue(lines[0].startswith("error: "))
        self.assertIn("ingestion failed", lines[0])
        self.assertNotIn("Traceback", stderr.getvalue())
        spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
