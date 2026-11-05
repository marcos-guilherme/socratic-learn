"""Deterministic construction of the universal tutor distribution."""

from __future__ import annotations

import os
import re
import tempfile
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
    r"^### ([a-z0-9]+(?:-[a-z0-9]+)*) — (\S.*)$",
    re.MULTILINE,
)


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


def _read_sources(root: Path) -> list[tuple[str, bytes]]:
    sources: list[tuple[str, bytes]] = []
    for relative in CANONICAL_SOURCES:
        if not _is_relative_source(relative):
            raise IntegrityError(
                "canonical source paths must be relative POSIX paths",
                path=relative,
            )
        path = root / relative
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
            ) from error
        sources.append((relative, _normalize_source(data, relative)))
    return sources


def _curriculum_index(relative: str, data: bytes) -> str:
    headings = _CURRICULUM_HEADING_RE.findall(data.decode("utf-8"))
    if not headings:
        raise IntegrityError(
            "curriculum source contains no node headings",
            path=relative,
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

    sources = _read_sources(root)
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
            temporary_path.unlink(missing_ok=True)
        raise FilesystemError("distribution artifact could not be written", path=path) from error


def write_distribution(root: Path, result: BuildResult) -> tuple[Path, Path]:
    """Atomically write exact build bytes under the repository's dist directory."""

    dist = root / "dist"
    try:
        dist.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FilesystemError("distribution directory could not be created", path=dist) from error
    bundle_path = dist / "learning-tutor.prompt.md"
    manifest_path = dist / "manifest.json"
    _atomic_write(bundle_path, result.bundle)
    _atomic_write(manifest_path, result.manifest)
    return bundle_path, manifest_path


def build(root: Path | None = None) -> BuildResult:
    """Build, write, and report the repository distribution."""

    repository = Path.cwd() if root is None else root
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
