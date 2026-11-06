from __future__ import annotations

import io
import json
import queue
import subprocess
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from evaluation.antigravity import (
    AntigravitySession,
    InfrastructureFailure,
    antigravity_argv,
    initial_bootstrap,
)
from evaluation.isolation import (
    LocalRuleContamination,
    create_run_layout,
    remove_runtime_root,
)
from evaluation.schema import load_stream_contract
from socratic_learn.hosts import ADAPTERS, command_for


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "fixtures"
    / "antigravity"
    / "stream-contract.json"
)


class RecordingStdin:
    def __init__(self, events: list[str]) -> None:
        self.data = bytearray()
        self.events = events
        self.closed = False

    def write(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("closed")
        self.events.append("stdin.write")
        self.data.extend(data)
        return len(data)

    def flush(self) -> None:
        self.events.append("stdin.flush")

    def close(self) -> None:
        self.events.append("stdin.close")
        self.closed = True


class RecordingStdout:
    def __init__(self, data: bytes, events: list[str]) -> None:
        self._stream = io.BytesIO(data)
        self.events = events
        self.closed = False

    def readline(self) -> bytes:
        self.events.append("stdout.readline")
        return self._stream.readline()

    def close(self) -> None:
        self.closed = True


class BlockingStdout:
    def __init__(self, events: list[str]) -> None:
        self._lines: queue.Queue[bytes] = queue.Queue()
        self.events = events
        self.closed = False

    def readline(self) -> bytes:
        self.events.append("stdout.readline")
        return self._lines.get()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._lines.put(b"")


class FakeProcess:
    def __init__(
        self,
        stdout: RecordingStdout | BlockingStdout,
        *,
        stderr: bytes = b"",
        returncode: int | None = 0,
        wait_actions: list[object] | None = None,
    ) -> None:
        self.events = stdout.events
        self.stdin = RecordingStdin(self.events)
        self.stdout = stdout
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.wait_actions = list(wait_actions or [])
        self.wait_timeouts: list[float | None] = []
        self.terminate_count = 0
        self.kill_count = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.wait_actions:
            action = self.wait_actions.pop(0)
            if isinstance(action, BaseException):
                raise action
            self.returncode = int(action)
        elif self.returncode is None:
            self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.terminate_count += 1
        self.stdout.close()

    def kill(self) -> None:
        self.kill_count += 1
        self.stdout.close()
        self.returncode = -9


def result_line(text: str) -> bytes:
    return (
        json.dumps(
            {
                "event": "result",
                "result": {"response": text, "status": "SUCCESS"},
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


class EvaluationAntigravityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.repository = root / "repository"
        self.repository.mkdir()
        self.user_home = root / "user-home"
        self.user_home.mkdir()
        self.runtime_base = self.user_home / "runtime"
        self.runtime_base.mkdir()
        self.layout = create_run_layout(
            self.repository,
            "suite",
            "scenario",
            raw_root=self.repository / ".semantic-runs",
            runtime_base=self.runtime_base,
            user_home=self.user_home,
        )
        self.contract = load_stream_contract(FIXTURE)

    def tearDown(self) -> None:
        if self.layout.runtime_root.exists():
            remove_runtime_root(self.layout, self.repository)
        self.temporary.cleanup()

    def session(
        self,
        process: FakeProcess,
        calls: list[tuple[list[str], dict[str, object]]] | None = None,
    ) -> AntigravitySession:
        def fake_popen(argv: list[str], **kwargs: object) -> FakeProcess:
            if calls is not None:
                calls.append((argv, kwargs))
            return process

        return AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={"KEEP": "yes"},
            popen=fake_popen,
        )

    def test_argv_is_exact_streaming_sandboxed_and_model_pinned(self) -> None:
        argv = antigravity_argv("agy", "captured-model-id", self.layout)

        self.assertEqual(
            (
                "agy",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--model",
                "captured-model-id",
                "--sandbox",
                "--disable-slash-commands",
                "--print-timeout",
                "300s",
                "--log-file",
                str(self.layout.raw / "antigravity.log"),
            ),
            argv,
        )
        self.assertNotIn("--print", argv)
        self.assertNotIn("--mode", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_bootstrap_delegates_to_public_launcher_adapter(self) -> None:
        goal = "learn cafés"
        public = command_for(
            ADAPTERS["antigravity"], "agy", self.layout.protocol, goal
        )
        self.assertEqual(public[2], initial_bootstrap(self.layout.protocol, goal))

    def test_adapter_has_no_learner_model_parameter(self) -> None:
        from inspect import signature

        parameters = signature(AntigravitySession).parameters
        self.assertNotIn("learner_model", parameters)
        self.assertNotIn("learner_runtime", parameters)

    def test_one_process_serves_two_turns_and_logs_exact_bytes(self) -> None:
        events: list[str] = []
        output = result_line("first tutor turn") + result_line("second tutor turn")
        process = FakeProcess(RecordingStdout(output, events))
        calls: list[tuple[list[str], dict[str, object]]] = []
        session = self.session(process, calls)

        session.start()
        first = session.send("first learner turn")
        second = session.send("second learner turn")
        session.close()

        self.assertEqual(1, len(calls))
        self.assertEqual("first tutor turn", first.text)
        self.assertEqual("second tutor turn", second.text)
        request_lines = bytes(process.stdin.data).splitlines()
        self.assertEqual(2, len(request_lines))
        self.assertEqual(
            ["first learner turn", "second learner turn"],
            [json.loads(line)["message"]["content"] for line in request_lines],
        )
        self.assertEqual(bytes(process.stdin.data), (self.layout.raw / "input.ndjson").read_bytes())
        self.assertEqual(output, (self.layout.raw / "output.ndjson").read_bytes())
        self.assertEqual(
            [
                "stdin.write",
                "stdin.flush",
                "stdout.readline",
                "stdin.write",
                "stdin.flush",
                "stdout.readline",
                "stdin.close",
            ],
            events[:7],
        )
        self.assertEqual("captured-model-id", session.model)
        self.assertEqual(self.contract.antigravity_version, session.runtime_version)

    def test_start_uses_external_cwd_isolated_environment_and_private_log(self) -> None:
        events: list[str] = []
        process = FakeProcess(RecordingStdout(b"", events))
        calls: list[tuple[list[str], dict[str, object]]] = []
        session = self.session(process, calls)

        session.start()
        session.close()

        argv, kwargs = calls[0]
        self.assertEqual(self.layout.cwd, kwargs["cwd"])
        self.assertFalse(self.layout.cwd.resolve().is_relative_to(self.repository.resolve()))
        self.assertEqual(str(self.layout.home), kwargs["env"]["SOCRATIC_LEARN_HOME"])  # type: ignore[index]
        self.assertEqual("1", kwargs["env"]["PYTHONDONTWRITEBYTECODE"])  # type: ignore[index]
        self.assertEqual("yes", kwargs["env"]["KEEP"])  # type: ignore[index]
        self.assertEqual(
            str(self.layout.raw / "antigravity.log"),
            argv[argv.index("--log-file") + 1],
        )
        self.assertIs(subprocess.PIPE, kwargs["stdin"])
        self.assertIs(subprocess.PIPE, kwargs["stdout"])
        self.assertIs(subprocess.PIPE, kwargs["stderr"])
        self.assertIs(False, kwargs["text"])

    def test_start_rechecks_local_rule_ancestors_before_popen(self) -> None:
        marker = self.layout.cwd.parent / "AGENTS.md"
        marker.write_text("must not be read", encoding="utf-8")
        popen_called = False

        def forbidden_popen(*args: object, **kwargs: object) -> FakeProcess:
            nonlocal popen_called
            popen_called = True
            raise AssertionError("must not launch")

        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=forbidden_popen,
        )

        with self.assertRaises(LocalRuleContamination):
            session.start()
        self.assertFalse(popen_called)
        self.assertEqual(0, session.close())

    def test_local_rule_check_is_the_last_prelaunch_operation(self) -> None:
        marker = self.layout.cwd.parent / "AGENTS.md"
        popen_called = False

        def environment_with_late_marker(*args: object) -> dict[str, str]:
            marker.write_text("must not be read", encoding="utf-8")
            return {}

        def forbidden_popen(*args: object, **kwargs: object) -> FakeProcess:
            nonlocal popen_called
            popen_called = True
            raise AssertionError("must not launch")

        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=forbidden_popen,
        )

        with patch(
            "evaluation.antigravity.isolated_environment",
            environment_with_late_marker,
        ):
            with self.assertRaises(LocalRuleContamination):
                session.start()
        self.assertFalse(popen_called)

    def test_start_refuses_cwd_inside_explicit_repository_without_popen(self) -> None:
        unsafe = self.repository / "learning"
        unsafe.mkdir()
        layout = replace(self.layout, cwd=unsafe)
        calls = 0

        def forbidden_popen(*args: object, **kwargs: object) -> FakeProcess:
            nonlocal calls
            calls += 1
            raise AssertionError("must not launch")

        session = AntigravitySession(
            "agy",
            "captured-model-id",
            layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=forbidden_popen,
        )
        with self.assertRaises(ValueError):
            session.start()
        self.assertEqual(0, calls)
        self.assertEqual(0, session.close())

    def test_start_refuses_runtime_root_inside_explicit_repository(self) -> None:
        layout = replace(self.layout, runtime_root=self.repository)
        session = AntigravitySession(
            "agy",
            "captured-model-id",
            layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=lambda *args, **kwargs: self.fail("must not launch"),
        )
        with self.assertRaises(ValueError):
            session.start()

    def test_malformed_output_is_logged_before_runtime_failure(self) -> None:
        bad = b'{"event":not-json}\n'
        process = FakeProcess(RecordingStdout(bad, []))
        session = self.session(process)
        session.start()

        with self.assertRaises(InfrastructureFailure) as raised:
            session.send("hello")

        self.assertEqual("runtime", raised.exception.kind)
        self.assertNotIn("not-json", raised.exception.detail)
        self.assertEqual(bad, (self.layout.raw / "output.ndjson").read_bytes())
        session.close()

    def test_failed_result_is_infrastructure_not_pedagogical_output(self) -> None:
        raw = (
            b'{"event":"result","result":{"status":"ERROR",'
            b'"response":"API_KEY=secret provider prose"}}\n'
        )
        process = FakeProcess(
            RecordingStdout(raw, []),
            stderr=b"quota exceeded\n",
            returncode=None,
        )
        session = self.session(process)
        session.start()

        with self.assertRaises(InfrastructureFailure) as raised:
            session.send("hello")

        self.assertEqual("quota", raised.exception.kind)
        self.assertNotIn("secret", raised.exception.detail)
        self.assertEqual(raw, (self.layout.raw / "output.ndjson").read_bytes())
        session.close()

    def test_early_eof_is_runtime_failure(self) -> None:
        process = FakeProcess(RecordingStdout(b"", []), returncode=0)
        session = self.session(process)
        session.start()

        with self.assertRaises(InfrastructureFailure) as raised:
            session.send("hello")

        self.assertEqual("runtime", raised.exception.kind)
        self.assertEqual("Antigravity ended before completing the turn.", raised.exception.detail)
        session.close()

    def test_timeout_closes_process_and_leaves_no_reader_thread(self) -> None:
        stdout = BlockingStdout([])
        process = FakeProcess(stdout, returncode=None)
        session = self.session(process)
        session.start()

        with patch("evaluation.antigravity.READ_TIMEOUT_SECONDS", 0.01):
            with self.assertRaises(InfrastructureFailure) as raised:
                session.send("hello")

        self.assertEqual("timeout", raised.exception.kind)
        self.assertTrue(process.stdin.closed)
        self.assertFalse(session._stdout_thread.is_alive())  # type: ignore[union-attr]
        self.assertEqual(0, session.close())

    def test_nonzero_exit_classification_is_deterministic_and_stderr_is_exact(self) -> None:
        cases = (
            (b"invalid API key: secret-value\n", "authentication"),
            (b"quota exceeded for project secret\n", "quota"),
            (b"connection reset by peer\n", "network"),
            (b"provider exploded at C:\\Users\\private\\file\n", "runtime"),
        )
        for index, (stderr, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                if index:
                    self.tearDown()
                    self.setUp()
                process = FakeProcess(
                    RecordingStdout(b"", []), stderr=stderr, returncode=17
                )
                session = self.session(process)
                session.start()
                with self.assertRaises(InfrastructureFailure) as raised:
                    session.send("hello")
                self.assertEqual(expected, raised.exception.kind)
                self.assertNotIn("secret", raised.exception.detail)
                self.assertNotIn("Users", raised.exception.detail)
                session.close()
                self.assertEqual(stderr, (self.layout.raw / "stderr.log").read_bytes())

    def test_stderr_is_drained_while_process_is_running(self) -> None:
        stderr = b"x" * (1024 * 1024)
        process = FakeProcess(
            RecordingStdout(result_line("ok"), []),
            stderr=stderr,
        )
        session = self.session(process)
        session.start()
        turn = session.send("hello")
        session.close()

        self.assertEqual("ok", turn.text)
        self.assertEqual(stderr, (self.layout.raw / "stderr.log").read_bytes())

    def test_state_errors_and_close_are_safe_and_idempotent(self) -> None:
        process = FakeProcess(RecordingStdout(result_line("unused"), []))
        session = self.session(process)

        with self.assertRaises(InfrastructureFailure) as before:
            session.send("before")
        self.assertEqual("runtime", before.exception.kind)
        self.assertEqual(0, session.close())
        self.assertEqual(0, session.close())

        second = self.session(FakeProcess(RecordingStdout(b"", [])))
        second.start()
        with self.assertRaises(InfrastructureFailure):
            second.start()
        self.assertEqual(0, second.close())
        with self.assertRaises(InfrastructureFailure) as after:
            second.send("after")
        self.assertEqual("runtime", after.exception.kind)
        self.assertEqual(0, second.close())

    def test_launch_failure_is_sanitized_and_close_remains_safe(self) -> None:
        secret = "API_KEY=do-not-leak C:\\Users\\private\\file"

        def fail_launch(*args: object, **kwargs: object) -> FakeProcess:
            raise OSError(secret)

        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=fail_launch,
        )
        with self.assertRaises(InfrastructureFailure) as raised:
            session.start()

        self.assertEqual("runtime", raised.exception.kind)
        self.assertNotIn(secret, raised.exception.detail)
        self.assertEqual(0, session.close())

    def test_close_escalates_once_then_returns_child_status(self) -> None:
        events: list[str] = []
        process = FakeProcess(
            RecordingStdout(b"", events),
            returncode=None,
            wait_actions=[
                subprocess.TimeoutExpired("agy", 10),
                subprocess.TimeoutExpired("agy", 5),
                137,
            ],
        )
        session = self.session(process)
        session.start()

        result = session.close()

        self.assertEqual(137, result)
        self.assertEqual([10, 5, None], process.wait_timeouts)
        self.assertEqual(1, process.terminate_count)
        self.assertEqual(1, process.kill_count)
        self.assertEqual(137, session.close())


class InfrastructureFailureTests(unittest.TestCase):
    def test_failure_rejects_unknown_kind_and_normalizes_detail_to_one_line(self) -> None:
        with self.assertRaises(ValueError):
            InfrastructureFailure("other", "bad")  # type: ignore[arg-type]

        failure = InfrastructureFailure("network", "line one\r\nline two")
        self.assertEqual("line one line two", failure.detail)
        self.assertNotIn("\n", str(failure))

    def test_failure_detail_rejects_credentials_and_paths(self) -> None:
        unsafe = InfrastructureFailure(
            "runtime",
            "API_KEY=do-not-leak at C:\\Users\\private\\response.txt",
        )

        self.assertEqual("Infrastructure failure.", unsafe.detail)
        self.assertNotIn("do-not-leak", str(unsafe))
        self.assertNotIn("Users", str(unsafe))


if __name__ == "__main__":
    unittest.main()
