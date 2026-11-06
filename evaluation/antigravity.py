"""Private persistent Antigravity adapter for semantic evaluation runs."""

from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
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
READ_TIMEOUT_SECONDS = 300.0
_FAILURE_KINDS = frozenset(
    {"authentication", "quota", "network", "runtime", "timeout"}
)
_READ_REQUEST = object()
_STOP_READER = object()
_READER_ERROR = object()
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
    """Append one byte sequence beneath private_root with owner-only permissions."""
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


def _result_succeeded(event: dict[str, JsonValue]) -> bool:
    result = event.get("result")
    if not isinstance(result, dict):
        return True
    status = result.get("status")
    return not isinstance(status, str) or status.upper() == "SUCCESS"


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
        self._stdout_requests: queue.Queue[object] = queue.Queue()
        self._stdout_results: queue.Queue[object] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._closed = False
        self._returncode: int | None = None

    def start(self) -> None:
        if self._process is not None or self._closed:
            raise InfrastructureFailure("runtime", "Antigravity session is not startable.")

        argv = antigravity_argv(self.executable, self.model, self.layout)
        environment = isolated_environment(self.layout, self.parent_environment)
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
                process.wait()
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
            request = self._stdout_requests.get()
            if request is _STOP_READER:
                return
            try:
                line = process.stdout.readline()
            except Exception:
                self._stdout_results.put(_READER_ERROR)
            else:
                self._stdout_results.put(line)

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
            try:
                _append_private(
                    self.layout.raw / "stderr.log",
                    raw,
                    self.layout.raw,
                )
            except Exception:
                return
            with self._stderr_lock:
                self._stderr.extend(raw)

    def _stderr_bytes(self) -> bytes:
        thread = self._stderr_thread
        if thread is not None:
            thread.join(timeout=0.1)
        with self._stderr_lock:
            return bytes(self._stderr)

    def _failure_from_stderr(self, *, early_eof: bool = False) -> InfrastructureFailure:
        kind = _classify(self._stderr_bytes())
        return InfrastructureFailure(kind, _detail(kind, early_eof=early_eof))

    def _next_stdout_line(self) -> bytes:
        self._stdout_requests.put(_READ_REQUEST)
        try:
            result = self._stdout_results.get(timeout=READ_TIMEOUT_SECONDS)
        except queue.Empty:
            self.close()
            raise InfrastructureFailure(
                "timeout", _detail("timeout")
            ) from None
        if result is _READER_ERROR or not isinstance(result, bytes):
            raise InfrastructureFailure(
                "runtime", "Antigravity output could not be read."
            )
        return result

    def send(self, text: str) -> TutorTurn:
        with self._send_lock:
            process = self._process
            if self._closed or process is None:
                raise InfrastructureFailure(
                    "runtime", "Antigravity session is not running."
                )
            if process.stdin is None:
                raise InfrastructureFailure(
                    "runtime", "Antigravity input is unavailable."
                )

            request = request_line(self.contract, text)
            try:
                process.stdin.write(request)
                process.stdin.flush()
                _append_private(
                    self.layout.raw / "input.ndjson",
                    request,
                    self.layout.raw,
                )
            except Exception:
                raise InfrastructureFailure(
                    "runtime", "Antigravity input could not be sent."
                ) from None

            events: list[dict[str, JsonValue]] = []
            while True:
                line = self._next_stdout_line()
                if not line:
                    if process.poll() not in (None, 0):
                        raise self._failure_from_stderr()
                    raise self._failure_from_stderr(early_eof=True)
                try:
                    _append_private(
                        self.layout.raw / "output.ndjson",
                        line,
                        self.layout.raw,
                    )
                except Exception:
                    raise InfrastructureFailure(
                        "runtime", "Antigravity output could not be recorded."
                    ) from None
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
                    if not _result_succeeded(event):
                        raise self._failure_from_stderr()
                    return collect_tutor_turn(events, self.contract)

    def close(self) -> int:
        if self._closed:
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

        try:
            returncode = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                returncode = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait()

        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=5)
        if process.stdout is not None:
            try:
                process.stdout.close()
            except Exception:
                pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except Exception:
                pass
        self._stdout_requests.put(_STOP_READER)
        if self._stdout_thread is not None:
            self._stdout_thread.join(timeout=1)
        if self._stderr_thread is not None and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1)

        self._returncode = cast(int, returncode)
        return self._returncode
