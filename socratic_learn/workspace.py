"""Private personal and project-local learning workspace preparation."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .errors import IntegrityError
from .install import RECEIPT_PATH, apply_install, load_receipt, plan_install
from .resources import packaged_distribution_root, resource_bytes


_RECORD_TEMPLATES = (
    "learner-profile.md",
    "learning-goal.md",
    "progress.md",
)


@dataclass(frozen=True)
class LearningWorkspace:
    root: Path
    protocol: Path
    records: Path


def launcher_home(environ: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    override = environment.get("SOCRATIC_LEARN_HOME")
    return Path(override) if override else Path.home() / ".socratic-learn"


def _require_directory(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise IntegrityError(
            f"{label} must not be a symbolic link",
            path=path,
            remediation=f"use a regular {label} directory",
        )
    if not path.is_dir():
        raise IntegrityError(
            f"{label} is not a directory",
            path=path,
            remediation=f"use a regular {label} directory",
        )
    return path.resolve()


def _create_home(home: Path) -> Path:
    if home.exists() or home.is_symlink():
        return _require_directory(home, "launcher home")
    try:
        home.mkdir()
    except OSError as error:
        raise IntegrityError(
            "launcher home could not be created",
            path=home,
            remediation="choose a writable launcher home directory",
        ) from error
    return _require_directory(home, "launcher home")


def _create_record(path: Path, content: bytes) -> None:
    if _existing_record_is_valid(path):
        return
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if _existing_record_is_valid(path):
            return
        raise IntegrityError(
            "private learning record changed while it was created",
            path=path,
            remediation="inspect the conflicting record path and retry",
        )
    except OSError as error:
        raise IntegrityError(
            "private learning record could not be created",
            path=path,
            remediation="check the workspace permissions and retry",
        ) from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def _existing_record_is_valid(path: Path) -> bool:
    try:
        status = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise IntegrityError(
            "private learning record could not be inspected",
            path=path,
            remediation="check the record path and retry",
        ) from error
    if not stat.S_ISREG(status.st_mode):
        raise IntegrityError(
            "existing private learning record must be a regular file",
            path=path,
            remediation="move the conflicting path and retry",
        )
    return True


def _validate_existing_records(records: Path) -> None:
    if not records.exists() and not records.is_symlink():
        return
    if records.is_symlink() or not records.is_dir():
        raise IntegrityError(
            "private records path is not a regular directory",
            path=records,
            remediation="restore the managed workspace directory and retry",
        )
    for name in _RECORD_TEMPLATES:
        _existing_record_is_valid(records / name)


def _prepare_records(records: Path) -> None:
    if records.is_symlink() or not records.is_dir():
        raise IntegrityError(
            "private records path is not a regular directory",
            path=records,
            remediation="restore the managed workspace directory and retry",
        )
    for name in _RECORD_TEMPLATES:
        _create_record(records / name, resource_bytes(f"templates/{name}"))
    sessions = records / "sessions"
    try:
        sessions.mkdir(exist_ok=True)
    except OSError as error:
        raise IntegrityError(
            "session records directory could not be created",
            path=sessions,
            remediation="check the workspace permissions and retry",
        ) from error
    _require_directory(sessions, "session records")


def _prepare_workspace(project: Path) -> LearningWorkspace:
    destination = _require_directory(project, "project")
    records = destination / ".socratic-learn/workspace"
    _validate_existing_records(records)
    receipt_path = destination.joinpath(*RECEIPT_PATH.split("/"))
    update = receipt_path.exists() or receipt_path.is_symlink()
    target = str(load_receipt(destination)["target"]) if update else "generic"
    with packaged_distribution_root() as source:
        plan = plan_install(source, destination, target, update=update)
        apply_install(plan)
    _prepare_records(records)
    return LearningWorkspace(
        root=destination,
        protocol=destination / ".socratic-learn/socratic-learn.prompt.md",
        records=records,
    )


def prepare_personal_workspace(home: Path) -> LearningWorkspace:
    launcher_root = _create_home(home)
    project = launcher_root / "learning"
    try:
        project.mkdir(exist_ok=True)
    except OSError as error:
        raise IntegrityError(
            "personal learning directory could not be created",
            path=project,
            remediation="check the launcher home permissions and retry",
        ) from error
    return _prepare_workspace(project)


def prepare_here_workspace(project: Path) -> LearningWorkspace:
    return _prepare_workspace(project)
