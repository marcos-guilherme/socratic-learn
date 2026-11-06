"""Private persistent Antigravity adapter for semantic evaluation runs."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, cast

from evaluation.isolation import (
    RunLayout,
    assert_no_local_rule_ancestors,
    isolated_environment,
)
from evaluation.parser import (
    TutorTurn,
    collect_tutor_turn,
    is_completion,
    parse_ndjson,
    request_line,
)
from evaluation.schema import JsonValue, StreamContract
from socratic_learn.hosts import ADAPTERS, command_for


FailureKind = Literal["authentication", "quota", "network", "runtime", "timeout"]
TURN_TIMEOUT_SECONDS = 330.0
PRE_SEND_GUARD_SECONDS = 0.05
EXIT_SETTLE_SECONDS = 0.5
STDERR_DRAIN_SECONDS = 0.5
CLOSE_WAIT_SECONDS = 10.0
TERMINATE_WAIT_SECONDS = 5.0
KILL_WAIT_SECONDS = 1.0
THREAD_JOIN_SECONDS = 0.25
STDERR_TAIL_BYTES = 64 * 1024
_FAILURE_KINDS = frozenset(
    {"authentication", "quota", "network", "runtime", "timeout"}
)
_READER_ERROR = object()
_MISSING = object()
_UNSAFE_DETAIL = re.compile(
    r"(?i)(?:"
    r"\b(?:authorization|api[_-]?key|access[_-]?token|secret|credential)\s*[:=]"
    r"|\bbearer\s+\S+"
    r"|\b[A-Z]:[\\/]"
    r"|/(?:Users|home)/"
    r"|\\\\[^\\\s]+\\[^\\\s]+"
    r")"
)


class InfrastructureFailure(RuntimeError):
    """A non-pedagogical failure safe to include in a private run record."""

    def __init__(self, kind: FailureKind, detail: str) -> None:
        if kind not in _FAILURE_KINDS:
            raise ValueError("unsupported infrastructure failure kind")
        normalized = " ".join(detail.split())
        if not normalized:
            normalized = "Infrastructure failure."
        elif _UNSAFE_DETAIL.search(normalized):
            normalized = "Infrastructure failure."
        self.kind = kind
        self.detail = normalized[:200]
        super().__init__(self.detail)


def initial_bootstrap(protocol: Path, goal: str) -> str:
    """Return the public launcher's Antigravity bootstrap without duplicating it."""
    return command_for(
        ADAPTERS["antigravity"],
        "agy",
        protocol,
        goal,
    )[2]


def antigravity_argv(
    executable: str,
    model: str,
    layout: RunLayout,
) -> tuple[str, ...]:
    """Build the approved private structured-streaming command."""
    return (
        executable,
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--model",
        model,
        "--sandbox",
        "--disable-slash-commands",
        "--print-timeout",
        "300s",
        "--log-file",
        str(layout.raw / "antigravity.log"),
    )


def _inside(candidate: Path, repository: Path) -> bool:
    try:
        candidate.resolve().relative_to(repository.resolve())
    except ValueError:
        return False
    return True


def _append_private(path: Path, data: bytes, private_root: Path) -> None:
    """Append bytes with an owner-only file mode beneath the private root.

    On Windows the containing directory's effective privacy is governed by its
    inherited ACL; chmod alone cannot replace the isolation provided by RunLayout.
    """
    root = private_root.resolve(strict=True)
    destination = path.resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as error:
        raise ValueError("raw log destination is outside the private root") from error
    if destination == root:
        raise ValueError("raw log destination must be a file")

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_APPEND
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(destination, flags, 0o600)
    try:
        try:
            os.chmod(destination, 0o600)
        except OSError:
            os.close(descriptor)
            descriptor = -1
            raise
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("private append made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _captured_success_status(contract: StreamContract) -> JsonValue | object:
    for sample in contract.sample_output_events:
        if not is_completion(sample, contract):
            continue
        result = sample.get("result")
        if isinstance(result, dict) and "status" in result:
            return result["status"]
    return _MISSING


def _result_succeeded(
    event: dict[str, JsonValue],
    contract: StreamContract,
) -> bool:
    expected = _captured_success_status(contract)
    if expected is _MISSING:
        return True
    result = event.get("result")
    if not isinstance(result, dict) or "status" not in result:
        return False
    actual = result["status"]
    return type(actual) is type(expected) and actual == expected


def _classify(stderr: bytes) -> FailureKind:
    text = stderr.decode("utf-8", errors="ignore").lower()
    if any(
        marker in text
        for marker in (
            "authentication",
            "unauthenticated",
            "unauthorized",
            "invalid api key",
            "invalid_api_key",
            "login required",
            "credential",
        )
    ):
        return "authentication"
    if any(
        marker in text
        for marker in (
            "quota",
            "rate limit",
            "rate_limit",
            "resource_exhausted",
            "billing",
            "http 429",
            "status 429",
        )
    ):
        return "quota"
    if any(
        marker in text
        for marker in (
            "timeout",
            "timed out",
            "deadline exceeded",
        )
    ):
        return "timeout"
    if any(
        marker in text
        for marker in (
            "network",
            "connection",
            "dns",
            "socket",
            "tls",
            "certificate",
            "host unreachable",
        )
    ):
        return "network"
    return "runtime"


def _detail(kind: FailureKind, *, early_eof: bool = False) -> str:
    if early_eof:
        return "Antigravity ended before completing the turn."
    return {
        "authentication": "Antigravity authentication failed.",
        "quota": "Antigravity quota was unavailable.",
        "network": "Antigravity network access failed.",
        "runtime": "Antigravity runtime failed.",
        "timeout": "Antigravity turn timed out.",
    }[kind]


class AntigravitySession:
    """Own one binary Antigravity process for a multi-turn evaluation session."""

    def __init__(
        self,
        executable: str,
        model: str,
        layout: RunLayout,
        contract: StreamContract,
        *,
        repository: Path,
        parent_environment: Mapping[str, str],
        popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    ) -> None:
        self.executable = executable
        self.model = model
        self.runtime_version = contract.antigravity_version
        self.layout = layout
        self.contract = contract
        self.repository = repository
        self.parent_environment = parent_environment
        self.popen = popen

        self._process: subprocess.Popen[bytes] | None = None
        self._stdout_results: queue.Queue[object] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail = bytearray()
        self._stderr_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._stderr_log_failed = False
        self._output_log_failed = False
        self._completed_turns = 0
        self._failed = False
        self._closed = False
        self._returncode: int | None = None

    def start(self) -> None:
        if self._process is not None or self._closed:
            raise InfrastructureFailure("runtime", "Antigravity session is not startable.")

        argv = antigravity_argv(self.executable, self.model, self.layout)
        environment = isolated_environment(self.layout, self.parent_environment)
        try:
            _append_private(
                self.layout.raw / "antigravity.log",
                b"",
                self.layout.raw,
            )
        except Exception:
            raise InfrastructureFailure(
                "runtime", "Antigravity private logging could not be prepared."
            ) from None
        if _inside(self.layout.cwd, self.repository) or _inside(
            self.layout.runtime_root, self.repository
        ):
            raise ValueError("Antigravity runtime paths must be outside the repository")
        assert_no_local_rule_ancestors(self.layout.cwd, self.layout.user_home)
        try:
            process = self.popen(
                list(argv),
                cwd=self.layout.cwd,
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            )
        except Exception:
            raise InfrastructureFailure(
                "runtime", "Antigravity could not be started."
            ) from None

        if process.stdin is None or process.stdout is None or process.stderr is None:
            try:
                process.kill()
            finally:
                try:
                    process.wait(timeout=KILL_WAIT_SECONDS)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            raise InfrastructureFailure(
                "runtime", "Antigravity did not provide binary pipes."
            )

        self._process = process
        self._stdout_thread = threading.Thread(
            target=self._stdout_reader,
            name="antigravity-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader,
            name="antigravity-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _stdout_reader(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        while True:
            try:
                line = process.stdout.readline()
            except Exception:
                self._stdout_results.put(_READER_ERROR)
                return
            raw = bytes(line)
            if raw:
                try:
                    _append_private(
                        self.layout.raw / "output.ndjson",
                        raw,
                        self.layout.raw,
                    )
                except Exception:
                    self._output_log_failed = True
            self._stdout_results.put(raw)
            if not raw:
                return

    def _remember_stderr(self, raw: bytes) -> None:
        with self._stderr_lock:
            self._stderr_tail.extend(raw)
            excess = len(self._stderr_tail) - STDERR_TAIL_BYTES
            if excess > 0:
                del self._stderr_tail[:excess]

    def _stderr_reader(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        while True:
            try:
                chunk = process.stderr.read(64 * 1024)
            except Exception:
                return
            if not chunk:
                return
            raw = bytes(chunk)
            self._remember_stderr(raw)
            try:
                _append_private(
                    self.layout.raw / "stderr.log",
                    raw,
                    self.layout.raw,
                )
            except Exception:
                self._stderr_log_failed = True

    def _stderr_bytes(self) -> bytes:
        with self._stderr_lock:
            return bytes(self._stderr_tail)

    def _bounded_wait(self, timeout: float) -> int | None:
        process = self._process
        if process is None:
            return 0
        returncode = process.poll()
        if returncode is not None:
            return returncode
        try:
            return process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            return process.poll()

    def _settled_failure(
        self,
        *,
        early_eof_candidate: bool = False,
    ) -> InfrastructureFailure:
        returncode = self._bounded_wait(EXIT_SETTLE_SECONDS)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=STDERR_DRAIN_SECONDS)
        if self._stderr_log_failed or self._output_log_failed:
            return InfrastructureFailure("runtime", _detail("runtime"))
        kind = _classify(self._stderr_bytes())
        return InfrastructureFailure(
            kind,
            _detail(
                kind,
                early_eof=early_eof_candidate and returncode == 0,
            ),
        )

    def _queued_output_before_request(self) -> InfrastructureFailure | None:
        if not self._completed_turns:
            return None
        try:
            queued = self._stdout_results.get(timeout=PRE_SEND_GUARD_SECONDS)
        except queue.Empty:
            return None
        if queued is _READER_ERROR:
            return self._settled_failure()
        if not isinstance(queued, bytes):
            return InfrastructureFailure("runtime", _detail("runtime"))
        if not queued:
            return self._settled_failure(early_eof_candidate=True)
        return InfrastructureFailure(
            "runtime",
            "Antigravity produced output before the next request.",
        )

    def _next_stdout_line(self, deadline: float) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InfrastructureFailure("timeout", _detail("timeout"))
        try:
            result = self._stdout_results.get(timeout=remaining)
        except queue.Empty:
            raise InfrastructureFailure("timeout", _detail("timeout")) from None
        if result is _READER_ERROR:
            raise self._settled_failure()
        if not isinstance(result, bytes):
            raise InfrastructureFailure("runtime", _detail("runtime"))
        return result

    def _send(self, text: str) -> TutorTurn:
        process = self._process
        if self._failed:
            raise InfrastructureFailure(
                "runtime", "Antigravity session has failed."
            )
        if self._closed or process is None:
            raise InfrastructureFailure(
                "runtime", "Antigravity session is not running."
            )
        if process.stdin is None:
            raise InfrastructureFailure(
                "runtime", "Antigravity input is unavailable."
            )

        queued_failure = self._queued_output_before_request()
        if queued_failure is not None:
            raise queued_failure

        request = request_line(self.contract, text)
        try:
            _append_private(
                self.layout.raw / "input.ndjson",
                request,
                self.layout.raw,
            )
        except Exception:
            raise InfrastructureFailure(
                "runtime", "Antigravity input could not be recorded."
            ) from None
        try:
            process.stdin.write(request)
            process.stdin.flush()
        except Exception:
            raise self._settled_failure() from None

        deadline = time.monotonic() + TURN_TIMEOUT_SECONDS
        events: list[dict[str, JsonValue]] = []
        while True:
            line = self._next_stdout_line(deadline)
            if self._output_log_failed or self._stderr_log_failed:
                raise InfrastructureFailure("runtime", _detail("runtime"))
            if not line:
                raise self._settled_failure(early_eof_candidate=True)
            try:
                parsed = parse_ndjson(line)
            except ValueError:
                raise InfrastructureFailure(
                    "runtime", "Antigravity returned malformed output."
                ) from None
            if len(parsed) != 1:
                raise InfrastructureFailure(
                    "runtime", "Antigravity returned malformed output."
                )
            event = parsed[0]
            events.append(event)
            if is_completion(event, self.contract):
                if not _result_succeeded(event, self.contract):
                    raise self._settled_failure()
                self._completed_turns += 1
                return collect_tutor_turn(events, self.contract)

    def send(self, text: str) -> TutorTurn:
        with self._send_lock:
            try:
                return self._send(text)
            except InfrastructureFailure as failure:
                self._failed = True
                if failure.kind == "timeout":
                    self.close()
                raise

    @staticmethod
    def _close_pipe_if_reader_stopped(
        pipe: object,
        reader: threading.Thread | None,
    ) -> None:
        if reader is not None and reader.is_alive():
            return
        try:
            pipe.close()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _finish_reader_cleanup(self) -> None:
        process = self._process
        if process is None:
            return
        for thread in (self._stdout_thread, self._stderr_thread):
            if thread is not None:
                thread.join(timeout=THREAD_JOIN_SECONDS)
        if process.stdout is not None:
            self._close_pipe_if_reader_stopped(
                process.stdout,
                self._stdout_thread,
            )
        if process.stderr is not None:
            self._close_pipe_if_reader_stopped(
                process.stderr,
                self._stderr_thread,
            )

    def close(self) -> int:
        if self._closed:
            self._finish_reader_cleanup()
            return 0 if self._returncode is None else self._returncode
        self._closed = True
        process = self._process
        if process is None:
            self._returncode = 0
            return 0

        if process.stdin is not None:
            try:
                process.stdin.close()
            except Exception:
                pass

        returncode = self._bounded_wait(CLOSE_WAIT_SECONDS)
        if returncode is None:
            try:
                process.terminate()
            except Exception:
                pass
            returncode = self._bounded_wait(TERMINATE_WAIT_SECONDS)
        if returncode is None:
            try:
                process.kill()
            except Exception:
                pass
            returncode = self._bounded_wait(KILL_WAIT_SECONDS)

        self._finish_reader_cleanup()

        confirmed = process.poll()
        self._returncode = (
            confirmed
            if confirmed is not None
            else (-9 if returncode is None else cast(int, returncode))
        )
        return self._returncode
