"""Private evidence sanitization and secure writes for semantic evaluation."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evaluation.schema import JsonValue

# Extension (6th pattern): uppercase env-style names with underscore segments where at least one
# full segment is API, KEY, TOKEN, SECRET, ACCESS, or AUTH (e.g. OPENAI_API_KEY, AWS_SECRET_ACCESS_KEY,
# MY_PROVIDER_TOKEN). Matches assignment `NAME=` / `NAME:` and JSON `"NAME":`. Does not match
# bare words like "token" in prose (requires NAME[=:] or quoted NAME plus colon). Excludes `max_tokens`
# / `MAX_TOKENS` because TOKEN must be an entire segment, not TOKENS.
_CREDENTIAL_ENV_STYLE_NAME = (
    r"(?:"  # one or more WORD_ prefixes ending at a credential segment
    r"(?:[A-Z][A-Z0-9]*_)+(?:API|KEY|TOKEN|SECRET|ACCESS|AUTH)"
    r"(?:_[A-Z][A-Z0-9]*)*"  # trailing segments (e.g. ..._ACCESS_KEY)
    r")"
)

_TRACKED_FORBIDDEN = (
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|access[_-]?token)\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+\\"),
    re.compile(r"/(?:Users|home)/[^/\r\n]+/"),
    re.compile(r"(?i)\b(?:conversation|session)[_-]?id\b.*[A-Za-z0-9_-]{12,}"),
    # Case-sensitive env-name matching so `max_tokens=` / `monkey=` / prose "token" stay allowed.
    re.compile(
        r"(?:"
        r"(?<![A-Za-z0-9_])"
        + _CREDENTIAL_ENV_STYLE_NAME
        + r"\s*[=:]"
        r'|[\'"]'
        + _CREDENTIAL_ENV_STYLE_NAME
        + r'[\'"]\s*:'
        r")"
    ),
)


@dataclass(frozen=True)
class RedactionRule:
    literal: str
    replacement: str


def _normalized_rule_table(rules: Sequence[RedactionRule]) -> tuple[dict[str, str], tuple[str, ...]]:
    literal_to_replacement: dict[str, str] = {}
    for rule in rules:
        if not rule.literal:
            raise ValueError("redaction literal must be non-empty")
        prior = literal_to_replacement.get(rule.literal)
        if prior is not None and prior != rule.replacement:
            raise ValueError("conflicting replacement for duplicate literal")
        literal_to_replacement[rule.literal] = rule.replacement
    indexed_items = sorted(
        literal_to_replacement.items(),
        key=lambda item: (-len(item[0]), item[0]),
    )
    ordered_literals = tuple(lit for lit, _ in indexed_items)
    return literal_to_replacement, ordered_literals


def sanitize_text(text: str, rules: Sequence[RedactionRule]) -> str:
    """Single-pass longest-match-first literal replacement; replacements are not re-scanned."""
    replacements, literals_longest_first = _normalized_rule_table(rules)
    n = len(text)
    i = 0
    parts: list[str] = []
    while i < n:
        matched: str | None = None
        for lit in literals_longest_first:
            if text.startswith(lit, i):
                matched = lit
                break
        if matched is not None:
            parts.append(replacements[matched])
            i += len(matched)
        else:
            parts.append(text[i])
            i += 1
    return "".join(parts)


def sanitize_json(value: JsonValue, rules: Sequence[RedactionRule]) -> JsonValue:
    """Recursively sanitize string leaves and dict keys; reject unsupported containers."""
    if isinstance(value, str):
        return sanitize_text(value, rules)
    if isinstance(value, dict):
        out: dict[str, JsonValue] = {}
        seen_original: set[str] = set()
        seen_sanitized: set[str] = set()
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("dict keys must be strings")
            if key in seen_original:
                raise ValueError("duplicate dict key")
            seen_original.add(key)
            new_key = sanitize_text(key, rules)
            if new_key in seen_sanitized:
                raise ValueError("sanitized dict key collision")
            seen_sanitized.add(new_key)
            out[new_key] = sanitize_json(item, rules)
        return out
    if isinstance(value, list):
        return [sanitize_json(item, rules) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    raise TypeError("unsupported JSON value type")


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
    root = private_root.resolve(strict=True)

    candidate = path if path.is_absolute() else (root / path)
    try:
        destination = candidate.resolve(strict=False)
        destination.relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValueError("destination outside private_root") from exc

    if destination == root:
        raise ValueError("destination must not equal private_root")

    destination.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd: int | None
    tmp_path: str
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(destination.parent),
        prefix=".private_write_",
    )
    committed = False
    try:
        try:
            os.chmod(tmp_path, 0o600)
        except BaseException:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
            tmp_fd = None
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        try:
            with os.fdopen(tmp_fd, "wb") as handle:
                tmp_fd = None
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, destination)
            committed = True
        except BaseException:
            if tmp_fd is not None:
                try:
                    os.close(tmp_fd)
                except OSError:
                    pass
                tmp_fd = None
            raise
    finally:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        if not committed:
            try:
                if os.path.lexists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
