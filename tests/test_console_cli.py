from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.cli import main
from socratic_learn.errors import IntegrityError
from socratic_learn.launcher import LaunchOptions


class ConsoleCliTests(unittest.TestCase):
    def setUp(self) -> None:
        banner_patcher = mock.patch("socratic_learn.cli.write_banner")
        self.write_banner = banner_patcher.start()
        self.addCleanup(banner_patcher.stop)

    def assert_banner_written_once(self) -> None:
        self.write_banner.assert_called_once_with(sys.stdout, os.environ)

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_no_arguments_launches_with_prompt(self, run: mock.Mock) -> None:
        events: list[str] = []
        self.write_banner.side_effect = lambda *_: events.append("banner")
        run.side_effect = lambda *_: events.append("run") or 0

        self.assertEqual(0, main([]))

        self.assert_banner_written_once()
        run.assert_called_once_with(
            LaunchOptions(None, None, False, Path.cwd())
        )
        self.assertEqual(["banner", "run"], events)

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_direct_goal_and_options_launch(self, run: mock.Mock) -> None:
        events: list[str] = []
        self.write_banner.side_effect = lambda *_: events.append("banner")
        run.side_effect = lambda *_: events.append("run") or 0

        self.assertEqual(
            0,
            main(["--agent", "pi", "--here", "linear", "algebra"]),
        )

        self.assert_banner_written_once()
        run.assert_called_once_with(
            LaunchOptions("linear algebra", "pi", True, Path.cwd())
        )
        self.assertEqual(["banner", "run"], events)

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_explicit_learn_allows_reserved_goal(self, run: mock.Mock) -> None:
        self.assertEqual(0, main(["learn", "doctor"]))
        self.assert_banner_written_once()
        run.assert_called_once_with(
            LaunchOptions("doctor", None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.administrative_main", return_value=7)
    def test_admin_command_is_forwarded_unchanged(
        self,
        admin: mock.Mock,
    ) -> None:
        self.assertEqual(7, main(["doctor", "project"]))
        admin.assert_called_once_with(["doctor", "project"])
        self.write_banner.assert_not_called()

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    @mock.patch("socratic_learn.cli.administrative_main")
    def test_admin_word_after_flag_is_a_goal(
        self,
        admin: mock.Mock,
        run: mock.Mock,
    ) -> None:
        self.assertEqual(0, main(["--here", "doctor", "project"]))
        self.assert_banner_written_once()
        admin.assert_not_called()
        run.assert_called_once_with(
            LaunchOptions("doctor project", None, True, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_launcher_options_can_follow_learn(
        self,
        run: mock.Mock,
    ) -> None:
        self.assertEqual(
            0,
            main(["learn", "--agent", "claude", "matrix", "proofs"]),
        )
        self.assert_banner_written_once()
        run.assert_called_once_with(
            LaunchOptions("matrix proofs", "claude", False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.administrative_main")
    @mock.patch("socratic_learn.cli.update_installation", return_value=6)
    def test_update_routes_to_self_management_only(
        self,
        update: mock.Mock,
        admin: mock.Mock,
    ) -> None:
        home = Path("C:/managed-home")
        with mock.patch("socratic_learn.cli.launcher_home", return_value=home):
            self.assertEqual(6, main(["update"]))

        update.assert_called_once_with(home, mock.ANY)
        admin.assert_not_called()
        self.write_banner.assert_not_called()

    @mock.patch("socratic_learn.cli.administrative_main")
    @mock.patch("socratic_learn.cli.uninstall", return_value=7)
    def test_uninstall_routes_flags_to_self_management_only(
        self,
        remove: mock.Mock,
        admin: mock.Mock,
    ) -> None:
        home = Path("C:/managed-home")
        with mock.patch("socratic_learn.cli.launcher_home", return_value=home):
            self.assertEqual(
                7,
                main(["uninstall", "--delete-data", "--yes"]),
            )

        remove.assert_called_once_with(
            home,
            executable=mock.ANY,
            delete_data=True,
            confirm=mock.ANY,
            yes=True,
        )
        admin.assert_not_called()
        self.write_banner.assert_not_called()

    @mock.patch("socratic_learn.cli.uninstall")
    def test_yes_without_delete_data_is_rejected_before_uninstall(
        self,
        remove: mock.Mock,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["uninstall", "--yes"])

        self.assertEqual(2, exit_code)
        self.assertIn("--yes", stderr.getvalue())
        remove.assert_not_called()
        self.write_banner.assert_not_called()

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_explicit_learn_allows_self_management_word_as_goal(
        self,
        run: mock.Mock,
    ) -> None:
        self.assertEqual(0, main(["learn", "uninstall"]))
        self.assert_banner_written_once()
        run.assert_called_once_with(
            LaunchOptions("uninstall", None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning")
    def test_launcher_rejects_abbreviated_agent_option(
        self,
        run: mock.Mock,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["--ag", "pi", "algebra"])

        self.assertEqual(2, exit_code)
        self.assertIn("--ag", stderr.getvalue())
        run.assert_not_called()
        self.write_banner.assert_not_called()

    def test_help_names_launcher_options_admin_commands_and_examples(
        self,
    ) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--help"])

        self.assertEqual(0, raised.exception.code)
        help_text = stdout.getvalue()
        for expected in (
            "--agent",
            "--here",
            "build",
            "export",
            "install",
            "doctor",
            "Examples:",
        ):
            self.assertIn(expected, help_text)
        self.write_banner.assert_not_called()

    def test_version_prints_distribution_version(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual("socratic-learn 0.1.0\n", stdout.getvalue())
        self.write_banner.assert_not_called()

    @mock.patch(
        "socratic_learn.cli.run_learning",
        side_effect=IntegrityError(
            "launcher data unavailable",
            remediation="reinstall the package",
        ),
    )
    def test_known_errors_are_actionable_without_traceback(
        self,
        run: mock.Mock,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["algebra"])

        message = stderr.getvalue()
        self.assertEqual(4, exit_code)
        self.assertIn("launcher data unavailable", message)
        self.assertIn("reinstall the package", message)
        self.assertNotIn("Traceback", message)
        self.assert_banner_written_once()


if __name__ == "__main__":
    unittest.main()
