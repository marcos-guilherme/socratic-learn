"""Deterministic Unicode normalization and section chunking."""

from __future__ import annotations

import re
import unicodedata

from socratic_learn.errors import SourceError

MIN_NON_WHITESPACE_CODE_POINTS = 200
MAX_NORMALIZED_CODE_POINTS = 5_000_000
DEFAULT_SECTION_CHUNK_LIMIT = 12_000

_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def normalize_text(text: str, *, require_meaningful: bool = True) -> str:
    """Normalize source text to NFC, LF, and stable whitespace.

    Whole-document ingestion keeps ``require_meaningful=True`` (default) and
    rejects fewer than ``MIN_NON_WHITESPACE_CODE_POINTS`` non-whitespace
    characters. Per-page or per-section fragments for extraction should pass
    ``require_meaningful=False`` to apply the same transforms without the
    document-wide minimum.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    lines = [_HORIZONTAL_WHITESPACE.sub(" ", line.strip(" \t")) for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANK_LINES.sub("\n\n", text)
    _validate_text_bounds(text, require_meaningful=require_meaningful)
    return text


def _validate_text_bounds(text: str, *, require_meaningful: bool) -> None:
    if len(text) > MAX_NORMALIZED_CODE_POINTS:
        raise SourceError(
            f"normalized source exceeds {MAX_NORMALIZED_CODE_POINTS} code points",
            remediation="Use a shorter source or split the material.",
        )
    if not require_meaningful:
        return
    non_whitespace = sum(1 for character in text if not character.isspace())
    if non_whitespace < MIN_NON_WHITESPACE_CODE_POINTS:
        raise SourceError(
            f"source has fewer than {MIN_NON_WHITESPACE_CODE_POINTS} meaningful characters",
            remediation="Choose a source with more extractable text.",
        )


def chunk_section(text: str, *, limit: int = DEFAULT_SECTION_CHUNK_LIMIT) -> tuple[str, ...]:
    if limit <= 0:
        raise SourceError(
            "chunk limit must be positive",
            remediation="Use a positive Unicode code-point limit.",
        )
    if len(text) <= limit:
        return (text,)

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        max_end = min(start + limit, text_length)
        if max_end >= text_length:
            chunks.append(text[start:])
            break
        end = _choose_boundary(text, start, max_end)
        if end <= start:
            end = max_end
        chunks.append(text[start:end])
        start = end
    return tuple(chunks)


def _choose_boundary(text: str, start: int, max_end: int) -> int:
    window = text[start:max_end]
    paragraph = window.rfind("\n\n")
    if paragraph != -1:
        return start + paragraph + 2
    for position in range(max_end - 1, start, -1):
        if text[position].isspace():
            return position
    return max_end
