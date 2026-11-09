"""Deterministic private source bundle serialization and validation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from socratic_learn.errors import IntegrityError
from socratic_learn.safe_fs import (
    IdentityMismatchError,
    TrackedDirectory,
    TrackedEntry,
    status_identity,
    track_directory,
)
from socratic_learn.safe_fs import _is_reparse_or_symlink, _verify_tracked_tree
from socratic_learn.sources.model import BundleMetadata, ExtractedDocument
from socratic_learn.sources.normalize import DEFAULT_SECTION_CHUNK_LIMIT, chunk_section

BUNDLE_SCHEMA_VERSION = 1
_SOURCE_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_METADATA_KEYS = frozenset(
    {
        "schema_version",
        "source_id",
        "title",
        "display_origin",
        "media_type",
        "raw_sha256",
        "extracted_at",
        "section_count",
        "normalized_characters",
    }
)
_ALLOWED_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "text/html",
        "application/xhtml+xml",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_NAME_RE = re.compile(r"^(\d{4})\.txt$")
_SECTIONS_CHILD_RE = re.compile(r"^sections/\d{4}\.txt$")
_INDEX_LINE_RE = re.compile(r"^- (.+): sections/(\d{4})\.txt$")


def canonical_metadata_bytes(metadata: BundleMetadata) -> bytes:
    if metadata.extracted_at.tzinfo is None:
        raise ValueError("extracted_at must be timezone-aware")
    utc = metadata.extracted_at.astimezone(timezone.utc)
    payload = {
        "schema_version": metadata.schema_version,
        "source_id": metadata.source_id,
        "title": metadata.title,
        "display_origin": metadata.display_origin,
        "media_type": metadata.media_type,
        "raw_sha256": metadata.raw_sha256,
        "extracted_at": utc.isoformat(),
        "section_count": metadata.section_count,
        "normalized_characters": metadata.normalized_characters,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    ) + b"\n"


def build_bundle_tree(
    bundle_dir: Path,
    *,
    raw: bytes,
    document: ExtractedDocument,
    source_id: str,
    display_origin: str,
    extracted_at: datetime,
) -> BundleMetadata:
    if extracted_at.tzinfo is None:
        extracted_at = extracted_at.replace(tzinfo=timezone.utc)
    sections_dir = bundle_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    index_lines: list[str] = []
    chunk_number = 1
    normalized_characters = 0
    for section in document.sections:
        normalized_characters += len(section.text)
        chunks = chunk_section(section.text)
        for sequence, chunk in enumerate(chunks, start=1):
            chunk_name = f"{chunk_number:04d}.txt"
            chunk_path = sections_dir / chunk_name
            encoded = unicodedata.normalize("NFC", chunk).encode("utf-8")
            chunk_path.write_bytes(encoded)
            label = f"{section.label} / {sequence}"
            index_lines.append(f"- {label}: sections/{chunk_name}")
            chunk_number += 1

    metadata = BundleMetadata(
        schema_version=BUNDLE_SCHEMA_VERSION,
        source_id=source_id,
        title=document.title,
        display_origin=display_origin,
        media_type=document.media_type,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        extracted_at=extracted_at,
        section_count=len(document.sections),
        normalized_characters=normalized_characters,
    )
    (bundle_dir / "metadata.json").write_bytes(canonical_metadata_bytes(metadata))
    (bundle_dir / "original.bin").write_bytes(raw)
    index_body = _render_index(document, display_origin, index_lines)
    (bundle_dir / "index.md").write_bytes(index_body.encode("utf-8"))
    return metadata


def _render_index(
    document: ExtractedDocument,
    display_origin: str,
    chunk_lines: list[str],
) -> str:
    lines = [
        f"# {document.title}",
        "",
        f"display_origin: {display_origin}",
        f"media_type: {document.media_type}",
        "",
        "## Chunks",
        "",
        *chunk_lines,
        "",
    ]
    return "\n".join(lines)


def validate_source_bundle(path: Path, expected_id: str) -> BundleMetadata:
    _reject_invalid_id(expected_id)
    if not path.is_dir():
        raise _bundle_invalid("bundle path is not a directory")

    try:
        tracked = track_directory(path)
    except IdentityMismatchError as error:
        raise _bundle_invalid("bundle contains a link or reparse point") from error
    _verify_tracked_tree(tracked)
    entries = {entry.relative: entry for entry in tracked.entries}
    required = {"metadata.json", "index.md", "original.bin", "sections"}
    top_level = {relative.split("/", 1)[0] for relative in entries}
    if top_level != required:
        raise _bundle_invalid("bundle layout is incomplete or contains unexpected entries")

    metadata = _load_metadata(path, "metadata.json", entries["metadata.json"], expected_id)
    _verify_tracked_tree(tracked)
    raw = _read_tracked_regular_file(path, "original.bin", entries["original.bin"])
    if hashlib.sha256(raw).hexdigest() != metadata.raw_sha256:
        raise _bundle_invalid("original.bin does not match metadata raw_sha256")

    chunk_texts = _validate_sections(path, "sections", entries["sections"], tracked)
    _verify_tracked_tree(tracked)
    derived_counts = _validate_index(
        path,
        "index.md",
        entries["index.md"],
        metadata,
        chunk_texts,
    )
    _verify_tracked_tree(tracked)
    if derived_counts.section_count != metadata.section_count:
        raise _bundle_invalid("metadata section_count does not match the index")
    if derived_counts.normalized_characters != metadata.normalized_characters:
        raise _bundle_invalid(
            "metadata normalized_characters does not match the chunk contents"
        )
    return metadata


def _read_tracked_regular_file(
    root: Path,
    relative: str,
    expected: TrackedEntry,
) -> bytes:
    target = root / relative
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags)
    try:
        status = os.fstat(descriptor)
        if _is_reparse_or_symlink(status) or not stat.S_ISREG(status.st_mode):
            raise _bundle_invalid("bundle entry is not a regular file")
        if status_identity(status) != expected.identity:
            raise _bundle_invalid("bundle entry identity changed during validation")
        remaining = status.st_size
        chunks: list[bytes] = []
        while remaining > 0:
            block = os.read(descriptor, min(remaining, 65536))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_tracked_utf8_text(
    root: Path,
    relative: str,
    expected: TrackedEntry,
) -> str:
    data = _read_tracked_regular_file(root, relative, expected)
    if b"\r" in data:
        raise _bundle_invalid(f"{relative} contains CR bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _bundle_invalid(f"{relative} is not valid UTF-8") from error


def _validate_sections(
    bundle_root: Path,
    relative: str,
    sections_entry: TrackedEntry,
    tracked: TrackedDirectory,
) -> dict[str, str]:
    if not sections_entry.directory:
        raise _bundle_invalid("sections entry is not a directory")
    section_children = [entry for entry in tracked.entries if entry.relative.startswith("sections/")]
    for entry in section_children:
        if entry.directory:
            raise _bundle_invalid("sections directory contains a nested directory")
        if not _SECTIONS_CHILD_RE.fullmatch(entry.relative):
            raise _bundle_invalid("sections directory contains an unexpected entry")
    chunk_entries = sorted(section_children, key=lambda entry: entry.relative)
    if not chunk_entries:
        raise _bundle_invalid("bundle has no chunk files")

    texts: dict[str, str] = {}
    expected_number = 1
    for entry in chunk_entries:
        chunk_name = Path(entry.relative).name
        match = _CHUNK_NAME_RE.match(chunk_name)
        if match is None:
            raise _bundle_invalid("chunk filename is malformed")
        number = int(match.group(1))
        if number != expected_number:
            raise _bundle_invalid("chunk numbering has gaps or is out of order")
        expected_number += 1
        text = _read_tracked_utf8_text(bundle_root, entry.relative, entry)
        if text != unicodedata.normalize("NFC", text):
            raise _bundle_invalid("chunk file is not Unicode NFC")
        if len(text) > DEFAULT_SECTION_CHUNK_LIMIT:
            raise _bundle_invalid("chunk file exceeds the code-point limit")
        texts[chunk_name] = text
    return texts


def _parse_index_label(label_body: str) -> tuple[str, int]:
    if " / " not in label_body:
        raise _bundle_invalid("index chunk label is missing a sequence separator")
    source_label, sequence_text = label_body.rsplit(" / ", 1)
    if not sequence_text.isdigit():
        raise _bundle_invalid("index chunk sequence is not numeric")
    sequence = int(sequence_text)
    if sequence < 1:
        raise _bundle_invalid("index chunk sequence must start at one")
    return source_label, sequence


class _DerivedIndexCounts:
    def __init__(self, *, section_count: int, normalized_characters: int) -> None:
        self.section_count = section_count
        self.normalized_characters = normalized_characters


def _validate_index(
    bundle_root: Path,
    relative: str,
    index_entry: TrackedEntry,
    metadata: BundleMetadata,
    chunk_texts: dict[str, str],
) -> _DerivedIndexCounts:
    text = _read_tracked_utf8_text(bundle_root, relative, index_entry)
    lines = text.split("\n")
    if not lines or not lines[0].startswith("# "):
        raise _bundle_invalid("index title is missing")
    title = lines[0][2:]
    if title != metadata.title:
        raise _bundle_invalid("index title does not match metadata")
    if f"display_origin: {metadata.display_origin}" not in lines:
        raise _bundle_invalid("index display_origin does not match metadata")
    if f"media_type: {metadata.media_type}" not in lines:
        raise _bundle_invalid("index media_type does not match metadata")

    chunk_lines = [line for line in lines if line.startswith("- ")]
    chunk_names = sorted(chunk_texts)
    if len(chunk_lines) != len(chunk_names):
        raise _bundle_invalid("index chunk list does not match sections tree")

    normalized_characters = 0
    section_count = 0
    current_label: str | None = None
    expected_sequence = 0

    for line, chunk_name in zip(chunk_lines, chunk_names, strict=True):
        match = _INDEX_LINE_RE.match(line)
        if match is None:
            raise _bundle_invalid("index chunk entry is malformed")
        source_label, sequence = _parse_index_label(match.group(1))
        if f"sections/{match.group(2)}.txt" != f"sections/{chunk_name}":
            raise _bundle_invalid("index chunk order does not match section files")
        if sequence == 1:
            section_count += 1
            current_label = source_label
            expected_sequence = 1
        else:
            if current_label is None or source_label != current_label:
                raise _bundle_invalid("index chunk sequence breaks section grouping")
            expected_sequence += 1
            if sequence != expected_sequence:
                raise _bundle_invalid("index chunk sequence is not contiguous")
        normalized_characters += len(chunk_texts[chunk_name])

    if section_count < 1:
        raise _bundle_invalid("index does not define any sections")
    return _DerivedIndexCounts(
        section_count=section_count,
        normalized_characters=normalized_characters,
    )


def _load_metadata(
    bundle_root: Path,
    relative: str,
    entry: TrackedEntry,
    expected_id: str,
) -> BundleMetadata:
    raw = _read_tracked_regular_file(bundle_root, relative, entry)
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _bundle_invalid("metadata.json is not valid JSON") from error
    if not isinstance(document, dict):
        raise _bundle_invalid("metadata.json must contain an object")
    if set(document) != _METADATA_KEYS:
        raise _bundle_invalid("metadata.json has unexpected fields")
    _reject_private_display_origin(document)

    schema_version = document["schema_version"]
    if type(schema_version) is not int or schema_version != BUNDLE_SCHEMA_VERSION:
        raise _bundle_invalid("metadata schema_version is invalid")

    source_id = document["source_id"]
    if type(source_id) is not str or source_id != expected_id:
        raise _bundle_invalid("metadata source_id does not match expected identifier")
    _reject_invalid_id(source_id)

    title = document["title"]
    display_origin = document["display_origin"]
    media_type = document["media_type"]
    raw_sha256 = document["raw_sha256"]
    extracted_at_raw = document["extracted_at"]
    section_count = document["section_count"]
    normalized_characters = document["normalized_characters"]
    for value, label in (
        (title, "title"),
        (display_origin, "display_origin"),
        (media_type, "media_type"),
        (raw_sha256, "raw_sha256"),
        (extracted_at_raw, "extracted_at"),
    ):
        if type(value) is not str:
            raise _bundle_invalid(f"metadata {label} must be a string")
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise _bundle_invalid("metadata media_type is not supported")
    if not _SHA256_RE.fullmatch(raw_sha256):
        raise _bundle_invalid("metadata raw_sha256 is malformed")
    try:
        extracted_at = datetime.fromisoformat(extracted_at_raw)
    except ValueError as error:
        raise _bundle_invalid("metadata extracted_at is malformed") from error
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise _bundle_invalid("metadata extracted_at must be UTC")
    if extracted_at.utcoffset().total_seconds() != 0:
        raise _bundle_invalid("metadata extracted_at must be UTC")
    if type(section_count) is not int or section_count < 1:
        raise _bundle_invalid("metadata section_count is invalid")
    if type(normalized_characters) is not int or normalized_characters < 0:
        raise _bundle_invalid("metadata normalized_characters is invalid")

    metadata = BundleMetadata(
        schema_version=schema_version,
        source_id=source_id,
        title=title,
        display_origin=display_origin,
        media_type=media_type,
        raw_sha256=raw_sha256,
        extracted_at=extracted_at,
        section_count=section_count,
        normalized_characters=normalized_characters,
    )
    if raw != canonical_metadata_bytes(metadata):
        raise _bundle_invalid("metadata.json is not canonical")
    return metadata


def _reject_private_display_origin(document: dict[str, object]) -> None:
    display_origin = document.get("display_origin")
    if not isinstance(display_origin, str):
        return
    if "?" in display_origin:
        raise _bundle_invalid("metadata display_origin contains a query")
    if "\\" in display_origin or ("/" in display_origin and "://" not in display_origin):
        raise _bundle_invalid("metadata display_origin contains a path")
    if re.search(r"(?i)^[a-z]:", display_origin):
        raise _bundle_invalid("metadata display_origin contains an absolute path")


def _reject_invalid_id(source_id: str) -> None:
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise _bundle_invalid("source identifier must be 64 lowercase hexadecimal characters")


def _bundle_invalid(message: str) -> IntegrityError:
    return IntegrityError(
        message,
        remediation="re-ingest the source or inspect the private bundle for recovery",
    )
