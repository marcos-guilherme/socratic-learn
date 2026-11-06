"""Generic project-local installation with receipts and transactional updates."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION, TARGETS
from .errors import (
    CollisionError,
    FilesystemError,
    IntegrityError,
    LearningTutorError,
    UsageError,
)
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
_NATIVE_SKILL_PATHS = {
    "cursor": ".cursor/skills/learning-tutor/SKILL.md",
    "pi": ".pi/skills/learning-tutor/SKILL.md",
}
_RECEIPT_KEYS = {
    "schema_version",
    "protocol_version",
    "target",
    "owned_paths",
    "hashes",
}
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
    emitted_snippet: str | None = None


@dataclass(frozen=True)
class PathIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class CreatedDirectory:
    path: Path
    identity: PathIdentity


@dataclass(frozen=True)
class LinkedFile:
    path: Path
    identity: PathIdentity
    project: Path
    parent_chain: tuple[ParentIdentity, ...]


@dataclass(frozen=True)
class ParentIdentity:
    path: Path
    identity: PathIdentity


@dataclass(frozen=True)
class BackupFile:
    relative: str
    path: Path
    identity: PathIdentity


@dataclass(frozen=True)
class RecoveryConflict:
    path: Path
    backup: Path | None = None


class _PublicationFailure(FilesystemError):
    """A failure after a destination link may have been published."""

    def __init__(self, *args: object, published_path: Path, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.published_path = published_path


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
    target = value["target"]
    if target not in TARGETS:
        raise IntegrityError(
            "installation receipt target is unsupported",
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
        target=target,
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


def _template_bytes(name: str, path_base: str = "") -> bytes:
    template_path = Path(__file__).parent / f"templates/{name}"
    data = _read_bytes(template_path, f"{name} template")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IntegrityError(
            f"{name} template is not valid UTF-8",
            path=template_path,
            remediation="reinstall the learning-tutor package",
        ) from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    rendered = normalized.replace("{{PATH_BASE}}", path_base)
    return (rendered.rstrip("\n") + "\n").encode()


def _planned_files(
    manifest: bytes,
    bundle: bytes,
    target: str,
    *,
    include_claude_loader: bool,
) -> tuple[PlannedFile, ...]:
    content_by_path = {
        f"{INSTALL_ROOT}/manifest.json": manifest,
        f"{INSTALL_ROOT}/learning-tutor.prompt.md": bundle,
        f"{INSTALL_ROOT}/loader.md": _template_bytes("generic-loader.md"),
        f"{INSTALL_ROOT}/.gitignore": _IGNORE_BYTES,
        f"{INSTALL_ROOT}/workspace/.gitkeep": b"",
    }
    owned_paths = list(OWNED_PATHS)
    if target in _NATIVE_SKILL_PATHS:
        native_path = _NATIVE_SKILL_PATHS[target]
        content_by_path[native_path] = _template_bytes(
            f"{target}-skill.md",
            "../../../",
        )
        owned_paths.append(native_path)
    elif target == "claude-code" and include_claude_loader:
        content_by_path["CLAUDE.md"] = _template_bytes("claude-loader.md")
        owned_paths.append("CLAUDE.md")
    hashed_paths = tuple(path for path in owned_paths if path != RECEIPT_PATH)
    hashes = {
        relative: sha256_bytes(content_by_path[relative])
        for relative in hashed_paths
    }
    receipt = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "target": target,
        "owned_paths": owned_paths,
        "hashes": hashes,
    }
    content_by_path[RECEIPT_PATH] = serialize_json(receipt)
    return tuple(
        PlannedFile(
            path=relative,
            content=content_by_path[relative],
            sha256=sha256_bytes(content_by_path[relative]),
        )
        for relative in owned_paths
    )


def _claude_snippet() -> str:
    return _template_bytes("claude-loader.md").decode("utf-8")


def _check_native_destination(project: Path, target: str) -> None:
    skill_path = _NATIVE_SKILL_PATHS.get(target)
    if skill_path is None:
        return
    parts = PurePosixPath(skill_path).parts
    current = project
    for index, part in enumerate(parts[:-1]):
        current /= part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise CollisionError(
                    "native skill destination is blocked by an existing path",
                    path=current,
                    remediation="move the existing path and retry",
                )
            if index == len(parts) - 2:
                raise CollisionError(
                    "native skill destination directory already exists",
                    path=current,
                    remediation="move the existing directory and retry",
                )


def _check_initial_destinations(project: Path, target: str, files: tuple[PlannedFile, ...]) -> None:
    install_root = project / INSTALL_ROOT
    if install_root.exists() or install_root.is_symlink():
        raise CollisionError(
            "installation path already exists",
            path=install_root,
            remediation="use --update for an intact managed installation",
        )
    _check_native_destination(project, target)
    if target == "claude-code" and any(file.path == "CLAUDE.md" for file in files):
        claude_path = project / "CLAUDE.md"
        if claude_path.exists() or claude_path.is_symlink():
            raise CollisionError(
                "Claude loader path appeared during planning",
                path=claude_path,
                remediation="preserve the existing file and create a new plan",
            )


def plan_install(
    source_root: Path,
    project: Path,
    target: str,
    update: bool,
) -> InstallPlan:
    """Validate and construct an installation plan without filesystem mutation."""

    if target not in TARGETS:
        raise UsageError(
            f"target '{target}' is unsupported",
            remediation=f"use one of: {', '.join(TARGETS)}",
        )
    source = _resolve_directory(source_root, "source root")
    destination = _resolve_directory(project, "project")
    install_root = destination / INSTALL_ROOT
    emitted_snippet: str | None = None
    include_claude_loader = target == "claude-code"
    claude_path = destination / "CLAUDE.md"
    if target == "claude-code" and (claude_path.exists() or claude_path.is_symlink()):
        if claude_path.is_symlink() or not claude_path.is_file():
            raise CollisionError(
                "Claude root path must be a regular file",
                path=claude_path,
                remediation="move the conflicting path and retry",
            )
        include_claude_loader = False
        emitted_snippet = _claude_snippet()
    if not update:
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
        if previous_receipt.target != target:
            raise IntegrityError(
                "installation receipt target does not match the requested target",
                path=RECEIPT_PATH,
                remediation=f"use target '{previous_receipt.target}' for this installation",
            )
        expected_existing = _verify_owned_files(
            destination,
            previous_receipt,
            receipt_bytes,
        )
        if target == "claude-code" and "CLAUDE.md" in previous_receipt.owned_paths:
            include_claude_loader = True
            emitted_snippet = None
    manifest, bundle = _load_distribution(source)
    files = _planned_files(
        manifest,
        bundle,
        target,
        include_claude_loader=include_claude_loader,
    )
    if not update:
        _check_initial_destinations(destination, target, files)
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
        target=target,
        update=update,
        files=files,
        previous_receipt=previous_receipt,
        expected_existing=expected_existing,
        emitted_snippet=emitted_snippet,
    )


def _write_staged_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _remove_created_tree(path: Path) -> None:
    """Remove one operation-created tree, surfacing Windows lock failures."""

    shutil.rmtree(path)


def _cleanup_created_trees(paths: list[Path]) -> list[tuple[Path, OSError]]:
    failures: list[tuple[Path, OSError]] = []
    for path in paths:
        try:
            if path.exists() or path.is_symlink():
                _remove_created_tree(path)
        except OSError as error:
            failures.append((path, error))
    return failures


def _combined_cleanup_error(
    context: str,
    cleanup_failures: list[tuple[Path, OSError]],
    *,
    original: BaseException | None = None,
) -> FilesystemError:
    cleanup_details = "; ".join(
        f"{path}: {type(error).__name__}: {error}"
        for path, error in cleanup_failures
    )
    original_detail = (
        ""
        if original is None
        else f"; original failure: {type(original).__name__}: {original}"
    )
    recovery_paths = ", ".join(str(path) for path, _ in cleanup_failures)
    return FilesystemError(
        f"{context}{original_detail}; cleanup failure: {cleanup_details}",
        path=cleanup_failures[0][0],
        remediation=(
            f"preserve and inspect the recovery path(s): {recovery_paths}; "
            "remove only those operation-created paths after releasing locks"
        ),
    )


def _ensure_parent_directories(
    path: Path,
    *,
    stop: Path,
    created: list[CreatedDirectory],
) -> None:
    missing: list[Path] = []
    parent = path.parent
    while parent != stop and not parent.exists():
        if not parent.is_relative_to(stop):
            raise IntegrityError(
                "managed parent path escapes the installation root",
                path=parent,
                remediation="create a new update plan",
            )
        missing.append(parent)
        parent = parent.parent
    if parent.is_symlink() or not parent.is_dir():
        raise IntegrityError(
            "managed parent path changed during commit",
            path=parent,
            remediation="remove the conflicting path and retry",
        )
    for directory in reversed(missing):
        try:
            directory.mkdir()
        except FileExistsError as error:
            if directory.is_symlink() or not directory.is_dir():
                raise IntegrityError(
                    "managed parent path changed during commit",
                    path=directory,
                    remediation="remove the conflicting path and retry",
                ) from error
        else:
            created.append(
                CreatedDirectory(directory, _path_identity(directory))
            )


def _path_identity(path: Path) -> PathIdentity:
    status = path.stat(follow_symlinks=False)
    return PathIdentity(status.st_dev, status.st_ino)


def _has_identity(path: Path, identity: PathIdentity) -> bool:
    try:
        return _path_identity(path) == identity
    except OSError:
        return False


def _status_identity(status: os.stat_result) -> PathIdentity:
    return PathIdentity(status.st_dev, status.st_ino)


def _is_reparse_or_symlink(status: os.stat_result) -> bool:
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def _capture_parent_chain(
    project: Path,
    destination: Path,
) -> tuple[ParentIdentity, ...]:
    try:
        relative_parent = destination.parent.relative_to(project)
    except ValueError as error:
        raise IntegrityError(
            "publication parent escapes the project",
            path=destination.parent,
            remediation="create a new installation plan",
        ) from error
    chain: list[ParentIdentity] = []
    current = project
    for part in (".", *relative_parent.parts):
        if part != ".":
            current = current / part
        try:
            status = current.stat(follow_symlinks=False)
        except OSError as error:
            raise IntegrityError(
                "publication parent chain cannot be read",
                path=current,
                remediation="preserve the changed path and create a new plan",
            ) from error
        if _is_reparse_or_symlink(status) or not stat.S_ISDIR(status.st_mode):
            raise IntegrityError(
                "publication parent chain contains a symlink, reparse point, or non-directory",
                path=current,
                remediation="preserve the changed path and create a new plan",
            )
        chain.append(ParentIdentity(current, _status_identity(status)))
    return tuple(chain)


def _verify_parent_chain(
    project: Path,
    destination: Path,
    expected: tuple[ParentIdentity, ...],
) -> None:
    if _capture_parent_chain(project, destination) != expected:
        raise IntegrityError(
            "publication parent chain identity changed",
            path=destination.parent,
            remediation="preserve the changed tree and create a new plan",
        )


def _before_link_publication(source: Path, destination: Path) -> None:
    """Narrow transaction-boundary hook for race testing."""


def _after_link_publication(source: Path, destination: Path) -> None:
    """Narrow transaction-boundary hook for race testing."""


def _supports_bound_parent_operations() -> bool:
    return (
        os.link in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.link in os.supports_follow_symlinks
        and os.stat in os.supports_follow_symlinks
        and hasattr(os, "O_DIRECTORY")
    )


def _open_verified_parent(parent: ParentIdentity) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(parent.path, flags)
    if _status_identity(os.fstat(descriptor)) != parent.identity:
        os.close(descriptor)
        raise IntegrityError(
            "publication parent changed while opening its directory handle",
            path=parent.path,
            remediation="preserve the changed tree and create a new plan",
        )
    return descriptor


def _parent_chain_publication_error(
    destination: Path,
    *,
    original_parent: ParentIdentity,
    published: bool,
    original: BaseException,
) -> FilesystemError:
    error_type = _PublicationFailure if published else FilesystemError
    arguments: dict[str, object] = {}
    if published:
        arguments["published_path"] = destination
    return error_type(
        (
            "publication parent chain changed before commit completed; "
            "published state was preserved and no external data was deleted; "
            f"original parent identity "
            f"({original_parent.identity.device}, {original_parent.identity.inode}); "
            f"original failure: {type(original).__name__}: {original}"
        ),
        path=destination,
        remediation=(
            f"inspect {destination.parent} and {destination}; do not remove either "
            "unless its identity and ownership are established; if the original "
            "parent was renamed, locate the reported device/inode before cleanup"
        ),
        **arguments,
    )


def _link_staged_file(source: Path, destination: Path) -> LinkedFile:
    """Atomically publish a staged file without replacing any existing path."""

    project = Path(os.path.commonpath((source, destination)))
    parent_chain = _capture_parent_chain(project, destination)
    identity = _path_identity(source)
    parent_descriptor: int | None = None
    if _supports_bound_parent_operations():
        parent_descriptor = _open_verified_parent(parent_chain[-1])
    try:
        _before_link_publication(source, destination)
        _verify_parent_chain(project, destination, parent_chain)
    except (LearningTutorError, OSError) as error:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise _parent_chain_publication_error(
            destination,
            original_parent=parent_chain[-1],
            published=False,
            original=error,
        ) from error
    try:
        if parent_descriptor is None:
            os.link(source, destination)
        else:
            os.link(
                source,
                destination.name,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
    except FileExistsError as error:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise CollisionError(
            "installation destination appeared after planning",
            path=destination,
            remediation="preserve the new path and create a new installation plan",
        ) from error
    except OSError as error:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise FilesystemError(
            "staged file could not be linked to its destination",
            path=destination,
            remediation="check destination permissions and retry",
        ) from error
    try:
        _after_link_publication(source, destination)
        _verify_parent_chain(project, destination, parent_chain)
        if parent_descriptor is None:
            linked = (
                os.path.samefile(source, destination)
                and _has_identity(destination, identity)
            )
        else:
            linked = (
                _status_identity(
                    os.stat(
                        destination.name,
                        dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                )
                == identity
            )
        if not linked:
            raise IntegrityError(
                "linked destination identity changed",
                path=destination,
                remediation="preserve the destination and inspect it",
            )
    except (LearningTutorError, OSError) as error:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise _parent_chain_publication_error(
            destination,
            original_parent=parent_chain[-1],
            published=True,
            original=error,
        ) from error
    if parent_descriptor is not None:
        os.close(parent_descriptor)
    return LinkedFile(destination, identity, project, parent_chain)


def _prepare_destination_parent(
    plan: InstallPlan,
    planned: PlannedFile,
    *,
    created_directories: list[CreatedDirectory],
) -> None:
    destination = _project_path(plan.project, planned.path)
    previously_owned = (
        plan.previous_receipt is not None
        and planned.path in plan.previous_receipt.owned_paths
    )
    if (
        planned.path == _NATIVE_SKILL_PATHS.get(plan.target)
        and not previously_owned
    ):
        native_directory = destination.parent
        _ensure_parent_directories(
            native_directory,
            stop=plan.project,
            created=created_directories,
        )
        try:
            native_directory.mkdir()
        except FileExistsError as error:
            raise CollisionError(
                "native skill destination directory appeared after planning",
                path=native_directory,
                remediation="preserve the new directory and create a new plan",
            ) from error
        created_directories.append(
            CreatedDirectory(
                native_directory,
                _path_identity(native_directory),
            )
        )
    else:
        _ensure_parent_directories(
            destination,
            stop=plan.project,
            created=created_directories,
        )


def _expected_existing_hashes(plan: InstallPlan) -> dict[str, str]:
    return dict(plan.expected_existing)


def _ordered_publication_files(plan: InstallPlan) -> tuple[PlannedFile, ...]:
    target = plan.project / INSTALL_ROOT
    external = [
        planned
        for planned in plan.files
        if not _project_path(plan.project, planned.path).is_relative_to(target)
    ]
    internal = [
        planned
        for planned in plan.files
        if _project_path(plan.project, planned.path).is_relative_to(target)
        and planned.path != RECEIPT_PATH
    ]
    receipt = [planned for planned in plan.files if planned.path == RECEIPT_PATH]
    return tuple((*external, *internal, *receipt))


def _published_paths(
    linked_files: list[LinkedFile],
    created_directories: list[CreatedDirectory],
    *,
    extra: Path | None = None,
) -> list[Path]:
    paths = [created.path for created in created_directories]
    paths.extend(linked.path for linked in linked_files)
    if extra is not None:
        paths.append(extra)
    return list(dict.fromkeys(paths))


def _conservative_failure_error(
    context: str,
    *,
    original: BaseException,
    published: list[Path],
    stage: Path,
    backup: Path | None = None,
    conflicts: list[RecoveryConflict] | None = None,
) -> FilesystemError:
    recovery_paths = [*published, stage]
    if backup is not None:
        recovery_paths.append(backup)
    for conflict in conflicts or []:
        recovery_paths.append(conflict.path)
        if conflict.backup is not None:
            recovery_paths.append(conflict.backup)
    recovery_paths = list(dict.fromkeys(recovery_paths))
    listed = ", ".join(str(path) for path in recovery_paths)
    return FilesystemError(
        (
            f"{context}; no external data was deleted; partial published paths "
            f"and private recovery artifacts were preserved: {listed}; "
            f"original failure: {type(original).__name__}: {original}"
        ),
        path=recovery_paths[0],
        remediation=(
            "do not rerun installation; inspect the listed paths, preserve private "
            "staging/backups, and run doctor after manual recovery"
        ),
    )


def _restore_backups_no_overwrite(
    plan: InstallPlan,
    backed_up: list[BackupFile],
) -> tuple[list[LinkedFile], list[RecoveryConflict]]:
    restored: list[LinkedFile] = []
    conflicts: list[RecoveryConflict] = []
    for backed in reversed(backed_up):
        target = _project_path(plan.project, backed.relative)
        if target.exists() or target.is_symlink():
            conflicts.append(RecoveryConflict(target, backed.path))
            continue
        try:
            restored.append(_link_staged_file(backed.path, target))
        except (LearningTutorError, OSError):
            conflicts.append(RecoveryConflict(target, backed.path))
    return restored, conflicts


def _verify_plan_still_safe(plan: InstallPlan) -> None:
    if not plan.update:
        _check_initial_destinations(plan.project, plan.target, plan.files)
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
    stage: Path | None = None
    try:
        stage = Path(
            tempfile.mkdtemp(prefix=".learning-tutor-stage-", dir=plan.project)
        )
        staged_install = stage / INSTALL_ROOT
        for planned in plan.files:
            staged_path = stage.joinpath(*PurePosixPath(planned.path).parts)
            _write_staged_file(staged_path, planned.content)
        for planned in plan.files:
            staged_path = stage.joinpath(*PurePosixPath(planned.path).parts)
            if sha256_bytes(staged_path.read_bytes()) != planned.sha256:
                raise IntegrityError(
                    "staged file hash does not match the installation plan",
                    path=planned.path,
                    remediation="check the filesystem and retry",
                )
        return stage, staged_install
    except (LearningTutorError, OSError) as error:
        cleanup_failures = (
            _cleanup_created_trees([stage]) if stage is not None else []
        )
        if cleanup_failures:
            raise _combined_cleanup_error(
                "installation staging and cleanup failed",
                cleanup_failures,
                original=error,
            ) from error
        if isinstance(error, LearningTutorError):
            raise
        raise FilesystemError(
            "installation staging failed",
            path=plan.project,
            remediation="check project permissions and retry",
        ) from error


def _apply_initial(plan: InstallPlan, stage: Path, staged_install: Path) -> None:
    target = plan.project / INSTALL_ROOT
    linked_files: list[LinkedFile] = []
    created_directories: list[CreatedDirectory] = []
    try:
        for planned in _ordered_publication_files(plan):
            destination = _project_path(plan.project, planned.path)
            target_recorded = any(
                created.path == target for created in created_directories
            )
            if destination.is_relative_to(target) and not target_recorded:
                try:
                    target.mkdir()
                except FileExistsError as error:
                    raise CollisionError(
                        "installation path appeared after staging",
                        path=target,
                        remediation=(
                            "preserve the new path and create a new installation plan"
                        ),
                    ) from error
                created_directories.append(
                    CreatedDirectory(target, _path_identity(target))
                )
            _prepare_destination_parent(
                plan,
                planned,
                created_directories=created_directories,
            )
            source = stage.joinpath(*PurePosixPath(planned.path).parts)
            linked_files.append(_link_staged_file(source, destination))
    except (LearningTutorError, OSError) as error:
        extra = (
            error.published_path
            if isinstance(error, _PublicationFailure)
            else None
        )
        published = _published_paths(
            linked_files,
            created_directories,
            extra=extra,
        )
        if published:
            raise _conservative_failure_error(
                "initial installation failed after publication",
                original=error,
                published=published,
                stage=stage,
            ) from error
        cleanup_failures = _cleanup_created_trees([stage])
        if cleanup_failures:
            raise _combined_cleanup_error(
                "pre-publication installation and staging cleanup failed",
                cleanup_failures,
                original=error,
            ) from error
        if isinstance(error, LearningTutorError):
            raise
        raise FilesystemError(
            "installation failed before publication",
            path=target,
            remediation="check for a new path or permission problem and retry",
        ) from error
    cleanup_failures = _cleanup_created_trees([stage])
    if cleanup_failures:
        raise _combined_cleanup_error(
            "installation committed but staging cleanup failed",
            cleanup_failures,
        )


def _apply_update(plan: InstallPlan, stage: Path, staged_install: Path) -> None:
    backup: Path | None = None
    backed_up: list[BackupFile] = []
    linked_files: list[LinkedFile] = []
    created_directories: list[CreatedDirectory] = []
    try:
        backup = Path(
            tempfile.mkdtemp(prefix=".learning-tutor-backup-", dir=plan.project)
        )
        assert plan.previous_receipt is not None
        replacement_paths = {planned.path for planned in plan.files}
        expected_hashes = _expected_existing_hashes(plan)
        for relative in plan.previous_receipt.owned_paths:
            if relative not in replacement_paths:
                continue
            source = _project_path(plan.project, relative)
            destination = backup.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
            backed = BackupFile(
                relative,
                destination,
                _path_identity(destination),
            )
            backed_up.append(backed)
            if sha256_bytes(_read_bytes(destination, "backup file")) != expected_hashes[relative]:
                raise IntegrityError(
                    "backup bytes do not match the installation receipt",
                    path=relative,
                    remediation="restore the preserved backup before retrying",
                )
        for planned in _ordered_publication_files(plan):
            source = stage.joinpath(*PurePosixPath(planned.path).parts)
            destination = _project_path(plan.project, planned.path)
            _prepare_destination_parent(
                plan,
                planned,
                created_directories=created_directories,
            )
            linked_files.append(_link_staged_file(source, destination))
    except (LearningTutorError, OSError) as error:
        if backup is None:
            cleanup_failures = _cleanup_created_trees([stage])
            if cleanup_failures:
                raise _combined_cleanup_error(
                    "update backup creation and staging cleanup failed",
                    cleanup_failures,
                    original=error,
                ) from error
            raise FilesystemError(
                "update backup could not be created",
                path=plan.project,
                remediation="check project permissions and retry",
            ) from error
        extra = (
            error.published_path
            if isinstance(error, _PublicationFailure)
            else None
        )
        published = _published_paths(
            linked_files,
            created_directories,
            extra=extra,
        )
        restored, conflicts = _restore_backups_no_overwrite(
            plan,
            backed_up,
        )
        if published or conflicts:
            published.extend(linked.path for linked in restored)
            raise _conservative_failure_error(
                "update failed with preserved recovery state",
                original=error,
                published=list(dict.fromkeys(published)),
                stage=stage,
                backup=backup,
                conflicts=conflicts,
            ) from error
        cleanup_failures = _cleanup_created_trees([backup, stage])
        if cleanup_failures:
            raise _combined_cleanup_error(
                "pre-publication update restoration and cleanup failed",
                cleanup_failures,
                original=error,
            ) from error
        if isinstance(error, LearningTutorError):
            raise
        raise FilesystemError(
            (
                "update failed before publication; the previous installation was restored; "
                f"original failure: {type(error).__name__}: {error}"
            ),
            path=plan.project / INSTALL_ROOT,
            remediation="check project permissions and retry",
        ) from error
    cleanup_failures = _cleanup_created_trees([backup, stage])
    if cleanup_failures:
        raise _combined_cleanup_error(
            "update committed but temporary cleanup failed",
            cleanup_failures,
        )


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
    report = plan.emitted_snippet or next(
        file.content for file in plan.files if file.path.endswith("/loader.md")
    ).decode("utf-8")
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
