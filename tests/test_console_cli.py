from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.cli import main
from socratic_learn.errors import IntegrityError
from socratic_learn.launcher import LaunchOptions


class ConsoleCliTests(unittest.TestCase):
    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_no_arguments_launches_with_prompt(self, run: mock.Mock) -> None:
        self.assertEqual(0, main([]))
        run.assert_called_once_with(
            LaunchOptions(None, None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_direct_goal_and_options_launch(self, run: mock.Mock) -> None:
        self.assertEqual(
            0,
            main(["--agent", "pi", "--here", "linear", "algebra"]),
        )
        run.assert_called_once_with(
            LaunchOptions("linear algebra", "pi", True, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_explicit_learn_allows_reserved_goal(self, run: mock.Mock) -> None:
        self.assertEqual(0, main(["learn", "doctor"]))
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

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    @mock.patch("socratic_learn.cli.administrative_main")
    def test_admin_word_after_flag_is_a_goal(
        self,
        admin: mock.Mock,
        run: mock.Mock,
    ) -> None:
        self.assertEqual(0, main(["--here", "doctor", "project"]))
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
        run.assert_called_once_with(
            LaunchOptions("matrix proofs", "claude", False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning")
    def test_self_management_tokens_are_reserved(
        self,
        run: mock.Mock,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["update"])

        self.assertEqual(2, exit_code)
        self.assertIn("reserved", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        run.assert_not_called()

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_explicit_learn_allows_self_management_word_as_goal(
        self,
        run: mock.Mock,
    ) -> None:
        self.assertEqual(0, main(["learn", "uninstall"]))
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

    def test_version_prints_distribution_version(self) -> None:
        stdout = io.StringIO()

        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual("socratic-learn 0.1.0\n", stdout.getvalue())

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


if __name__ == "__main__":
    unittest.main()
