"""Private command surface for manual semantic evaluation runs."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
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
    remove_runtime_root,
)
from evaluation.schema import (
    Scenario,
    StreamContract,
    fixture_root,
    load_scenario,
    load_stream_contract,
)
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
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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


def _scenario(repository: Path, identifier: str) -> Scenario:
    scenario_id = _identifier(identifier, "Scenario")
    path = repository / "evaluation" / "fixtures" / "scenarios" / (
        scenario_id + ".json"
    )
    try:
        loaded = load_scenario(path)
    except (OSError, UnicodeError, ValueError):
        raise CliRefusal("Unknown or invalid evaluation scenario.") from None
    if loaded.identifier != scenario_id:
        raise CliRefusal("Evaluation scenario identity does not match its file.")
    return loaded


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

    commands.add_parser("score")
    commands.add_parser("report")
    commands.add_parser("validate-report")
    return parser


def _run_command(
    args: argparse.Namespace,
    *,
    repository: Path,
    output: TextIO,
    run_process: RunProcess,
) -> int:
    suite_id = _identifier(args.suite_id, "Suite")
    selected_scenario = _scenario(repository, args.scenario)
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
            model_identifier=checked.model,
            runtime_version=checked.runtime_version,
        )
    except BaseException as primary:
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
