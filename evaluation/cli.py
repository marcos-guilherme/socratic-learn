"""Private command surface for manual semantic evaluation runs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess
from typing import TextIO

from evaluation.antigravity import AntigravitySession
from evaluation.contract_capture import (
    ContractCaptureError,
    select_model,
    validate_fixture,
)
from evaluation.isolation import (
    ProtocolIdentity,
    assert_protocol_unchanged,
    capture_protocol_identity,
    create_run_layout,
    load_runtime_context,
    remove_runtime_root,
)
from evaluation.report import (
    ScenarioRuntimeDisclosure,
    finding_from_mapping,
    render_baseline_report,
    validate_baseline_report,
    validate_finding,
    write_sanitized_report,
)
from evaluation.sanitize import write_private
from evaluation.schema import (
    Finding,
    Rubric,
    RunRecord,
    Scenario,
    Scorecard,
    StreamContract,
    SuiteManifest,
    canonical_json,
    fixture_root,
    identities_for_scenario,
    load_scenario,
    load_rubric,
    load_run_record,
    load_stream_contract,
    load_suite_manifest,
    resolve_fixture_path,
    suite_manifest_path,
    validate_run_record,
)
from evaluation.scoring import interactive_score, scorecard_from_mapping
from evaluation.session import (
    ConsoleEvaluator,
    RuntimeCleanupError,
    execute_isolated_run,
    verify_run_isolation,
)


REPOSITORY = Path(__file__).resolve().parents[1]
EXPECTED_BRANCH = "feat/semantic-evaluation-runtime-ux"
BLOCKED_EXIT_CODE = 2
PREFLIGHT_TIMEOUT_SECONDS = 30.0
PRECHECK_REFUSAL_MESSAGE = "BLOCKED: Semantic evaluation precheck refused.\n"
RUN_FAILURE_MESSAGE = "BLOCKED: Semantic evaluation run failed.\n"
ISOLATION_FAILURE_MESSAGE = (
    "BLOCKED: Post-run isolation verification failed.\n"
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


class CliRefusal(ValueError):
    """A fixed, non-sensitive command refusal suitable for stderr."""


class _RunPhaseFailure(RuntimeError):
    """A private run failed; its original detail must not reach the console."""


class _IsolationVerificationFailure(RuntimeError):
    """Post-run isolation verification failed without exposing path details."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliRefusal("Invalid semantic evaluation command arguments.")


@dataclass(frozen=True)
class PreflightResult:
    model: str
    runtime_version: str
    contract: StreamContract
    identity: ProtocolIdentity


RunProcess = Callable[..., CompletedProcess[str]]


def _invoke(
    run_process: RunProcess,
    argv: tuple[str, ...],
    repository: Path,
) -> CompletedProcess[str]:
    try:
        return run_process(
            list(argv),
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=PREFLIGHT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise CliRefusal("Required preflight command timed out.") from None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise CliRefusal("Required preflight command could not be executed.") from None


def _successful(
    run_process: RunProcess,
    argv: tuple[str, ...],
    repository: Path,
    message: str,
) -> CompletedProcess[str]:
    result = _invoke(run_process, argv, repository)
    if result.returncode != 0:
        raise CliRefusal(message)
    return result


def _private_model_file(repository: Path, model_file: Path) -> Path:
    repository_root = repository.absolute().resolve(strict=True)
    raw_root = (repository_root / ".semantic-runs").resolve(strict=False)
    candidate = (
        model_file
        if model_file.is_absolute()
        else repository_root / model_file
    ).absolute().resolve(strict=False)
    try:
        candidate.relative_to(raw_root)
    except ValueError:
        raise CliRefusal("Model file must be private evaluation evidence.") from None
    if not candidate.is_file():
        raise CliRefusal("Validated model file is unavailable.")
    try:
        text = candidate.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise CliRefusal("Validated model file is unavailable.") from None
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0].strip() or lines[0] != lines[0].strip():
        raise CliRefusal("Validated model file must contain one exact identifier.")
    return candidate


def _preflight(
    repository: Path,
    model_file: Path,
    *,
    run_process: RunProcess = subprocess.run,
) -> PreflightResult:
    """Validate all live-run inputs without creating a run layout."""
    repository_root = repository.absolute().resolve(strict=True)
    branch = _successful(
        run_process,
        ("git", "branch", "--show-current"),
        repository_root,
        "Evaluation must run from the approved branch.",
    ).stdout.strip()
    if branch != EXPECTED_BRANCH:
        raise CliRefusal("Evaluation must run from the approved branch.")

    contract_path = fixture_root() / "antigravity" / "stream-contract.json"
    try:
        validate_fixture(contract_path)
        contract = load_stream_contract(contract_path)
    except (ContractCaptureError, ValueError, OSError, UnicodeError):
        raise CliRefusal("Antigravity contract fixture is invalid.") from None

    selected_path = _private_model_file(repository_root, Path(model_file))
    try:
        selected_model = selected_path.read_text(
            encoding="utf-8-sig"
        ).strip()
    except (OSError, UnicodeError):
        raise CliRefusal("Validated model file is unavailable.") from None
    if selected_model != contract.model_identifier:
        raise CliRefusal("Validated model does not match the captured contract.")

    models = _successful(
        run_process,
        ("agy", "models"),
        repository_root,
        "Antigravity model validation failed.",
    )
    try:
        select_model(models.stdout, selected_model)
    except ContractCaptureError:
        raise CliRefusal("Validated model is not currently available.") from None

    version = _successful(
        run_process,
        ("agy", "--version"),
        repository_root,
        "Antigravity version validation failed.",
    ).stdout.strip()
    if version != contract.antigravity_version:
        raise CliRefusal("Antigravity version differs from the captured contract.")

    identity = capture_protocol_identity(repository_root)
    assert_protocol_unchanged(identity, repository_root)

    _successful(
        run_process,
        ("git", "diff", "--exit-code", "--", "core", "dist"),
        repository_root,
        "Protocol files contain uncommitted changes.",
    )
    _successful(
        run_process,
        ("git", "check-ignore", "--quiet", ".semantic-runs/"),
        repository_root,
        "Private semantic run storage is not ignored.",
    )
    tracked = _successful(
        run_process,
        ("git", "ls-files", "--", ".semantic-runs"),
        repository_root,
        "Tracked semantic run check failed.",
    )
    if tracked.stdout.strip():
        raise CliRefusal("Private semantic run storage contains tracked files.")

    return PreflightResult(
        model=selected_model,
        runtime_version=version,
        contract=contract,
        identity=identity,
    )


def _identifier(value: str, label: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise CliRefusal(f"{label} must be a lowercase hyphenated identifier.")
    return value


def _scenario_fixture_path(repository: Path, identifier: str) -> Path:
    scenario_id = _identifier(identifier, "Scenario")
    root = (repository / "evaluation" / "fixtures").resolve(strict=False)
    path = (root / "scenarios" / f"{scenario_id}.json").resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        raise CliRefusal("Unknown or invalid evaluation scenario.") from None
    return path


def _scenario(repository: Path, identifier: str) -> Scenario:
    path = _scenario_fixture_path(repository, identifier)
    try:
        loaded = load_scenario(path)
    except (OSError, UnicodeError, ValueError):
        raise CliRefusal("Unknown or invalid evaluation scenario.") from None
    if loaded.identifier != _identifier(identifier, "Scenario"):
        raise CliRefusal("Evaluation scenario identity does not match its file.")
    return loaded


def _suite_manifest(suite_id: str) -> SuiteManifest:
    try:
        return load_suite_manifest(suite_manifest_path(suite_id))
    except (OSError, UnicodeError, ValueError):
        raise CliRefusal("Unknown or invalid evaluation suite.") from None


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="python -m evaluation.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--model-file", required=True)

    run = commands.add_parser("run")
    run.add_argument("--suite-id", required=True)
    run.add_argument("--scenario", required=True)
    run.add_argument("--model-file", required=True)

    verify = commands.add_parser("verify-isolation")
    verify.add_argument("--suite-id", required=True)
    verify.add_argument("--scenario", required=True)

    score = commands.add_parser("score")
    score.add_argument("--suite-id", required=True)

    report = commands.add_parser("report")
    report.add_argument("--suite-id", required=True)
    report.add_argument("--output", required=True)

    validate_report = commands.add_parser("validate-report")
    validate_report.add_argument("path")
    return parser


def _run_command(
    args: argparse.Namespace,
    *,
    repository: Path,
    output: TextIO,
    run_process: RunProcess,
) -> int:
    suite_id = _identifier(args.suite_id, "Suite")
    manifest = _suite_manifest(suite_id)
    selected_scenario = _scenario(repository, args.scenario)
    if selected_scenario.identifier not in manifest.scenario_ids:
        raise CliRefusal("Scenario is not part of the selected evaluation suite.")
    fixture_identities = identities_for_scenario(manifest, selected_scenario.identifier)
    expected_run_dir = (
        repository
        / ".semantic-runs"
        / suite_id
        / selected_scenario.identifier
    )
    if os.path.lexists(expected_run_dir):
        raise CliRefusal("Evaluation run already exists.")
    checked = _preflight(
        repository,
        Path(args.model_file),
        run_process=run_process,
    )
    run_id = f"{suite_id}-{selected_scenario.identifier}"

    layout = create_run_layout(
        repository,
        suite_id,
        selected_scenario.identifier,
    )
    try:
        execute_isolated_run(
            layout,
            repository,
            suite_id,
            selected_scenario,
            lambda active_layout: AntigravitySession(
                "agy",
                checked.model,
                active_layout,
                checked.contract,
                repository=repository,
                parent_environment=os.environ,
            ),
            ConsoleEvaluator(output=output),
            checked.identity,
            run_id,
            fixture_identities=fixture_identities,
            model_identifier=checked.model,
            runtime_version=checked.runtime_version,
        )
    except BaseException as primary:
        preserve_runtime = (
            isinstance(primary, RuntimeCleanupError)
            and primary.preserve_runtime
        ) or getattr(primary, "_preserve_semantic_runtime", False) is True
        if not preserve_runtime:
            try:
                remove_runtime_root(layout, repository)
            except BaseException as cleanup_error:
                primary.add_note(
                    "post-handoff runtime removal failed: "
                    f"{type(cleanup_error).__name__}"
                )
        if isinstance(primary, Exception):
            raise _RunPhaseFailure from None
        raise

    try:
        verify_run_isolation(layout.run_dir, repository)
    except Exception:
        raise _IsolationVerificationFailure from None
    output.write("Semantic evaluation session completed.\n")
    return 0


def _suite_directory(repository: Path, suite_id: str) -> Path:
    suite = repository / ".semantic-runs" / _identifier(suite_id, "Suite")
    if not suite.is_dir():
        raise CliRefusal("Evaluation suite is unavailable.")
    return suite


def _suite_records(
    suite: Path,
    rubric: Rubric | None = None,
) -> list[tuple[Path, RunRecord]]:
    records: list[tuple[Path, RunRecord]] = []
    for run_dir in sorted(suite.iterdir(), key=lambda path: path.name):
        record_path = run_dir / "run-record.json"
        if run_dir.is_dir() and record_path.is_file():
            record = load_run_record(record_path)
            if rubric is not None:
                validate_run_record(record, rubric)
            records.append((run_dir, record))
    if not records:
        raise CliRefusal("Evaluation suite has no run records.")
    if len({record.scenario_id for _, record in records}) != len(records):
        raise CliRefusal("Evaluation suite contains duplicate scenarios.")
    return records


def _load_json(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, value in pairs:
            if key in document:
                raise ValueError("duplicate JSON key")
            document[key] = value
        return document

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicates,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"invalid JSON constant: {value}")
        ),
    )


def _interactive_findings(records: Mapping[str, RunRecord]) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    while input("Add a finding? [y/N]: ").strip().lower() in {"y", "yes"}:
        finding = Finding(
            identifier=input("Finding identifier: ").strip(),
            classification=input("Classification: ").strip(),  # type: ignore[arg-type]
            scope=input("Scope (general or scenario-specific): ").strip(),  # type: ignore[arg-type]
            scenario_ids=tuple(
                item.strip()
                for item in input("Scenario IDs (comma-separated): ").split(",")
                if item.strip()
            ),
            evidence_turns=tuple(
                item.strip()
                for item in input("Evidence turns (scenario:turn, comma-separated): ").split(",")
                if item.strip()
            ),
            summary=input("Finding summary: "),
            research_links=tuple(
                item.strip()
                for item in input("Research links (comma-separated, blank for none): ").split(",")
                if item.strip()
            ),
        )
        validate_finding(finding, records)
        if any(item.identifier == finding.identifier for item in findings):
            raise ValueError("finding identifiers must be unique")
        findings.append(finding)
    return tuple(findings)


def _score_command(args: argparse.Namespace, *, repository: Path, output: TextIO) -> int:
    manifest = _suite_manifest(args.suite_id)
    suite = _suite_directory(repository, args.suite_id)
    rubric = load_rubric(
        resolve_fixture_path(
            manifest.rubric_path,
            label="suite manifest rubric_path",
        )
    )
    run_records = _suite_records(suite, rubric)
    records = {record.scenario_id: record for _, record in run_records}
    scorecards: list[tuple[Path, Scorecard]] = []
    for run_dir, record in run_records:
        if record.stop_reason == "infrastructure_failure" or record.infrastructure_failure:
            continue
        destination = run_dir / "scorecard.json"
        if destination.exists():
            raise CliRefusal("Evaluation scorecard already exists.")
        scorecards.append((destination, interactive_score(record, rubric)))
    findings_path = suite / "findings.json"
    if findings_path.exists():
        raise CliRefusal("Evaluation findings already exist.")
    findings = _interactive_findings(records)
    for destination, scorecard in scorecards:
        write_private(
            destination,
            canonical_json(asdict(scorecard)),
            private_root=destination.parent,
        )
    write_private(
        findings_path,
        canonical_json([asdict(finding) for finding in findings]),
        private_root=suite,
    )
    output.write("Semantic evaluation scoring completed.\n")
    return 0


def _tracked_report_path(repository: Path, supplied: str) -> Path:
    repository_root = repository.resolve(strict=True)
    reports_root = (repository_root / "evaluation" / "reports").resolve(strict=False)
    candidate = (
        Path(supplied)
        if Path(supplied).is_absolute()
        else repository_root / supplied
    ).resolve(strict=False)
    try:
        candidate.relative_to(reports_root)
    except ValueError:
        raise CliRefusal("Report path must be under evaluation/reports.") from None
    return candidate


def _report_command(args: argparse.Namespace, *, repository: Path, output: TextIO) -> int:
    manifest = _suite_manifest(args.suite_id)
    suite = _suite_directory(repository, args.suite_id)
    rubric = load_rubric(
        resolve_fixture_path(
            manifest.rubric_path,
            label="suite manifest rubric_path",
        )
    )
    run_records = _suite_records(suite, rubric)
    records = [record for _, record in run_records]
    records.sort(
        key=lambda record: manifest.scenario_ids.index(record.scenario_id),
    )
    records_by_scenario = {record.scenario_id: record for record in records}
    scorecards: list[Scorecard] = []
    disclosures: dict[str, ScenarioRuntimeDisclosure] = {}
    for run_dir, record in run_records:
        context = load_runtime_context(run_dir)
        disclosures[record.scenario_id] = ScenarioRuntimeDisclosure(
            scenario_id=record.scenario_id,
            local_rule_check_passed=context.local_rule_check_passed,
            rule_disclosure=context.rule_disclosure,
        )
        scorecard_path = run_dir / "scorecard.json"
        if scorecard_path.is_file():
            document = _load_json(scorecard_path)
            if not isinstance(document, dict):
                raise ValueError("scorecard must be a JSON object")
            scorecards.append(scorecard_from_mapping(document, rubric, record))

    findings_document = _load_json(suite / "findings.json")
    if not isinstance(findings_document, list):
        raise ValueError("findings must be a JSON array")
    findings: list[Finding] = []
    for item in findings_document:
        if not isinstance(item, dict):
            raise ValueError("finding must be a JSON object")
        findings.append(finding_from_mapping(item, records_by_scenario))

    text = render_baseline_report(
        manifest,
        rubric,
        records,
        scorecards,
        findings,
        runtime_disclosures=disclosures,
        rules=(),
    )
    write_sanitized_report(_tracked_report_path(repository, args.output), text)
    output.write("Semantic baseline report written.\n")
    return 0


def _validate_report_command(
    args: argparse.Namespace,
    *,
    repository: Path,
    output: TextIO,
) -> int:
    path = _tracked_report_path(repository, args.path)
    validate_baseline_report(path.read_text(encoding="utf-8"))
    output.write("Semantic baseline report is valid.\n")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
    error: TextIO = sys.stderr,
    run_process: RunProcess | None = None,
) -> int:
    runner = subprocess.run if run_process is None else run_process
    repository = REPOSITORY
    try:
        args = _parser().parse_args(argv)
        if args.command == "preflight":
            _preflight(
                repository,
                Path(args.model_file),
                run_process=runner,
            )
            output.write("Semantic evaluation preflight passed.\n")
            return 0
        if args.command == "run":
            return _run_command(
                args,
                repository=repository,
                output=output,
                run_process=runner,
            )
        if args.command == "verify-isolation":
            suite_id = _identifier(args.suite_id, "Suite")
            scenario_id = _identifier(args.scenario, "Scenario")
            try:
                verify_run_isolation(
                    repository
                    / ".semantic-runs"
                    / suite_id
                    / scenario_id,
                    repository,
                )
            except Exception:
                raise _IsolationVerificationFailure from None
            output.write("Runtime isolation verified.\n")
            return 0
        if args.command == "score":
            return _score_command(args, repository=repository, output=output)
        if args.command == "report":
            return _report_command(args, repository=repository, output=output)
        if args.command == "validate-report":
            return _validate_report_command(
                args,
                repository=repository,
                output=output,
            )
        error.write("BLOCKED: Command is not available until Task 8.\n")
        return BLOCKED_EXIT_CODE
    except _IsolationVerificationFailure:
        error.write(ISOLATION_FAILURE_MESSAGE)
        return BLOCKED_EXIT_CODE
    except _RunPhaseFailure:
        error.write(RUN_FAILURE_MESSAGE)
        return BLOCKED_EXIT_CODE
    except CliRefusal:
        error.write(PRECHECK_REFUSAL_MESSAGE)
        return BLOCKED_EXIT_CODE
    except (ContractCaptureError, FileExistsError, OSError, UnicodeError, ValueError):
        error.write(PRECHECK_REFUSAL_MESSAGE)
        return BLOCKED_EXIT_CODE
    except RuntimeCleanupError:
        error.write(RUN_FAILURE_MESSAGE)
        return BLOCKED_EXIT_CODE
    except Exception:
        error.write(RUN_FAILURE_MESSAGE)
        return BLOCKED_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
