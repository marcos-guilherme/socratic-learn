from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from socratic_learn.errors import FilesystemError, UsageError
from socratic_learn.launcher import LaunchOptions, run_learning


class LauncherTests(unittest.TestCase):
    def test_first_run_prompts_goal_and_agent_then_saves_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            answers = iter(["probability", "1"])
            calls: list[tuple[list[str], Path]] = []

            def fake_run(
                argv: list[str], *, cwd: Path, check: bool
            ) -> CompletedProcess[str]:
                calls.append((argv, cwd))
                return CompletedProcess(argv, 0)

            result = run_learning(
                LaunchOptions(goal=None, agent=None, here=False, cwd=Path.cwd()),
                input_fn=lambda prompt: next(answers),
                output=io.StringIO(),
                which={"pi": "C:/bin/pi.exe"}.get,
                run_process=fake_run,
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(0, result)
            self.assertIn("probability", calls[0][0])
            self.assertIn(
                '"default_agent": "pi"',
                (Path(temporary) / "config.json").read_text("utf-8"),
            )

    def test_child_exit_code_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                input_fn=lambda prompt: "",
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: CompletedProcess(argv, 23),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )
            self.assertEqual(23, result)

    def test_no_agent_fails_before_goal_prompt_with_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            prompts: list[str] = []

            with self.assertRaisesRegex(UsageError, "compatible agent") as raised:
                run_learning(
                    LaunchOptions(None, None, False, Path.cwd()),
                    input_fn=lambda prompt: prompts.append(prompt) or "logic",
                    output=io.StringIO(),
                    which=lambda name: None,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )

            self.assertEqual([], prompts)
            self.assertIsNotNone(raised.exception.remediation)

    def test_empty_prompted_goal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UsageError, "goal"):
                run_learning(
                    LaunchOptions(None, "pi", False, Path.cwd()),
                    input_fn=lambda prompt: " \t ",
                    output=io.StringIO(),
                    which={"pi": "pi"}.get,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )

    def test_explicit_agent_must_be_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UsageError, "claude"):
                run_learning(
                    LaunchOptions("logic", "claude", False, Path.cwd()),
                    input_fn=lambda prompt: self.fail("must not prompt"),
                    output=io.StringIO(),
                    which={"pi": "pi"}.get,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )

    def test_saved_missing_host_prompts_once_and_rewrites_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / "config.json").write_text(
                '{"schema_version": 1, "default_agent": "claude"}\n',
                encoding="utf-8",
            )
            prompts: list[str] = []
            output = io.StringIO()

            result = run_learning(
                LaunchOptions("logic", None, False, Path.cwd()),
                input_fn=lambda prompt: prompts.append(prompt) or "1",
                output=output,
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(0, result)
            self.assertEqual(1, len(prompts))
            self.assertIn("claude", output.getvalue())
            self.assertIn(
                '"default_agent": "pi"',
                (home / "config.json").read_text(encoding="utf-8"),
            )

    def test_agent_selection_accepts_only_a_listed_number(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            answers = iter(["claude", "0", "3", "2"])
            prompts: list[str] = []
            calls: list[list[str]] = []

            result = run_learning(
                LaunchOptions("logic", None, False, Path.cwd()),
                input_fn=lambda prompt: prompts.append(prompt) or next(answers),
                output=io.StringIO(),
                which={"pi": "pi", "claude": "claude"}.get,
                run_process=lambda argv, **kwargs: (
                    calls.append(argv) or CompletedProcess(argv, 0)
                ),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(0, result)
            self.assertEqual(4, len(prompts))
            self.assertEqual("claude", calls[0][0])

    def test_here_uses_supplied_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            working_directories: list[Path] = []

            result = run_learning(
                LaunchOptions("logic", "pi", True, project),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=lambda argv, *, cwd, check: (
                    working_directories.append(cwd) or CompletedProcess(argv, 0)
                ),
                environ={"SOCRATIC_LEARN_HOME": str(Path(temporary) / "home")},
            )

            self.assertEqual(0, result)
            self.assertEqual([project.resolve()], working_directories)

    def test_goal_with_spaces_and_unicode_remains_one_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            calls: list[list[str]] = []
            goal = "Bayes cafés"

            run_learning(
                LaunchOptions(goal, "pi", False, Path.cwd()),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: (
                    calls.append(argv) or CompletedProcess(argv, 0)
                ),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(1, calls[0].count(goal))

    def test_child_inherits_stdio_and_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            keyword_arguments: list[dict[str, object]] = []

            def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[str]:
                keyword_arguments.append(kwargs)
                return CompletedProcess(argv, 0)

            run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=fake_run,
                environ={
                    "SOCRATIC_LEARN_HOME": temporary,
                    "ANTHROPIC_API_KEY": "must-not-appear",
                },
            )

            self.assertEqual(
                {"cwd", "check"},
                set(keyword_arguments[0]),
            )
            self.assertFalse(keyword_arguments[0]["check"])

    def test_credentials_are_not_written_or_printed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            secret = "ANTHROPIC_API_KEY=must-not-appear"

            run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                output=output,
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
                environ={
                    "SOCRATIC_LEARN_HOME": temporary,
                    "ANTHROPIC_API_KEY": secret,
                },
            )

            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn(
                secret,
                (Path(temporary) / "config.json").read_text(encoding="utf-8")
                if (Path(temporary) / "config.json").exists()
                else "",
            )

    def test_keyboard_interrupt_from_child_returns_130(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def interrupt(argv: list[str], **kwargs: object) -> CompletedProcess[str]:
                raise KeyboardInterrupt

            result = run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=interrupt,
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(130, result)

    def test_keyboard_interrupt_while_prompting_is_not_caught(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(KeyboardInterrupt):
                run_learning(
                    LaunchOptions(None, None, False, Path.cwd()),
                    input_fn=lambda prompt: (_ for _ in ()).throw(KeyboardInterrupt),
                    output=io.StringIO(),
                    which={"pi": "pi"}.get,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )

    def test_executable_disappearance_is_a_filesystem_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            def disappeared(
                argv: list[str], **kwargs: object
            ) -> CompletedProcess[str]:
                raise FileNotFoundError(argv[0])

            with self.assertRaises(FilesystemError) as raised:
                run_learning(
                    LaunchOptions("logic", "pi", False, Path.cwd()),
                    output=io.StringIO(),
                    which={"pi": "C:/bin/pi.exe"}.get,
                    run_process=disappeared,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )

            self.assertIn("pi", str(raised.exception))
            self.assertIn("C:/bin/pi.exe", str(raised.exception))
