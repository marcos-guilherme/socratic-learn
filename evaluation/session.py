"""Manual adaptive semantic sessions and isolated runtime lifecycle ownership."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol, TextIO

from evaluation.antigravity import (
    FailureKind,
    InfrastructureFailure,
    ProcessCleanupError,
    initial_bootstrap,
)
from evaluation.isolation import (
    RULE_MARKERS,
    USER_HOME_RULE_PATHS,
    ProtocolIdentity,
    RunLayout,
    load_runtime_context,
    cleanup_sourced_study,
    prepare_sourced_study,
    remove_runtime_root,
    snapshot_learner_records,
)
from evaluation.parser import TutorTurn
from evaluation.sanitize import write_private
from evaluation.schema import (
    MAX_LEARNER_RESPONSES,
    FixtureIdentities,
    JsonValue,
    RUN_WRITE_SCHEMA_VERSION,
    RunRecord,
    Scenario,
    StopReason,
    TurnRecord,
    canonical_json,
    load_run_record,
)


_MANUAL_STOP_REASONS = frozenset(
    {
        "observable_outcome",
        "completion_without_evidence",
        "critical_pedagogical_failure",
    }
)
_EMPTY_TUTOR_TURN_DETAIL = "Tutor completed without response text."


class TutorSession(Protocol):
    model: str
    runtime_version: str

    def send(self, text: str) -> TutorTurn: ...


@dataclass(frozen=True)
class EvaluatorDecision:
    action: Literal["respond", "stop"]
    response: str | None
    stop_reason: StopReason | None


@dataclass(frozen=True)
class EvaluatorContext:
    scenario: Scenario
    tutor_turns: tuple[TutorTurn, ...]
    learner_responses: tuple[str, ...]


@dataclass
class SessionProgress:
    turns: list[TurnRecord]
    learner_response_count: int


class ConsoleEvaluator:
    """Human evaluator boundary; no learner model is accepted or configured."""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] = input,
        output: TextIO = sys.stdout,
    ) -> None:
        self._input = input_fn
        self._output = output

    @staticmethod
    def _items(value: tuple[str, ...] | str) -> str:
        if isinstance(value, str):
            return value
        return "\n".join(f"- {item}" for item in value)

    def decide(self, context: EvaluatorContext) -> EvaluatorDecision:
        persona = context.scenario.persona
        self._output.write(
            f"Scenario: {context.scenario.title}\n"
            f"Learner responses used: {len(context.learner_responses)}/15\n"
            "Persona knowledge:\n"
            f"{self._items(persona['knowledge'])}\n"
            "Persona misconception:\n"
            f"{self._items(persona['misconception'])}\n"
            "Communication style:\n"
            f"{self._items(persona['communication_style'])}\n"
            "Allowed progress:\n"
            f"{self._items(persona['allowed_progress'])}\n"
            "Forbidden behavior:\n"
            f"{self._items(persona['forbidden_behavior'])}\n"
            "Response policy:\n"
            f"{self._items(context.scenario.response_policy)}\n"
            "Tutor turn:\n"
            f"{context.tutor_turns[-1].text}\n\n"
            "Choose: respond | outcome | completion-without-evidence | critical-failure\n"
        )
        mapping: dict[str, StopReason] = {
            "outcome": "observable_outcome",
            "completion-without-evidence": "completion_without_evidence",
            "critical-failure": "critical_pedagogical_failure",
        }
        while True:
            choice = self._input("Choice: ").strip().lower()
            if choice == "respond":
                while True:
                    response = self._input("Learner response: ").strip()
                    if response:
                        return EvaluatorDecision("respond", response, None)
                    self._output.write("Learner response must not be empty.\n")
            if choice in mapping:
                return EvaluatorDecision("stop", None, mapping[choice])
            self._output.write("Choose one of the listed actions.\n")


class RuntimeCleanupError(RuntimeError):
    """Raised after a completed session when one or more cleanup steps failed."""

    def __init__(
        self,
        failed_steps: list[str] | tuple[str, ...],
        *,
        preserve_runtime: bool = False,
    ) -> None:
        self.failed_steps = tuple(failed_steps)
        self.preserve_runtime = preserve_runtime
        super().__init__(
            "Runtime cleanup failed: " + ", ".join(self.failed_steps)
        )


def _record_document(record: RunRecord) -> dict[str, JsonValue]:
    document = asdict(record)
    return document  # type: ignore[return-value]


def _suite_id(record_path: Path | None, run_id: str) -> str:
    if record_path is None:
        return run_id
    return record_path.parent.parent.name


def _validated_record_path(record_path: Path | None) -> Path | None:
    if record_path is None:
        return None
    candidate = Path(record_path).absolute().resolve(strict=False)
    if ".semantic-runs" not in candidate.parts:
        raise ValueError("record path must resolve under .semantic-runs")
    if candidate.exists():
        raise FileExistsError("run record already exists")
    if not candidate.parent.is_dir():
        raise ValueError("run record directory is unavailable")
    return candidate


def _write_record(path: Path | None, record: RunRecord) -> None:
    if path is None:
        return
    write_private(
        path,
        canonical_json(_record_document(record)),
        private_root=path.parent,
    )


def _run_record(
    *,
    scenario: Scenario,
    tutor: TutorSession,
    identity: ProtocolIdentity,
    run_id: str,
    suite_id: str,
    progress: SessionProgress,
    stop_reason: StopReason,
    infrastructure_failure: str | None,
    fixture_identities: FixtureIdentities,
    source_fixture_id: str | None = None,
    source_fixture_sha256: str | None = None,
) -> RunRecord:
    return RunRecord(
        schema_version=RUN_WRITE_SCHEMA_VERSION,
        run_id=run_id,
        suite_id=suite_id,
        scenario_id=scenario.identifier,
        repository_commit=identity.repository_commit,
        protocol_version=identity.protocol_version,
        protocol_sha256=identity.bundle_sha256,
        runtime="antigravity",
        runtime_version=tutor.runtime_version,
        model_identifier=tutor.model,
        learner_response_count=progress.learner_response_count,
        stop_reason=stop_reason,
        infrastructure_failure=infrastructure_failure,
        turns=tuple(progress.turns),
        scenario_sha256=fixture_identities.scenario_sha256,
        rubric_sha256=fixture_identities.rubric_sha256,
        suite_sha256=fixture_identities.suite_sha256,
        source_fixture_id=source_fixture_id,
        source_fixture_sha256=source_fixture_sha256,
    )


def run_session(
    scenario: Scenario,
    tutor: TutorSession,
    evaluator: ConsoleEvaluator,
    identity: ProtocolIdentity,
    initial_request: str,
    run_id: str,
    *,
    fixture_identities: FixtureIdentities,
    record_path: Path | None = None,
    progress: SessionProgress | None = None,
    source_fixture_id: str | None = None,
    source_fixture_sha256: str | None = None,
) -> RunRecord:
    """Run one bootstrap turn followed by at most fifteen adaptive responses."""
    destination = _validated_record_path(record_path)
    collector = progress if progress is not None else SessionProgress([], 0)
    if collector.turns or collector.learner_response_count:
        raise ValueError("session progress must be empty at session start")

    tutor_turns: list[TutorTurn] = []
    learner_responses: list[str] = []
    pending = initial_request
    pending_is_learner_response = False
    suite_id = _suite_id(destination, run_id)

    while True:
        try:
            tutor_turn = tutor.send(pending)
            if tutor_turn.completed and not tutor_turn.text.strip():
                raise InfrastructureFailure(
                    "runtime",
                    _EMPTY_TUTOR_TURN_DETAIL,
                )
        except InfrastructureFailure as failure:
            record = _run_record(
                scenario=scenario,
                tutor=tutor,
                identity=identity,
                run_id=run_id,
                suite_id=suite_id,
                progress=collector,
                stop_reason="infrastructure_failure",
                infrastructure_failure=failure.kind,
                fixture_identities=fixture_identities,
                source_fixture_id=source_fixture_id,
                source_fixture_sha256=source_fixture_sha256,
            )
            _write_record(destination, record)
            return record

        if not tutor_turn.completed:
            raise RuntimeError("tutor returned an incomplete turn")
        tutor_turns.append(tutor_turn)
        collector.turns.append(
            TurnRecord(
                number=len(collector.turns) + 1,
                learner=pending,
                tutor=tutor_turn.text,
            )
        )
        if pending_is_learner_response:
            learner_responses.append(pending)
            collector.learner_response_count = len(learner_responses)

        decision = evaluator.decide(
            EvaluatorContext(
                scenario=scenario,
                tutor_turns=tuple(tutor_turns),
                learner_responses=tuple(learner_responses),
            )
        )
        if decision.action == "stop":
            if (
                decision.stop_reason not in _MANUAL_STOP_REASONS
                or decision.response is not None
            ):
                raise ValueError("evaluator returned an invalid stop decision")
            record = _run_record(
                scenario=scenario,
                tutor=tutor,
                identity=identity,
                run_id=run_id,
                suite_id=suite_id,
                progress=collector,
                stop_reason=decision.stop_reason,
                infrastructure_failure=None,
                fixture_identities=fixture_identities,
                source_fixture_id=source_fixture_id,
                source_fixture_sha256=source_fixture_sha256,
            )
            _write_record(destination, record)
            return record

        if (
            decision.action != "respond"
            or decision.stop_reason is not None
            or decision.response is None
            or not decision.response.strip()
        ):
            raise ValueError("evaluator returned an invalid response decision")
        if len(learner_responses) >= min(
            scenario.max_learner_responses,
            MAX_LEARNER_RESPONSES,
        ):
            record = _run_record(
                scenario=scenario,
                tutor=tutor,
                identity=identity,
                run_id=run_id,
                suite_id=suite_id,
                progress=collector,
                stop_reason="maximum_learner_responses",
                infrastructure_failure=None,
                fixture_identities=fixture_identities,
                source_fixture_id=source_fixture_id,
                source_fixture_sha256=source_fixture_sha256,
            )
            _write_record(destination, record)
            return record

        pending = decision.response
        pending_is_learner_response = True


def infrastructure_record(
    *,
    scenario: Scenario,
    identity: ProtocolIdentity,
    run_id: str,
    suite_id: str,
    runtime_version: str,
    model_identifier: str,
    kind: Literal["authentication", "quota", "network", "runtime", "timeout"],
    progress: SessionProgress,
    fixture_identities: FixtureIdentities,
    source_fixture_id: str | None = None,
    source_fixture_sha256: str | None = None,
) -> dict[str, JsonValue]:
    """Build plain schema data without arbitrary exception or provider text."""
    return {
        "schema_version": RUN_WRITE_SCHEMA_VERSION,
        "run_id": run_id,
        "suite_id": suite_id,
        "scenario_id": scenario.identifier,
        "repository_commit": identity.repository_commit,
        "protocol_version": identity.protocol_version,
        "protocol_sha256": identity.bundle_sha256,
        "runtime": "antigravity",
        "runtime_version": runtime_version,
        "model_identifier": model_identifier,
        "learner_response_count": progress.learner_response_count,
        "stop_reason": "infrastructure_failure",
        "infrastructure_failure": kind,
        "turns": [asdict(turn) for turn in progress.turns],
        "scenario_sha256": fixture_identities.scenario_sha256,
        "rubric_sha256": fixture_identities.rubric_sha256,
        "suite_sha256": fixture_identities.suite_sha256,
        "source_fixture_id": source_fixture_id,
        "source_fixture_sha256": source_fixture_sha256,
    }


def _save_failure_evidence(
    *,
    layout: RunLayout,
    record_path: Path,
    error: BaseException,
    progress: SessionProgress,
    phase: Literal["start", "session"],
    scenario: Scenario,
    identity: ProtocolIdentity,
    run_id: str,
    suite_id: str,
    model_identifier: str,
    runtime_version: str,
    fixture_identities: FixtureIdentities,
    source_fixture_id: str | None = None,
    source_fixture_sha256: str | None = None,
) -> None:
    kind: FailureKind = (
        error.kind if isinstance(error, InfrastructureFailure) else "runtime"
    )
    if not record_path.exists():
        document = infrastructure_record(
            scenario=scenario,
            identity=identity,
            run_id=run_id,
            suite_id=suite_id,
            runtime_version=runtime_version,
            model_identifier=model_identifier,
            kind=kind,
            progress=progress,
            fixture_identities=fixture_identities,
            source_fixture_id=source_fixture_id,
            source_fixture_sha256=source_fixture_sha256,
        )
        write_private(
            record_path,
            canonical_json(document),
            private_root=layout.run_dir,
        )
    failure_path = layout.run_dir / "failure.json"
    if not failure_path.exists():
        write_private(
            failure_path,
            canonical_json(
                {
                    "exception_type": type(error).__name__,
                    "phase": phase,
                }
            ),
            private_root=layout.run_dir,
        )


def execute_isolated_run(
    layout: RunLayout,
    repository: Path,
    suite_id: str,
    scenario: Scenario,
    tutor_factory: Callable[[RunLayout], TutorSession],
    evaluator: ConsoleEvaluator,
    identity: ProtocolIdentity,
    run_id: str,
    *,
    fixture_identities: FixtureIdentities,
    model_identifier: str,
    runtime_version: str,
) -> RunRecord:
    """Execute, save evidence, and independently attempt every cleanup step."""
    progress = SessionProgress(turns=[], learner_response_count=0)
    record_path = layout.run_dir / "run-record.json"
    tutor: TutorSession | None = None
    started = False
    primary: BaseException | None = None
    sourced = None
    try:
        if scenario.source_fixture_id is not None:
            sourced = prepare_sourced_study(repository, layout, scenario)
        tutor = tutor_factory(layout)
        tutor.start()  # type: ignore[attr-defined]
        started = True
        bootstrap = initial_bootstrap(
            layout.protocol,
            scenario.initial_goal,
            sourced.source_study_payload if sourced is not None else None,
        )
        return run_session(
            scenario,
            tutor,
            evaluator,
            identity,
            bootstrap,
            run_id,
            fixture_identities=fixture_identities,
            record_path=record_path,
            progress=progress,
            source_fixture_id=sourced.fixture_id if sourced is not None else None,
            source_fixture_sha256=sourced.fixture_sha256 if sourced is not None else None,
        )
    except BaseException as error:
        primary = error
        try:
            _save_failure_evidence(
                layout=layout,
                record_path=record_path,
                error=error,
                progress=progress,
                phase="session" if started else "start",
                scenario=scenario,
                identity=identity,
                run_id=run_id,
                suite_id=suite_id,
                model_identifier=model_identifier,
                runtime_version=runtime_version,
                fixture_identities=fixture_identities,
                source_fixture_id=(
                    sourced.fixture_id if sourced is not None else None
                ),
                source_fixture_sha256=(
                    sourced.fixture_sha256 if sourced is not None else None
                ),
            )
        except BaseException as evidence_error:
            error.add_note(
                "failure evidence save failed: "
                f"{type(evidence_error).__name__}"
            )
        raise
    finally:
        failed_steps: list[str] = []
        cleanup_primary: BaseException | None = None
        cleanup_failures: list[tuple[str, str]] = []
        preserve_runtime = False
        if sourced is not None:
            try:
                cleanup_sourced_study(sourced)
            except BaseException as cleanup_error:
                if primary is not None:
                    primary.add_note(
                        "source fixture cleanup failed: "
                        f"{type(cleanup_error).__name__}"
                    )
        steps: tuple[tuple[str, Callable[[], object]], ...] = (
            (
                "close",
                lambda: tutor.close() if tutor is not None else None,  # type: ignore[attr-defined]
            ),
            ("snapshot", lambda: snapshot_learner_records(layout)),
            (
                "remove-runtime",
                lambda: remove_runtime_root(layout, repository),
            ),
        )
        for name, step in steps:
            try:
                step()
            except BaseException as cleanup_error:
                failed_steps.append(name)
                cleanup_failures.append((name, type(cleanup_error).__name__))
                if name == "close" and isinstance(
                    cleanup_error,
                    ProcessCleanupError,
                ):
                    preserve_runtime = True
                    if primary is not None:
                        try:
                            setattr(primary, "_preserve_semantic_runtime", True)
                        except Exception:
                            pass
                if primary is not None:
                    primary.add_note(
                        f"cleanup step {name} failed: "
                        f"{type(cleanup_error).__name__}"
                    )
                elif cleanup_primary is not None:
                    cleanup_primary.add_note(
                        f"cleanup step {name} failed: "
                        f"{type(cleanup_error).__name__}"
                    )
                elif not isinstance(cleanup_error, Exception):
                    cleanup_primary = cleanup_error
                    for failed_name, failure_type in cleanup_failures:
                        cleanup_primary.add_note(
                            f"cleanup step {failed_name} failed: {failure_type}"
                        )
            if preserve_runtime:
                break
        if cleanup_primary is not None:
            raise cleanup_primary
        if failed_steps and primary is None:
            raise RuntimeCleanupError(
                failed_steps,
                preserve_runtime=preserve_runtime,
            ) from None


def _contains(parent: Path, candidate: Path) -> bool:
    try:
        return os.path.commonpath(
            (
                os.path.normcase(os.fspath(parent)),
                os.path.normcase(os.fspath(candidate)),
            )
        ) == os.path.normcase(os.fspath(parent))
    except ValueError:
        return False


def verify_run_isolation(run_dir: Path, repository: Path) -> None:
    """Verify private isolation evidence without exposing its path values."""
    context = load_runtime_context(run_dir)
    repository_root = Path(repository).absolute().resolve(strict=True)
    runtime_root = context.runtime_root.absolute().resolve(strict=False)
    if _contains(repository_root, runtime_root) or _contains(
        runtime_root,
        repository_root,
    ):
        raise ValueError("recorded runtime root is not outside the repository")
    if os.path.lexists(runtime_root):
        raise ValueError("recorded runtime root still exists")

    disclosure = context.rule_disclosure
    if disclosure.boundary not in ("user_home", "filesystem_root"):
        raise ValueError("runtime rule boundary is invalid")
    if any(
        item not in USER_HOME_RULE_PATHS
        for item in disclosure.user_home_rule_paths
    ):
        raise ValueError("runtime user-home rule disclosure is invalid")
    if any(
        marker.levels_above_home < 1 or marker.marker not in RULE_MARKERS
        for marker in disclosure.above_home_markers
    ):
        raise ValueError("runtime above-home rule disclosure is invalid")

    record_path = Path(run_dir) / "run-record.json"
    if not record_path.is_file():
        raise ValueError("run record is unavailable")
    load_run_record(record_path)
