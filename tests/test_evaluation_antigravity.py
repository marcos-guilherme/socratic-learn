from __future__ import annotations

import io
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from collections.abc import Callable
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
    def __init__(
        self,
        events: list[str],
        on_flush: Callable[[], None] | None = None,
    ) -> None:
        self.data = bytearray()
        self.events = events
        self.closed = False
        self.on_flush = on_flush

    def write(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("closed")
        self.events.append("stdin.write")
        self.data.extend(data)
        return len(data)

    def flush(self) -> None:
        self.events.append("stdin.flush")
        if self.on_flush is not None:
            self.on_flush()

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


class GatedStdout(BlockingStdout):
    def __init__(self, lines: list[bytes], events: list[str]) -> None:
        super().__init__(events)
        self.pending = list(lines)

    def release(self) -> None:
        if self.pending:
            self._lines.put(self.pending.pop(0))


class FakeProcess:
    def __init__(
        self,
        stdout: RecordingStdout | BlockingStdout | GatedStdout,
        *,
        stderr: bytes = b"",
        returncode: int | None = 0,
        wait_actions: list[object] | None = None,
    ) -> None:
        self.events = stdout.events
        callback = stdout.release if isinstance(stdout, GatedStdout) else None
        self.stdin = RecordingStdin(self.events, callback)
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
        if self.returncode is not None and self.stdout is not None:
            self.stdout.close()
        return self.returncode

    def terminate(self) -> None:
        self.terminate_count += 1
        self.stdout.close()

    def kill(self) -> None:
        self.kill_count += 1
        self.stdout.close()
        self.returncode = -9


class MissingPipeProcess(FakeProcess):
    def __init__(self) -> None:
        super().__init__(RecordingStdout(b"", []), returncode=None)
        self.stdout = None  # type: ignore[assignment]

    def kill(self) -> None:
        self.kill_count += 1
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


def wait_until(predicate: object, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.01)
    return bool(predicate())  # type: ignore[operator]


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

    def local_session(
        self,
        script: str,
        *,
        environment: dict[str, str] | None = None,
    ) -> tuple[AntigravitySession, list[subprocess.Popen[bytes]]]:
        processes: list[subprocess.Popen[bytes]] = []

        def local_popen(
            argv: list[str], **kwargs: object
        ) -> subprocess.Popen[bytes]:
            process = subprocess.Popen(
                [sys.executable, "-u", "-c", textwrap.dedent(script)],
                **kwargs,
            )
            processes.append(process)
            return process

        parent = dict(os.environ)
        if environment:
            parent.update(environment)
        return (
            AntigravitySession(
                "agy",
                "captured-model-id",
                self.layout,
                self.contract,
                repository=self.repository,
                parent_environment=parent,
                popen=local_popen,
            ),
            processes,
        )

    def stop_grandchild(
        self,
        pid_file: Path,
        stop_file: Path,
        done_file: Path,
    ) -> None:
        if not wait_until(pid_file.exists):
            self.fail("grandchild pid was not recorded")
        pid = int(pid_file.read_text(encoding="ascii"))
        stop_file.touch()
        if wait_until(done_file.exists):
            return
        if os.name == "nt":
            subprocess.run(
                ("taskkill", "/PID", str(pid), "/F", "/T"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.kill(pid, signal.SIGKILL)
        time.sleep(0.1)

    def assert_no_nondaemon_adapter_threads(self) -> None:
        leaked = [
            thread.name
            for thread in threading.enumerate()
            if thread.name.startswith("antigravity-") and not thread.daemon
        ]
        self.assertEqual([], leaked)

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

    def test_evaluation_initial_message_matches_public_antigravity_bootstrap(self) -> None:
        protocol = Path("C:/isolated/.socratic-learn/socratic-learn.prompt.md")
        goal = "learn cafés"
        public = command_for(
            ADAPTERS["antigravity"],
            "agy",
            protocol,
            goal,
        )
        self.assertEqual(public[2], initial_bootstrap(protocol, goal))

    def test_adapter_has_no_learner_model_parameter(self) -> None:
        from inspect import signature

        parameters = signature(AntigravitySession).parameters
        self.assertNotIn("learner_model", parameters)
        self.assertNotIn("learner_runtime", parameters)

    def test_one_process_serves_two_turns_and_logs_exact_bytes(self) -> None:
        events: list[str] = []
        lines = [result_line("first tutor turn"), result_line("second tutor turn")]
        output = b"".join(lines)
        process = FakeProcess(GatedStdout(lines, events))
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
        self.assertEqual(2, events.count("stdin.write"))
        self.assertEqual(2, events.count("stdin.flush"))
        self.assertGreaterEqual(events.count("stdout.readline"), 2)
        self.assertLess(events.index("stdin.write"), events.index("stdin.flush"))
        self.assertEqual("captured-model-id", session.model)
        self.assertEqual(self.contract.antigravity_version, session.runtime_version)

    def test_real_local_process_serves_two_turns(self) -> None:
        session, processes = self.local_session(
            """
            import json
            import sys

            for number, line in enumerate(sys.stdin.buffer, 1):
                request = json.loads(line)
                event = {
                    "event": "result",
                    "result": {
                        "response": f"turn-{number}:" + request["message"]["content"],
                        "status": "SUCCESS",
                    },
                }
                sys.stdout.write(json.dumps(event, separators=(",", ":")) + "\\n")
                sys.stdout.flush()
            """
        )
        try:
            session.start()
            self.assertEqual("turn-1:first", session.send("first").text)
            self.assertEqual("turn-2:second", session.send("second").text)
            self.assertEqual(0, session.close())
            self.assertEqual(1, len(processes))
            self.assert_no_nondaemon_adapter_threads()
        finally:
            session.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_completion_success_marker_is_derived_from_contract_sample(self) -> None:
        from copy import deepcopy
        from dataclasses import replace as replace_dataclass

        samples = deepcopy(self.contract.sample_output_events)
        completion = next(
            event for event in samples if event.get("event") == "result"
        )
        completion["result"]["status"] = "CAPTURED_OK"  # type: ignore[index]
        contract = replace_dataclass(
            self.contract,
            sample_output_events=tuple(samples),
        )
        output = (
            b'{"event":"result","result":{"response":"ok",'
            b'"status":"CAPTURED_OK"}}\n'
        )
        process = FakeProcess(RecordingStdout(output, []), returncode=None)
        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            contract,
            repository=self.repository,
            parent_environment={},
            popen=lambda *args, **kwargs: process,
        )

        session.start()
        self.assertEqual("ok", session.send("hello").text)
        session.close()

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

        with patch("evaluation.antigravity.TURN_TIMEOUT_SECONDS", 0.01):
            with self.assertRaises(InfrastructureFailure) as raised:
                session.send("hello")

        self.assertEqual("timeout", raised.exception.kind)
        self.assertTrue(process.stdin.closed)
        self.assertFalse(session._stdout_thread.is_alive())  # type: ignore[union-attr]
        self.assertEqual(0, session.close())

    def test_turn_timeout_uses_one_absolute_deadline(self) -> None:
        session, processes = self.local_session(
            """
            import json
            import sys
            import time

            sys.stdin.buffer.readline()
            for index in range(20):
                print(json.dumps({"event": "progress", "index": index}), flush=True)
                time.sleep(0.03)
            """
        )
        started = time.monotonic()
        try:
            session.start()
            with patch.multiple(
                "evaluation.antigravity",
                TURN_TIMEOUT_SECONDS=0.12,
                CLOSE_WAIT_SECONDS=0.05,
                TERMINATE_WAIT_SECONDS=0.05,
                KILL_WAIT_SECONDS=0.2,
                THREAD_JOIN_SECONDS=0.05,
            ):
                with self.assertRaises(InfrastructureFailure) as raised:
                    session.send("hello")
            elapsed = time.monotonic() - started
            self.assertEqual("timeout", raised.exception.kind)
            self.assertLess(elapsed, 1.0)
            self.assert_no_nondaemon_adapter_threads()
        finally:
            session.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_authentication_exit_classifies_same_immediate_or_delayed(self) -> None:
        for send_delay in (0.0, 0.16):
            with self.subTest(send_delay=send_delay):
                if send_delay:
                    self.tearDown()
                    self.setUp()
                session, processes = self.local_session(
                    """
                    import os
                    import sys
                    import time

                    time.sleep(0.08)
                    print("authentication failed: private provider text", file=sys.stderr, flush=True)
                    raise SystemExit(17)
                    """,
                )
                try:
                    session.start()
                    time.sleep(send_delay)
                    with patch.multiple(
                        "evaluation.antigravity",
                        EXIT_SETTLE_SECONDS=0.3,
                        STDERR_DRAIN_SECONDS=0.3,
                    ):
                        with self.assertRaises(InfrastructureFailure) as raised:
                            session.send("hello")
                    self.assertEqual("authentication", raised.exception.kind)
                    self.assertEqual(
                        "Antigravity authentication failed.",
                        raised.exception.detail,
                    )
                    self.assertEqual(17, processes[0].poll())
                    self.assertIn(
                        b"authentication failed",
                        (self.layout.raw / "stderr.log").read_bytes(),
                    )
                finally:
                    session.close()
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=2)

    def test_infrastructure_failure_makes_session_permanently_unsendable(self) -> None:
        malformed = b'{"event":not-json}\n' + result_line("must-not-bleed")
        process = FakeProcess(RecordingStdout(malformed, []), returncode=None)
        session = self.session(process)
        session.start()

        with self.assertRaises(InfrastructureFailure):
            session.send("first")
        with self.assertRaises(InfrastructureFailure) as raised:
            session.send("second")

        self.assertEqual("runtime", raised.exception.kind)
        self.assertEqual(
            "Antigravity session has failed.",
            raised.exception.detail,
        )
        self.assertEqual(1, len((self.layout.raw / "input.ndjson").read_bytes().splitlines()))
        session.close()

    def test_queued_post_completion_output_fails_before_next_request(self) -> None:
        received = self.layout.cwd / "received.txt"
        session, processes = self.local_session(
            """
            import json
            import os
            import sys
            from pathlib import Path

            received = Path(os.environ["TEST_RECEIVED"])
            first = sys.stdin.buffer.readline()
            received.write_text("1", encoding="ascii")
            success = {
                "event": "result",
                "result": {"response": "ok", "status": "SUCCESS"},
            }
            rogue = {"event": "progress", "text": "must not bleed"}
            print(json.dumps(success, separators=(",", ":")), flush=True)
            print(json.dumps(rogue, separators=(",", ":")), flush=True)
            for line in sys.stdin.buffer:
                received.write_text("2", encoding="ascii")
            """,
            environment={"TEST_RECEIVED": str(received)},
        )
        try:
            session.start()
            self.assertEqual("ok", session.send("first").text)
            with patch("evaluation.antigravity.PRE_SEND_GUARD_SECONDS", 0.15):
                with self.assertRaises(InfrastructureFailure) as raised:
                    session.send("second")
            self.assertEqual("runtime", raised.exception.kind)
            self.assertEqual("1", received.read_text(encoding="ascii"))
            self.assertIn(
                b"must not bleed",
                (self.layout.raw / "output.ndjson").read_bytes(),
            )
            self.assertEqual(
                1,
                len((self.layout.raw / "input.ndjson").read_bytes().splitlines()),
            )
        finally:
            session.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_stderr_log_failure_keeps_draining_and_forces_runtime(self) -> None:
        stderr = b"authentication failed\n" + (b"x" * (1024 * 1024))
        process = FakeProcess(
            RecordingStdout(b"", []),
            stderr=stderr,
            returncode=17,
        )
        session = self.session(process)
        original_append = __import__(
            "evaluation.antigravity", fromlist=["_append_private"]
        )._append_private

        def fail_stderr_log(path: Path, data: bytes, root: Path) -> None:
            if path.name == "stderr.log":
                raise OSError("private path must not leak")
            original_append(path, data, root)

        session.start()
        with patch("evaluation.antigravity._append_private", fail_stderr_log):
            with self.assertRaises(InfrastructureFailure) as raised:
                session.send("hello")

        self.assertEqual("runtime", raised.exception.kind)
        self.assertEqual("Antigravity runtime failed.", raised.exception.detail)
        self.assertGreaterEqual(len(session._stderr_tail), 64 * 1024)
        session.close()

    def test_stderr_log_failure_rejects_otherwise_successful_turn(self) -> None:
        process = FakeProcess(
            GatedStdout([result_line("must-not-return")], []),
            stderr=b"diagnostic\n",
            returncode=None,
        )
        session = self.session(process)
        original_append = __import__(
            "evaluation.antigravity", fromlist=["_append_private"]
        )._append_private

        def fail_stderr_log(path: Path, data: bytes, root: Path) -> None:
            if path.name == "stderr.log":
                raise OSError("private path must not leak")
            original_append(path, data, root)

        with patch("evaluation.antigravity._append_private", fail_stderr_log):
            session.start()
            self.assertTrue(wait_until(lambda: session._stderr_log_failed))
            with self.assertRaises(InfrastructureFailure) as raised:
                session.send("hello")

        self.assertEqual("runtime", raised.exception.kind)
        self.assertEqual("Antigravity runtime failed.", raised.exception.detail)
        session.close()

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

    def test_missing_pipe_cleanup_uses_bounded_child_wait(self) -> None:
        process = MissingPipeProcess()
        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=lambda *args, **kwargs: process,
        )

        with self.assertRaises(InfrastructureFailure):
            session.start()

        self.assertEqual(1, process.kill_count)
        self.assertEqual([1.0], process.wait_timeouts)

    def test_runtime_log_is_precreated_privately_before_popen(self) -> None:
        observed = False
        process = FakeProcess(RecordingStdout(b"", []))

        def inspect_popen(*args: object, **kwargs: object) -> FakeProcess:
            nonlocal observed
            log = self.layout.raw / "antigravity.log"
            observed = log.is_file() and log.read_bytes() == b""
            return process

        session = AntigravitySession(
            "agy",
            "captured-model-id",
            self.layout,
            self.contract,
            repository=self.repository,
            parent_environment={},
            popen=inspect_popen,
        )
        session.start()
        session.close()
        self.assertTrue(observed)

    def test_close_is_bounded_when_grandchild_inherits_output_handles(self) -> None:
        pid_file = self.layout.cwd / "grandchild.pid"
        stop_file = self.layout.cwd / "grandchild.stop"
        done_file = self.layout.cwd / "grandchild.done"
        session, processes = self.local_session(
            """
            import os
            import subprocess
            import sys
            from pathlib import Path

            code = '''
            import os
            import time
            from pathlib import Path
            stop = Path(os.environ["TEST_STOP_FILE"])
            deadline = time.monotonic() + 20
            while not stop.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            Path(os.environ["TEST_DONE_FILE"]).touch()
            '''
            child = subprocess.Popen([sys.executable, "-u", "-c", code])
            Path(os.environ["TEST_PID_FILE"]).write_text(str(child.pid), encoding="ascii")
            """,
            environment={
                "TEST_PID_FILE": str(pid_file),
                "TEST_STOP_FILE": str(stop_file),
                "TEST_DONE_FILE": str(done_file),
            },
        )
        try:
            session.start()
            self.assertTrue(wait_until(pid_file.exists))
            started = time.monotonic()
            with patch.multiple(
                "evaluation.antigravity",
                CLOSE_WAIT_SECONDS=0.05,
                TERMINATE_WAIT_SECONDS=0.05,
                KILL_WAIT_SECONDS=0.2,
                THREAD_JOIN_SECONDS=0.05,
            ):
                session.close()
            self.assertLess(time.monotonic() - started, 0.8)
            self.assert_no_nondaemon_adapter_threads()
        finally:
            self.stop_grandchild(pid_file, stop_file, done_file)
            session.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_timeout_is_bounded_when_grandchild_inherits_output_handles(self) -> None:
        pid_file = self.layout.cwd / "grandchild.pid"
        stop_file = self.layout.cwd / "grandchild.stop"
        done_file = self.layout.cwd / "grandchild.done"
        session, processes = self.local_session(
            """
            import os
            import subprocess
            import sys
            import time
            from pathlib import Path

            code = '''
            import os
            import time
            from pathlib import Path
            stop = Path(os.environ["TEST_STOP_FILE"])
            deadline = time.monotonic() + 20
            while not stop.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            Path(os.environ["TEST_DONE_FILE"]).touch()
            '''
            child = subprocess.Popen([sys.executable, "-u", "-c", code])
            Path(os.environ["TEST_PID_FILE"]).write_text(str(child.pid), encoding="ascii")
            sys.stdin.buffer.readline()
            time.sleep(20)
            """,
            environment={
                "TEST_PID_FILE": str(pid_file),
                "TEST_STOP_FILE": str(stop_file),
                "TEST_DONE_FILE": str(done_file),
            },
        )
        try:
            session.start()
            self.assertTrue(wait_until(pid_file.exists))
            started = time.monotonic()
            with patch.multiple(
                "evaluation.antigravity",
                TURN_TIMEOUT_SECONDS=0.08,
                CLOSE_WAIT_SECONDS=0.05,
                TERMINATE_WAIT_SECONDS=0.05,
                KILL_WAIT_SECONDS=0.2,
                THREAD_JOIN_SECONDS=0.05,
            ):
                with self.assertRaises(InfrastructureFailure) as raised:
                    session.send("hello")
            self.assertEqual("timeout", raised.exception.kind)
            self.assertLess(time.monotonic() - started, 0.9)
            self.assert_no_nondaemon_adapter_threads()
        finally:
            self.stop_grandchild(pid_file, stop_file, done_file)
            session.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

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

        self.assertEqual(-9, result)
        self.assertEqual([10.0, 5.0], process.wait_timeouts)
        self.assertEqual(1, process.terminate_count)
        self.assertEqual(1, process.kill_count)
        self.assertEqual(-9, session.close())


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
