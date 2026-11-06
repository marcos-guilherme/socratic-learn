"""Private evidence sanitization and secure writes for semantic evaluation."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evaluation.schema import JsonValue

_TRACKED_FORBIDDEN = (
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|access[_-]?token)\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+\\"),
    re.compile(r"/(?:Users|home)/[^/\r\n]+/"),
    re.compile(r"(?i)\b(?:conversation|session)[_-]?id\b.*[A-Za-z0-9_-]{12,}"),
)


@dataclass(frozen=True)
class RedactionRule:
    literal: str
    replacement: str


def sanitize_text(text: str, rules: Sequence[RedactionRule]) -> str:
    """Apply literal replacements longest-first; rules are independent of input order."""
    ordered = sorted(rules, key=lambda r: len(r.literal), reverse=True)
    result = text
    for rule in ordered:
        result = result.replace(rule.literal, rule.replacement)
    return result


def sanitize_json(value: JsonValue, rules: Sequence[RedactionRule]) -> JsonValue:
    """Recursively sanitize string leaves; preserves JSON shape and non-string scalars."""
    if isinstance(value, str):
        return sanitize_text(value, rules)
    if isinstance(value, dict):
        return {k: sanitize_json(v, rules) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_json(item, rules) for item in value]
    return value


def assert_tracked_safe(text: str, *, forbidden_literals: Sequence[str]) -> None:
    """Reject tracked text that leaks secrets, credentials, home paths, or forbidden literals."""
    for literal in forbidden_literals:
        if literal in text:
            raise ValueError("tracked text contains forbidden literal")
    for pattern in _TRACKED_FORBIDDEN:
        if pattern.search(text):
            raise ValueError("tracked text matches forbidden pattern")


def write_private(path: Path, data: bytes, *, private_root: Path) -> None:
    """Atomically write bytes under private_root with restrictive permissions."""
    root = private_root.resolve()
    candidate = path if path.is_absolute() else (root / path)
    destination = candidate.resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise ValueError("destination outside private_root") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=".private_write_",
    )
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(tmp_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, destination)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
