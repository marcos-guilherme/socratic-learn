"""Deterministic manifest serialization and validation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION, TARGETS
from .errors import IntegrityError


SESSION_HEADINGS = (
    "## Outcome",
    "## Diagnostic evidence",
    "## Approved dependency path",
    "## Concepts established",
    "## Application evidence",
    "## Remaining gaps",
    "## Next step",
    "## Sources",
)

CAPABILITY_FALLBACKS = {
    "cross_session_memory": "Ask for a prior summary and state what is unknown.",
    "diagram_rendering": "Use Mermaid if available or a textual edge list.",
    "filesystem": "Return the complete session record as Markdown.",
    "structured_quiz": "Ask one question at a time in conversation.",
    "subagents": "Research and teach sequentially.",
    "web": "Mark volatile claims unverified and prefer stable content.",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for *data*."""

    return hashlib.sha256(data).hexdigest()


def serialize_json(value: object) -> bytes:
    """Serialize JSON with stable ordering, formatting, and termination."""

    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _is_relative_portable_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
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


def _require_hash(value: object, field: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise IntegrityError(f"manifest {field} must be a lowercase SHA-256 hash")


def validate_manifest(manifest: Mapping[str, object]) -> None:
    """Reject manifests that drift from the distribution contract."""

    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise IntegrityError("unsupported manifest schema_version")
    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        raise IntegrityError("manifest protocol_version does not match")
    if manifest.get("language") != "en":
        raise IntegrityError("manifest language must be 'en'")
    if manifest.get("targets") != list(TARGETS):
        raise IntegrityError("manifest targets do not match the exact target set")

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise IntegrityError("manifest sources must be a non-empty list")
    seen_paths: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise IntegrityError(f"manifest sources[{index}] must be an object")
        path = source.get("path")
        if not _is_relative_portable_path(path):
            raise IntegrityError("manifest source paths must be relative POSIX paths")
        assert isinstance(path, str)
        if path in seen_paths:
            raise IntegrityError(f"duplicate source path: {path}")
        seen_paths.add(path)
        _require_hash(source.get("sha256"), f"sources[{index}].sha256")

    bundle = manifest.get("bundle")
    if not isinstance(bundle, Mapping):
        raise IntegrityError("manifest bundle must be an object")
    if bundle.get("path") != "learning-tutor.prompt.md":
        raise IntegrityError("manifest bundle path must be learning-tutor.prompt.md")
    _require_hash(bundle.get("sha256"), "bundle.sha256")

    fallbacks = manifest.get("capability_fallbacks")
    if not isinstance(fallbacks, Mapping) or set(fallbacks) != set(
        CAPABILITY_FALLBACKS
    ):
        raise IntegrityError("manifest capability_fallbacks are incomplete")
    if any(not isinstance(value, str) or not value.strip() for value in fallbacks.values()):
        raise IntegrityError("manifest capability_fallbacks must be non-empty")

    if manifest.get("session_headings") != list(SESSION_HEADINGS):
        raise IntegrityError("manifest session_headings sequence does not match")
