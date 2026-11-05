"""Deterministic construction of the universal tutor distribution."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION, TARGETS
from .errors import FilesystemError, IntegrityError
from .manifest import (
    CAPABILITY_FALLBACKS,
    SESSION_HEADINGS,
    serialize_json,
    sha256_bytes,
    validate_manifest,
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
        "# Universal Learning Tutor",
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
    manifest: dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "language": "en",
        "targets": list(TARGETS),
        "sources": [
            {"path": relative, "sha256": sha256_bytes(data)}
            for relative, data in sources
        ],
        "bundle": {
            "path": "learning-tutor.prompt.md",
            "sha256": sha256_bytes(bundle),
        },
        "capability_fallbacks": dict(CAPABILITY_FALLBACKS),
        "session_headings": list(SESSION_HEADINGS),
    }
    validate_manifest(manifest)
    return BuildResult(bundle=bundle, manifest=serialize_json(manifest))


def _atomic_write(path: Path, data: bytes) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise FilesystemError(
            "distribution artifact could not be written",
            path=path,
            remediation="check destination permissions and retry",
        ) from error


def _validate_staged_distribution(stage: Path, result: BuildResult) -> None:
    try:
        manifest_bytes = (stage / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        bundle_bytes = (stage / "learning-tutor.prompt.md").read_bytes()
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
            path=stage / "learning-tutor.prompt.md",
            remediation="retry the build",
        )


def write_distribution(root: Path, result: BuildResult) -> tuple[Path, Path]:
    """Stage, validate, and replace the complete distribution with rollback."""

    repository = _resolve_repository_root(root)
    dist = _dist_path(repository)
    stage: Path | None = None
    backup = repository / f".dist-backup-{uuid.uuid4().hex}"
    old_moved = False
    committed = False
    try:
        stage = Path(tempfile.mkdtemp(prefix=".dist-stage-", dir=repository))
        _atomic_write(stage / "learning-tutor.prompt.md", result.bundle)
        _atomic_write(stage / "manifest.json", result.manifest)
        _validate_staged_distribution(stage, result)

        if dist.exists():
            os.replace(dist, backup)
            old_moved = True
        os.replace(stage, dist)
        committed = True
        stage = None
    except OSError as error:
        if old_moved:
            try:
                os.replace(backup, dist)
                old_moved = False
            except OSError as rollback_error:
                raise FilesystemError(
                    "distribution swap failed and the old directory could not be restored",
                    path=dist,
                    remediation=f"restore the old distribution from {backup.name}",
                ) from rollback_error
        raise FilesystemError(
            "distribution swap or staged artifact write failed; old distribution restored",
            path=dist,
            remediation="check repository permissions and rebuild",
        ) from error
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if committed and backup.exists():
            shutil.rmtree(backup, ignore_errors=True)

    bundle_path = dist / "learning-tutor.prompt.md"
    manifest_path = dist / "manifest.json"
    return bundle_path, manifest_path


def build(root: Path | None = None) -> BuildResult:
    """Build, write, and report the repository distribution."""

    repository = _resolve_repository_root(Path.cwd() if root is None else root)
    result = build_distribution(repository)
    bundle_path, manifest_path = write_distribution(repository, result)
    print(
        f"{bundle_path.relative_to(repository).as_posix()} "
        f"{sha256_bytes(result.bundle)}"
    )
    print(
        f"{manifest_path.relative_to(repository).as_posix()} "
        f"{sha256_bytes(result.manifest)}"
    )
    return result
