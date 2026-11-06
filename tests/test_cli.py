from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.__main__ import main
from socratic_learn.errors import CollisionError, FilesystemError, IntegrityError


class CliContractTests(unittest.TestCase):
    def test_canonical_module_help_uses_socratic_learn_name(self) -> None:
        repository = Path(__file__).resolve().parents[1]

        completed = subprocess.run(
            [sys.executable, "-m", "socratic_learn", "--help"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("usage: socratic-learn", completed.stdout)

    def test_legacy_module_warns_once_and_forwards(self) -> None:
        repository = Path(__file__).resolve().parents[1]

        completed = subprocess.run(
            [sys.executable, "-m", "learning_tutor", "--help"],
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("deprecated", completed.stderr.lower())
        self.assertEqual(1, len(completed.stderr.splitlines()))
        self.assertIn("usage: socratic-learn", completed.stdout)

    def assert_usage_error(self, argv: list[str], command: str) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(argv)

        message = stderr.getvalue()
        self.assertEqual(2, exit_code)
        self.assertIn(command, message)
        self.assertIn("--help", message)
        self.assertNotIn("Traceback", message)

    def test_no_command_returns_usage_error(self) -> None:
        self.assert_usage_error([], "command")

    def test_unknown_command_returns_usage_error(self) -> None:
        self.assert_usage_error(["unknown"], "unknown")

    def test_install_rejects_unknown_target(self) -> None:
        self.assert_usage_error(["install", "unknown", "."], "unknown")

    def test_force_option_does_not_exist(self) -> None:
        self.assert_usage_error(
            ["install", "generic", ".", "--force"],
            "--force",
        )

    @mock.patch("socratic_learn.__main__._dispatch_install", return_value=0)
    def test_install_rejects_abbreviated_update(
        self,
        dispatch: mock.Mock,
    ) -> None:
        self.assert_usage_error(
            ["install", "generic", ".", "--up"],
            "--up",
        )
        dispatch.assert_not_called()

    @mock.patch("socratic_learn.__main__._dispatch_export_prompt", return_value=0)
    def test_export_rejects_abbreviated_output(
        self,
        dispatch: mock.Mock,
    ) -> None:
        self.assert_usage_error(
            ["export", "prompt", "--out", "prompt.md"],
            "--out",
        )
        dispatch.assert_not_called()

    def test_error_classes_have_stable_exit_codes(self) -> None:
        self.assertEqual(3, CollisionError("x").exit_code)
        self.assertEqual(4, IntegrityError("x").exit_code)
        self.assertEqual(5, FilesystemError("x").exit_code)

    def test_error_string_includes_supplied_fields(self) -> None:
        error = IntegrityError(
            "manifest mismatch",
            path="build/manifest.json",
            remediation="run build",
        )

        self.assertEqual(
            "manifest mismatch; path: build/manifest.json; remediation: run build",
            str(error),
        )

    @mock.patch("socratic_learn.__main__._dispatch_build", return_value=0)
    def test_build_dispatches(self, dispatch: mock.Mock) -> None:
        self.assertEqual(0, main(["build"]))
        dispatch.assert_called_once_with()

    @mock.patch("socratic_learn.__main__._dispatch_export_prompt", return_value=0)
    def test_export_prompt_dispatches_with_output(
        self,
        dispatch: mock.Mock,
    ) -> None:
        self.assertEqual(
            0,
            main(["export", "prompt", "--output", "prompt.md"]),
        )
        dispatch.assert_called_once_with(Path("prompt.md"))

    @mock.patch("socratic_learn.__main__._dispatch_install", return_value=0)
    def test_install_dispatches_with_options(self, dispatch: mock.Mock) -> None:
        self.assertEqual(
            0,
            main(["install", "cursor", "project", "--update"]),
        )
        dispatch.assert_called_once_with("cursor", Path("project"), update=True)

    @mock.patch("socratic_learn.__main__._dispatch_doctor", return_value=0)
    def test_doctor_dispatches(self, dispatch: mock.Mock) -> None:
        self.assertEqual(0, main(["doctor", "project"]))
        dispatch.assert_called_once_with(Path("project"))

    @mock.patch(
        "socratic_learn.__main__._dispatch_build",
        side_effect=IntegrityError(
            "implementation unavailable",
            remediation="install a complete package",
        ),
    )
    def test_known_errors_are_actionable_without_traceback(
        self,
        dispatch: mock.Mock,
    ) -> None:
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr):
            exit_code = main(["build"])

        message = stderr.getvalue()
        self.assertEqual(4, exit_code)
        self.assertIn("implementation unavailable", message)
        self.assertIn("install a complete package", message)
        self.assertNotIn("Traceback", message)

    @mock.patch(
        "socratic_learn.__main__._dispatch_build",
        side_effect=RuntimeError("unexpected"),
    )
    def test_unexpected_errors_are_not_swallowed(
        self,
        dispatch: mock.Mock,
    ) -> None:
        with self.assertRaisesRegex(RuntimeError, "unexpected"):
            main(["build"])


if __name__ == "__main__":
    unittest.main()
