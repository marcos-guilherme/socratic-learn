"""Deterministic construction of the universal tutor distribution."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PRODUCT_ID, PROTOCOL_VERSION, TARGETS
from .conformance import (
    CONFORMANCE_CONTRACT_VERSION,
    REQUIRED_DIAGNOSTIC_CODES,
    check_conformance,
)
from .errors import FilesystemError, IntegrityError
from .manifest import (
    BUNDLE_NAME,
    CAPABILITY_FALLBACKS,
    SESSION_HEADINGS,
    serialize_json,
    sha256_bytes,
    validate_manifest,
)
from .safe_fs import (
    ParentIdentity,
    POSIX_SAME_PRINCIPAL_LIMIT,
    TrackedDirectory,
    identity_bound_replace,
    path_identity,
    remove_tracked_tree,
    track_directory,
)


CANONICAL_SOURCES = (
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
)

_CURRICULUM_HEADING_RE = re.compile(
    r" {0,3}### ([a-z0-9]+(?:-[a-z0-9]+)*) — (\S.*)",
)
_LEVEL_THREE_ATX_RE = re.compile(r" {0,3}###(?:[ \t]|$)")


@dataclass(frozen=True)
class BuildResult:
    """Exact bytes produced by one distribution build."""

    bundle: bytes
    manifest: bytes


def _is_relative_source(path: str) -> bool:
    posix = PurePosixPath(path)
    windows = PureWindowsPath(path)
    return (
        bool(path)
        and "\\" not in path
        and not posix.is_absolute()
        and not windows.is_absolute()
        and windows.drive == ""
        and ".." not in posix.parts
        and path == posix.as_posix()
    )


def _normalize_source(data: bytes, relative: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IntegrityError(
            "source is not valid UTF-8",
            path=relative,
            remediation="save the source as UTF-8 and rebuild",
        ) from error

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return ("\n".join(lines) + "\n").encode("utf-8")


def _resolve_repository_root(root: Path) -> Path:
    try:
        repository = root.resolve(strict=True)
    except OSError as error:
        raise IntegrityError(
            "repository root cannot be resolved",
            path=root,
            remediation="use an existing repository directory",
        ) from error
    if not repository.is_dir():
        raise IntegrityError(
            "repository root is not a directory",
            path=root,
            remediation="use an existing repository directory",
        )
    return repository


def _ensure_contained(
    repository: Path,
    candidate: Path,
    *,
    display_path: str | Path,
) -> Path:
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as error:
        raise IntegrityError(
            "path cannot be resolved safely",
            path=display_path,
            remediation="remove invalid links and retry",
        ) from error
    if not resolved.is_relative_to(repository):
        raise IntegrityError(
            "path resolves outside the repository",
            path=display_path,
            remediation="remove the escaping symlink or choose a path inside the repository",
        )
    return resolved


def _dist_path(repository: Path) -> Path:
    dist = repository / "dist"
    if dist.is_symlink():
        raise IntegrityError(
            "distribution directory must not be a symlink",
            path="dist",
            remediation="remove the dist symlink and rebuild",
        )
    _ensure_contained(repository, dist, display_path="dist")
    if dist.exists() and not dist.is_dir():
        raise IntegrityError(
            "distribution path is not a directory",
            path="dist",
            remediation="move the existing path and rebuild",
        )
    return dist


def _read_sources(root: Path) -> list[tuple[str, bytes]]:
    sources: list[tuple[str, bytes]] = []
    for relative in CANONICAL_SOURCES:
        if not _is_relative_source(relative):
            raise IntegrityError(
                "canonical source paths must be relative POSIX paths",
                path=relative,
            )
        path = _ensure_contained(
            root,
            root / relative,
            display_path=relative,
        )
        try:
            data = path.read_bytes()
        except FileNotFoundError as error:
            raise IntegrityError(
                "required canonical source is missing",
                path=relative,
                remediation="restore the source and rebuild",
            ) from error
        except OSError as error:
            raise FilesystemError(
                "canonical source could not be read",
                path=relative,
                remediation="check source permissions and rebuild",
            ) from error
        sources.append((relative, _normalize_source(data, relative)))
    return sources


def _curriculum_index(relative: str, data: bytes) -> str:
    headings: list[tuple[str, str]] = []
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if _LEVEL_THREE_ATX_RE.match(line) is None:
            continue
        match = _CURRICULUM_HEADING_RE.fullmatch(line)
        if match is None:
            raise IntegrityError(
                "unsupported or malformed curriculum node heading",
                path=f"{relative}:{line_number}",
                remediation="use '### identifier — Title' for every node heading",
            )
        headings.append((match.group(1), match.group(2)))
    if not headings:
        raise IntegrityError(
            "curriculum source contains no node headings",
            path=relative,
            remediation="add at least one '### identifier — Title' node heading",
        )
    return "\n".join(f"- {identifier} — {title}" for identifier, title in headings)


def _compose_bundle(sources: list[tuple[str, bytes]]) -> bytes:
    sections = [
        "# Socratic Learn",
        f"Protocol: {PROTOCOL_VERSION}",
        "",
        "Canonical sources (relative to the distribution repository):",
        *(f"- {relative}" for relative, _ in sources),
    ]
    for relative, data in sources:
        sections.extend(("", f"<!-- source:{relative} -->"))
        if relative.startswith("curricula/"):
            sections.extend(
                (
                    f"## Curriculum index: {relative}",
                    _curriculum_index(relative, data),
                )
            )
        else:
            sections.extend(
                (
                    f"## Canonical source: {relative}",
                    data.decode("utf-8").rstrip("\n"),
                )
            )
        sections.append(f"<!-- /source:{relative} -->")
    return ("\n".join(sections).rstrip("\n") + "\n").encode("utf-8")


def build_distribution(root: Path) -> BuildResult:
    """Build deterministic bundle and manifest bytes without writing them."""

    repository = _resolve_repository_root(root)
    sources = _read_sources(repository)
    bundle = _compose_bundle(sources)
    diagnostics = check_conformance(bundle.decode("utf-8"))
    if diagnostics:
        details = "; ".join(
            f"{diagnostic.code} ({diagnostic.path}): {diagnostic.message}"
            for diagnostic in diagnostics
        )
        remediation = "; ".join(
            f"{diagnostic.code}: {diagnostic.remediation}"
            for diagnostic in diagnostics
        )
        raise IntegrityError(
            f"bundle behavioral conformance failed: {details}",
            path=f"dist/{BUNDLE_NAME}",
            remediation=remediation,
        )
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": PRODUCT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "language": "en",
        "targets": list(TARGETS),
        "sources": [
            {"path": relative, "sha256": sha256_bytes(data)}
            for relative, data in sources
        ],
        "bundle": {
            "path": BUNDLE_NAME,
            "sha256": sha256_bytes(bundle),
        },
        "capability_fallbacks": dict(CAPABILITY_FALLBACKS),
        "conformance": {
            "version": CONFORMANCE_CONTRACT_VERSION,
            "required_diagnostic_codes": list(REQUIRED_DIAGNOSTIC_CODES),
        },
        "session_headings": list(SESSION_HEADINGS),
    }
    validate_manifest(manifest)
    return BuildResult(bundle=bundle, manifest=serialize_json(manifest))


def _atomic_write(
    path: Path,
    data: bytes,
    *,
    root: Path | None = None,
    temporary_directory: Path | None = None,
    expected_destination_chain: tuple[ParentIdentity, ...] | None = None,
) -> None:
    temporary_path: Path | None = None
    temporary_identity = None
    mutation_root = path.parent if root is None else root
    temporary_parent = path.parent if temporary_directory is None else temporary_directory
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=temporary_parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
            temporary_identity = path_identity(temporary_path)
        identity_bound_replace(
            temporary_path,
            path,
            root=mutation_root,
            expected_source=temporary_identity,
            expected_destination_chain=expected_destination_chain,
        )
    except OSError as error:
        raise FilesystemError(
            "distribution artifact could not be written",
            path=path,
            remediation=(
                "check destination permissions and retry; preserve any reported "
                f"temporary path for recovery: {temporary_path}"
            ),
        ) from error


def _validate_staged_distribution(stage: Path, result: BuildResult) -> None:
    try:
        manifest_bytes = (stage / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        bundle_bytes = (stage / BUNDLE_NAME).read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(
            "staged distribution cannot be read and validated",
            path=stage,
            remediation="retry the build after checking repository permissions",
        ) from error
    if not isinstance(manifest, dict):
        raise IntegrityError(
            "staged manifest must contain a JSON object",
            path=stage / "manifest.json",
            remediation="regenerate the distribution",
        )
    validate_manifest(manifest)
    if manifest_bytes != result.manifest:
        raise IntegrityError(
            "staged manifest bytes differ from the build result",
            path=stage / "manifest.json",
            remediation="retry the build",
        )
    if bundle_bytes != result.bundle or sha256_bytes(bundle_bytes) != manifest["bundle"]["sha256"]:
        raise IntegrityError(
            "staged prompt bytes do not match the manifest",
            path=stage / BUNDLE_NAME,
            remediation="retry the build",
        )


def _fully_owned_dist_tree(dist: Path) -> TrackedDirectory | None:
    """Return an identity snapshot only for the exact deterministic dist tree."""

    try:
        names = {entry.name for entry in os.scandir(dist)}
        if names != {"manifest.json", BUNDLE_NAME}:
            return None
        manifest_bytes = (dist / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        if not isinstance(manifest, dict):
            return None
        validate_manifest(manifest)
        bundle = manifest["bundle"]
        if not isinstance(bundle, dict) or bundle["path"] != BUNDLE_NAME:
            return None
        bundle_bytes = (dist / BUNDLE_NAME).read_bytes()
        if sha256_bytes(bundle_bytes) != bundle["sha256"]:
            return None
        return track_directory(dist)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, IntegrityError):
        return None


def write_distribution(root: Path, result: BuildResult) -> tuple[Path, Path]:
    """Stage, validate, and replace the complete distribution with rollback."""

    repository = _resolve_repository_root(root)
    dist = _dist_path(repository)
    stage: Path | None = None
    stage_directory: TrackedDirectory | None = None
    backup = repository / f".dist-backup-{uuid.uuid4().hex}"
    backup_directory: TrackedDirectory | None = None
    backup_fully_owned = False
    old_moved = False
    committed = False
    try:
        stage = Path(tempfile.mkdtemp(prefix=".dist-stage-", dir=repository))
        stage_directory = track_directory(stage)
        _atomic_write(stage / BUNDLE_NAME, result.bundle)
        stage_directory = track_directory(stage)
        _atomic_write(stage / "manifest.json", result.manifest)
        stage_directory = track_directory(stage)
        _validate_staged_distribution(stage, result)

        if dist.exists():
            try:
                tracked_dist = track_directory(dist)
            except OSError as error:
                raise FilesystemError(
                    "existing distribution could not be safely tracked and was "
                    "preserved without mutation",
                    path=dist,
                    remediation=(
                        f"inspect and preserve {dist}; remove any symlink/reparse "
                        "point or unsupported entry only after establishing "
                        "ownership, then rebuild"
                    ),
                ) from error
            owned_dist = _fully_owned_dist_tree(dist)
            identity_bound_replace(
                dist,
                backup,
                root=repository,
                expected_source=tracked_dist.identity,
            )
            old_moved = True
            backup_directory = TrackedDirectory(
                backup,
                tracked_dist.identity,
                tracked_dist.entries,
            )
            owned_at_tracking = (
                owned_dist is not None and owned_dist == tracked_dist
            )
            try:
                # Re-capture verifies no child changed between proof and move.
                backup_fully_owned = (
                    owned_at_tracking
                    and track_directory(backup) == backup_directory
                )
            except OSError:
                backup_fully_owned = False
        assert stage_directory is not None
        identity_bound_replace(
            stage,
            dist,
            root=repository,
            expected_source=stage_directory.identity,
        )
        committed = True
        stage = None
    except OSError as error:
        if old_moved:
            if dist.exists() or dist.is_symlink():
                raise FilesystemError(
                    "distribution swap failed with an ambiguous destination; "
                    "reported recovery paths retained their verified identities; "
                    f"{POSIX_SAME_PRINCIPAL_LIMIT}",
                    path=dist,
                    remediation=(
                        f"preserve and inspect {dist} and {backup}; restore the old "
                        "distribution only after establishing ownership"
                    ),
                ) from error
            try:
                if backup_directory is None:
                    raise FilesystemError(
                        "distribution swap failed after the old directory moved, "
                        "but its backup could not be tracked; the backup was "
                        "preserved",
                        path=backup,
                        remediation=(
                            f"preserve and inspect {backup}; restore it to {dist} "
                            "only after establishing ownership of every entry"
                        ),
                    ) from error
                identity_bound_replace(
                    backup,
                    dist,
                    root=repository,
                    expected_source=backup_directory.identity,
                )
                old_moved = False
            except OSError as rollback_error:
                raise FilesystemError(
                    "distribution swap failed and the old directory could not be "
                    f"restored; {POSIX_SAME_PRINCIPAL_LIMIT}",
                    path=dist,
                    remediation=f"restore the old distribution from {backup.name}",
                ) from rollback_error
        raise FilesystemError(
            "distribution swap or staged artifact write failed; verified recovery "
            f"state was retained where identifiable; {POSIX_SAME_PRINCIPAL_LIMIT}",
            path=dist,
            remediation=(
                "check repository permissions and rebuild; preserve any reported "
                "staging or backup path for recovery"
            ),
        ) from error
    finally:
        cleanup_targets: list[TrackedDirectory] = []
        if stage is not None and stage_directory is not None:
            cleanup_targets.append(stage_directory)
        if committed and backup_directory is not None and backup_fully_owned:
            cleanup_targets.append(backup_directory)
        for directory in cleanup_targets:
            if not directory.path.exists() and not directory.path.is_symlink():
                continue
            try:
                remove_tracked_tree(directory)
            except OSError as cleanup_error:
                raise FilesystemError(
                    "distribution state committed or reported recovery paths "
                    "retained their verified identities, but temporary cleanup "
                    f"was unsafe; {POSIX_SAME_PRINCIPAL_LIMIT}",
                    path=directory.path,
                    remediation=(
                        f"preserve and inspect {directory.path}; remove it only after "
                        "confirming its recorded operation ownership"
                    ),
                ) from cleanup_error
        if committed and backup_directory is not None and not backup_fully_owned:
            raise FilesystemError(
                "distribution committed, but the previous distribution backup "
                "was not fully owned and was preserved",
                path=backup_directory.path,
                remediation=(
                    f"inspect {backup_directory.path}; remove it only after "
                    "establishing ownership of every entry"
                ),
            )

    bundle_path = dist / BUNDLE_NAME
    manifest_path = dist / "manifest.json"
    return bundle_path, manifest_path


def build(root: Path | None = None) -> BuildResult:
    """Build, write, and report the repository distribution."""

    repository = _resolve_repository_root(Path.cwd() if root is None else root)
    result = build_distribution(repository)
    bundle_path, manifest_path = write_distribution(repository, result)
    report = (
        f"{bundle_path.relative_to(repository).as_posix()} "
        f"{sha256_bytes(result.bundle)}\n"
        f"{manifest_path.relative_to(repository).as_posix()} "
        f"{sha256_bytes(result.manifest)}\n"
    )
    try:
        sys.stdout.write(report)
        sys.stdout.flush()
    except OSError as error:
        raise FilesystemError(
            "distribution report could not be written to standard output",
            path="<stdout>",
            remediation="redirect standard output to a writable destination and retry",
        ) from error
    return result
