"""Generic project-local installation with receipts and transactional updates."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION
from .errors import CollisionError, FilesystemError, IntegrityError, UsageError
from .manifest import serialize_json, sha256_bytes, validate_manifest


INSTALL_ROOT = ".learning-tutor"
RECEIPT_PATH = f"{INSTALL_ROOT}/install.json"
OWNED_PATHS = (
    f"{INSTALL_ROOT}/manifest.json",
    f"{INSTALL_ROOT}/learning-tutor.prompt.md",
    RECEIPT_PATH,
    f"{INSTALL_ROOT}/loader.md",
    f"{INSTALL_ROOT}/.gitignore",
    f"{INSTALL_ROOT}/workspace/.gitkeep",
)
_RECEIPT_KEYS = {
    "schema_version",
    "protocol_version",
    "target",
    "owned_paths",
    "hashes",
}
_HASHED_PATHS = tuple(path for path in OWNED_PATHS if path != RECEIPT_PATH)
_IGNORE_BYTES = b"workspace/*\n!workspace/.gitkeep\n"


@dataclass(frozen=True)
class PlannedFile:
    """One exact managed file in an installation plan."""

    path: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class InstallReceipt:
    """Validated ownership metadata used to authorize an update."""

    schema_version: int
    protocol_version: str
    target: str
    owned_paths: tuple[str, ...]
    hashes: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "target": self.target,
            "owned_paths": list(self.owned_paths),
            "hashes": dict(self.hashes),
        }


@dataclass(frozen=True)
class InstallPlan:
    """A side-effect-free description of a generic install or update."""

    source_root: Path
    project: Path
    target: str
    update: bool
    files: tuple[PlannedFile, ...]
    previous_receipt: InstallReceipt | None = None
    expected_existing: tuple[tuple[str, str], ...] = ()


def _portable_relative_path(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and windows.drive == ""
        and ".." not in posix.parts
        and value == posix.as_posix()
    )


def _resolve_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise IntegrityError(
            f"{label} does not exist or cannot be resolved",
            path=path,
            remediation=f"use an existing {label} directory",
        ) from error
    if not resolved.is_dir():
        raise IntegrityError(
            f"{label} is not a directory",
            path=path,
            remediation=f"use an existing {label} directory",
        )
    return resolved


def _project_path(project: Path, relative: str) -> Path:
    if not _portable_relative_path(relative):
        raise IntegrityError(
            "receipt path must be a control-free relative POSIX path",
            path=relative,
            remediation="remove the invalid receipt and reinstall",
        )
    candidate = project.joinpath(*PurePosixPath(relative).parts)
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise IntegrityError(
            "managed path cannot be resolved safely",
            path=relative,
            remediation="remove invalid links and retry",
        ) from error
    if not resolved.is_relative_to(project):
        raise IntegrityError(
            "managed path resolves outside the project",
            path=relative,
            remediation="remove the escaping link and retry",
        )
    current = project
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise IntegrityError(
                "managed path must not contain symbolic links",
                path=relative,
                remediation="replace the link with a regular project-local path",
            )
    return candidate


def _read_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as error:
        raise IntegrityError(
            f"{label} is missing",
            path=path,
            remediation="restore the file or perform a clean install",
        ) from error
    except OSError as error:
        raise FilesystemError(
            f"{label} could not be read",
            path=path,
            remediation="check path permissions and retry",
        ) from error


def _load_distribution(source_root: Path) -> tuple[bytes, bytes]:
    manifest_path = source_root / "dist/manifest.json"
    manifest_bytes = _read_bytes(manifest_path, "distribution manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(
            "distribution manifest is not valid UTF-8 JSON",
            path=manifest_path,
            remediation="run 'learning-tutor build'",
        ) from error
    if not isinstance(manifest, dict):
        raise IntegrityError(
            "distribution manifest must contain a JSON object",
            path=manifest_path,
            remediation="run 'learning-tutor build'",
        )
    validate_manifest(manifest)
    bundle = manifest["bundle"]
    assert isinstance(bundle, dict)
    bundle_path = source_root / "dist" / str(bundle["path"])
    bundle_bytes = _read_bytes(bundle_path, "distribution prompt")
    if sha256_bytes(bundle_bytes) != bundle["sha256"]:
        raise IntegrityError(
            "distribution prompt hash does not match the manifest",
            path=bundle_path,
            remediation="run 'learning-tutor build'",
        )
    return manifest_bytes, bundle_bytes


def _parse_receipt(value: object, path: Path) -> InstallReceipt:
    if not isinstance(value, Mapping):
        raise IntegrityError(
            "installation receipt must contain a JSON object",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    if set(value) != _RECEIPT_KEYS:
        raise IntegrityError(
            "installation receipt has missing or unknown properties",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    if value["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise IntegrityError(
            "installation receipt schema version is unsupported",
            path=path,
            remediation="install with a compatible learning-tutor version",
        )
    protocol = value["protocol_version"]
    if type(protocol) is not str or not protocol:
        raise IntegrityError(
            "installation receipt protocol version is invalid",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    if value["target"] != "generic":
        raise IntegrityError(
            "installation receipt target must be generic",
            path=path,
            remediation="use the installer matching the recorded target",
        )
    owned_value = value["owned_paths"]
    if (
        type(owned_value) is not list
        or not owned_value
        or any(not _portable_relative_path(item) for item in owned_value)
        or len(set(owned_value)) != len(owned_value)
        or RECEIPT_PATH not in owned_value
    ):
        raise IntegrityError(
            "installation receipt owned paths are invalid",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    hashes_value = value["hashes"]
    if not isinstance(hashes_value, Mapping):
        raise IntegrityError(
            "installation receipt hashes must contain a JSON object",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    expected_hash_paths = set(owned_value) - {RECEIPT_PATH}
    if set(hashes_value) != expected_hash_paths:
        raise IntegrityError(
            "installation receipt must hash every owned path except itself",
            path=path,
            remediation="remove the invalid installation and reinstall",
        )
    hashes: list[tuple[str, str]] = []
    for relative in owned_value:
        if relative == RECEIPT_PATH:
            continue
        digest = hashes_value.get(relative)
        if (
            type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise IntegrityError(
                "installation receipt contains an invalid SHA-256 hash",
                path=relative,
                remediation="remove the invalid installation and reinstall",
            )
        hashes.append((relative, digest))
    return InstallReceipt(
        schema_version=MANIFEST_SCHEMA_VERSION,
        protocol_version=protocol,
        target="generic",
        owned_paths=tuple(owned_value),
        hashes=tuple(hashes),
    )


def _read_receipt(project: Path) -> tuple[InstallReceipt, bytes]:
    receipt_path = _project_path(project, RECEIPT_PATH)
    receipt_bytes = _read_bytes(receipt_path, "installation receipt")
    try:
        value = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(
            "installation receipt is not valid UTF-8 JSON",
            path=receipt_path,
            remediation="remove the invalid installation and reinstall",
        ) from error
    return _parse_receipt(value, receipt_path), receipt_bytes


def load_receipt(project: Path) -> dict[str, object]:
    """Load and validate project installation metadata without mutation."""

    resolved_project = _resolve_directory(project, "project")
    receipt, _ = _read_receipt(resolved_project)
    return receipt.as_dict()


def _verify_owned_files(
    project: Path,
    receipt: InstallReceipt,
    receipt_bytes: bytes,
) -> tuple[tuple[str, str], ...]:
    hashes = dict(receipt.hashes)
    expected: list[tuple[str, str]] = []
    for relative in receipt.owned_paths:
        path = _project_path(project, relative)
        content = _read_bytes(path, "owned installation file")
        digest = sha256_bytes(content)
        if relative != RECEIPT_PATH and digest != hashes[relative]:
            raise IntegrityError(
                "owned installation file was modified",
                path=relative,
                remediation="restore the installed file or perform a clean install",
            )
        expected.append((relative, digest))
    if sha256_bytes(receipt_bytes) != dict(expected)[RECEIPT_PATH]:
        raise AssertionError("receipt snapshot changed while it was read")
    return tuple(expected)


def _loader_bytes() -> bytes:
    loader_path = Path(__file__).parent / "templates/generic-loader.md"
    data = _read_bytes(loader_path, "generic loader template")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IntegrityError(
            "generic loader template is not valid UTF-8",
            path=loader_path,
            remediation="reinstall the learning-tutor package",
        ) from error
    return (text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n").encode()


def _planned_files(manifest: bytes, bundle: bytes) -> tuple[PlannedFile, ...]:
    content_by_path = {
        f"{INSTALL_ROOT}/manifest.json": manifest,
        f"{INSTALL_ROOT}/learning-tutor.prompt.md": bundle,
        f"{INSTALL_ROOT}/loader.md": _loader_bytes(),
        f"{INSTALL_ROOT}/.gitignore": _IGNORE_BYTES,
        f"{INSTALL_ROOT}/workspace/.gitkeep": b"",
    }
    hashes = {
        relative: sha256_bytes(content_by_path[relative])
        for relative in _HASHED_PATHS
    }
    receipt = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "target": "generic",
        "owned_paths": list(OWNED_PATHS),
        "hashes": hashes,
    }
    content_by_path[RECEIPT_PATH] = serialize_json(receipt)
    return tuple(
        PlannedFile(
            path=relative,
            content=content_by_path[relative],
            sha256=sha256_bytes(content_by_path[relative]),
        )
        for relative in OWNED_PATHS
    )


def plan_install(
    source_root: Path,
    project: Path,
    target: str,
    update: bool,
) -> InstallPlan:
    """Validate and construct an installation plan without filesystem mutation."""

    if target != "generic":
        raise UsageError(
            f"target '{target}' is not implemented by the generic installer",
            remediation="use target 'generic'",
        )
    source = _resolve_directory(source_root, "source root")
    destination = _resolve_directory(project, "project")
    install_root = destination / INSTALL_ROOT
    if not update:
        if install_root.exists() or install_root.is_symlink():
            raise CollisionError(
                "installation path already exists",
                path=install_root,
                remediation="use --update for an intact managed installation",
            )
        previous_receipt = None
        expected_existing: tuple[tuple[str, str], ...] = ()
    else:
        if not install_root.is_dir() or install_root.is_symlink():
            raise IntegrityError(
                "managed installation directory is missing or invalid",
                path=install_root,
                remediation="restore the installation or perform a clean install",
            )
        previous_receipt, receipt_bytes = _read_receipt(destination)
        expected_existing = _verify_owned_files(
            destination,
            previous_receipt,
            receipt_bytes,
        )
    manifest, bundle = _load_distribution(source)
    files = _planned_files(manifest, bundle)
    if update:
        assert previous_receipt is not None
        owned = set(previous_receipt.owned_paths)
        for planned in files:
            path = _project_path(destination, planned.path)
            if planned.path not in owned and (path.exists() or path.is_symlink()):
                raise CollisionError(
                    "update target is not owned by the installation receipt",
                    path=planned.path,
                    remediation="move the unowned path and retry",
                )
    return InstallPlan(
        source_root=source,
        project=destination,
        target="generic",
        update=update,
        files=files,
        previous_receipt=previous_receipt,
        expected_existing=expected_existing,
    )


def _write_staged_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _verify_plan_still_safe(plan: InstallPlan) -> None:
    if not plan.update:
        target = plan.project / INSTALL_ROOT
        if target.exists() or target.is_symlink():
            raise CollisionError(
                "installation path appeared after planning",
                path=target,
                remediation="inspect the new path and retry planning",
            )
        return
    for relative, expected_hash in plan.expected_existing:
        path = _project_path(plan.project, relative)
        content = _read_bytes(path, "owned installation file")
        if sha256_bytes(content) != expected_hash:
            raise IntegrityError(
                "owned installation file changed after planning",
                path=relative,
                remediation="restore the file and create a new update plan",
            )
    assert plan.previous_receipt is not None
    owned = set(plan.previous_receipt.owned_paths)
    for planned in plan.files:
        path = _project_path(plan.project, planned.path)
        if planned.path not in owned and (path.exists() or path.is_symlink()):
            raise CollisionError(
                "unowned update target appeared after planning",
                path=planned.path,
                remediation="move the unowned path and create a new update plan",
            )


def _stage(plan: InstallPlan) -> tuple[Path, Path]:
    try:
        stage = Path(
            tempfile.mkdtemp(prefix=".learning-tutor-stage-", dir=plan.project)
        )
        staged_install = stage / INSTALL_ROOT
        for planned in plan.files:
            relative_inside = PurePosixPath(planned.path).relative_to(INSTALL_ROOT)
            staged_path = staged_install.joinpath(*relative_inside.parts)
            _write_staged_file(staged_path, planned.content)
        for planned in plan.files:
            relative_inside = PurePosixPath(planned.path).relative_to(INSTALL_ROOT)
            staged_path = staged_install.joinpath(*relative_inside.parts)
            if sha256_bytes(staged_path.read_bytes()) != planned.sha256:
                raise IntegrityError(
                    "staged file hash does not match the installation plan",
                    path=planned.path,
                    remediation="check the filesystem and retry",
                )
        return stage, staged_install
    except (OSError, FilesystemError) as error:
        if "stage" in locals():
            shutil.rmtree(stage, ignore_errors=True)
        if isinstance(error, FilesystemError):
            raise
        raise FilesystemError(
            "installation staging failed",
            path=plan.project,
            remediation="check project permissions and retry",
        ) from error


def _apply_initial(plan: InstallPlan, stage: Path, staged_install: Path) -> None:
    target = plan.project / INSTALL_ROOT
    created_root = False
    try:
        target.mkdir()
        created_root = True
        for planned in plan.files:
            relative_inside = PurePosixPath(planned.path).relative_to(INSTALL_ROOT)
            source = staged_install.joinpath(*relative_inside.parts)
            destination = _project_path(plan.project, planned.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
    except OSError as error:
        if created_root:
            shutil.rmtree(target, ignore_errors=True)
        raise FilesystemError(
            "installation commit failed",
            path=target,
            remediation="check for a new path or permission problem and retry",
        ) from error
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _rollback_update(
    plan: InstallPlan,
    backup: Path,
    installed: list[str],
    backed_up: list[str],
) -> OSError | None:
    try:
        for relative in reversed(installed):
            target = _project_path(plan.project, relative)
            target.unlink(missing_ok=True)
        for relative in reversed(backed_up):
            source = backup.joinpath(*PurePosixPath(relative).parts)
            target = _project_path(plan.project, relative)
            os.replace(source, target)
    except OSError as error:
        return error
    return None


def _apply_update(plan: InstallPlan, stage: Path, staged_install: Path) -> None:
    backup: Path | None = None
    backed_up: list[str] = []
    installed: list[str] = []
    try:
        backup = Path(
            tempfile.mkdtemp(prefix=".learning-tutor-backup-", dir=plan.project)
        )
        assert plan.previous_receipt is not None
        replacement_paths = {planned.path for planned in plan.files}
        for relative in plan.previous_receipt.owned_paths:
            if relative not in replacement_paths:
                continue
            source = _project_path(plan.project, relative)
            destination = backup.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            backed_up.append(relative)
        for planned in plan.files:
            relative_inside = PurePosixPath(planned.path).relative_to(INSTALL_ROOT)
            source = staged_install.joinpath(*relative_inside.parts)
            destination = _project_path(plan.project, planned.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            installed.append(planned.path)
    except OSError as error:
        if backup is None:
            raise FilesystemError(
                "update backup could not be created",
                path=plan.project,
                remediation="check project permissions and retry",
            ) from error
        rollback_error = _rollback_update(plan, backup, installed, backed_up)
        if rollback_error is not None:
            raise FilesystemError(
                "update failed and rollback could not restore every owned file",
                path=plan.project / INSTALL_ROOT,
                remediation=f"restore managed files from {backup.name}",
            ) from rollback_error
        shutil.rmtree(backup, ignore_errors=True)
        raise FilesystemError(
            "update failed; the previous installation was restored",
            path=plan.project / INSTALL_ROOT,
            remediation="check project permissions and retry",
        ) from error
    else:
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def apply_install(plan: InstallPlan) -> None:
    """Apply a validated plan transactionally."""

    _verify_plan_still_safe(plan)
    stage, staged_install = _stage(plan)
    if plan.update:
        _apply_update(plan, stage, staged_install)
    else:
        _apply_initial(plan, stage, staged_install)


def install(
    target: str,
    project: Path,
    *,
    update: bool = False,
    source_root: Path | None = None,
) -> None:
    """Plan, apply, and report a generic installation."""

    plan = plan_install(
        Path.cwd() if source_root is None else source_root,
        project,
        target,
        update,
    )
    previous_protocol = (
        plan.previous_receipt.protocol_version
        if plan.previous_receipt is not None
        else None
    )
    apply_install(plan)
    loader = next(file.content for file in plan.files if file.path.endswith("/loader.md"))
    report = loader.decode("utf-8")
    if update:
        report += f"Protocol: {previous_protocol} -> {PROTOCOL_VERSION}\n"
    try:
        sys.stdout.write(report)
        sys.stdout.flush()
    except OSError as error:
        raise FilesystemError(
            "installation report could not be written to standard output",
            path="<stdout>",
            remediation="inspect the installed loader directly",
        ) from error
