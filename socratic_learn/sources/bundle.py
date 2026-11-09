"""Deterministic private source bundle serialization and validation."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from socratic_learn.errors import IntegrityError
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

    children = sorted(path.iterdir(), key=lambda item: item.name)
    names = {child.name for child in children}
    required = {"metadata.json", "index.md", "original.bin", "sections"}
    if names != required:
        raise _bundle_invalid("bundle layout is incomplete or contains unexpected entries")

    for child in children:
        status = child.lstat() if hasattr(child, "lstat") else child.stat()
        if child.is_symlink():
            raise _bundle_invalid("bundle contains a symbolic link")
        if child.name == "sections":
            if not child.is_dir():
                raise _bundle_invalid("sections entry is not a directory")
            continue
        if not child.is_file():
            raise _bundle_invalid("bundle contains a non-regular entry")

    metadata = _load_metadata(path / "metadata.json", expected_id)
    raw = (path / "original.bin").read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata.raw_sha256:
        raise _bundle_invalid("original.bin does not match metadata raw_sha256")

    _validate_sections(path / "sections", metadata)
    _validate_index(path / "index.md", metadata)
    return metadata


def _validate_sections(sections_dir: Path, metadata: BundleMetadata) -> None:
    chunk_paths = sorted(sections_dir.iterdir(), key=lambda item: item.name)
    if not chunk_paths:
        raise _bundle_invalid("bundle has no chunk files")
    expected_number = 1
    for chunk_path in chunk_paths:
        if chunk_path.is_symlink() or not chunk_path.is_file():
            raise _bundle_invalid("chunk path is not a regular file")
        match = _CHUNK_NAME_RE.match(chunk_path.name)
        if match is None:
            raise _bundle_invalid("chunk filename is malformed")
        number = int(match.group(1))
        if number != expected_number:
            raise _bundle_invalid("chunk numbering has gaps or is out of order")
        expected_number += 1
        data = chunk_path.read_bytes()
        if b"\r" in data:
            raise _bundle_invalid("chunk file contains CR bytes")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise _bundle_invalid("chunk file is not valid UTF-8") from error
        if text != unicodedata.normalize("NFC", text):
            raise _bundle_invalid("chunk file is not Unicode NFC")
        if len(text) > DEFAULT_SECTION_CHUNK_LIMIT:
            raise _bundle_invalid("chunk file exceeds the code-point limit")


def _validate_index(index_path: Path, metadata: BundleMetadata) -> None:
    text = index_path.read_text(encoding="utf-8")
    if "\r" in text:
        raise _bundle_invalid("index file contains CR bytes")
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
    section_dir = index_path.parent / "sections"
    chunk_files = sorted(path.name for path in section_dir.iterdir())
    if len(chunk_lines) != len(chunk_files):
        raise _bundle_invalid("index chunk list does not match sections tree")
    observed_paths: list[str] = []
    for line in chunk_lines:
        match = _INDEX_LINE_RE.match(line)
        if match is None:
            raise _bundle_invalid("index chunk entry is malformed")
        observed_paths.append(f"sections/{match.group(2)}.txt")
    expected_paths = [f"sections/{name}" for name in chunk_files]
    if observed_paths != expected_paths:
        raise _bundle_invalid("index chunk order does not match section files")


def _load_metadata(metadata_path: Path, expected_id: str) -> BundleMetadata:
    try:
        raw = metadata_path.read_bytes()
    except OSError as error:
        raise _bundle_invalid("metadata.json is unreadable") from error
    if b"\r" in raw:
        raise _bundle_invalid("metadata.json contains CR bytes")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _bundle_invalid("metadata.json is not valid JSON") from error
    if not isinstance(document, dict):
        raise _bundle_invalid("metadata.json must contain an object")
    if set(document) != _METADATA_KEYS:
        raise _bundle_invalid("metadata.json has unexpected fields")
    _reject_private_metadata_strings(document)

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


def _reject_private_metadata_strings(document: dict[str, object]) -> None:
    for key, value in document.items():
        if not isinstance(value, str):
            continue
        if key == "display_origin":
            if "?" in value:
                raise _bundle_invalid("metadata display_origin contains a query")
            if "\\" in value or ("/" in value and "://" not in value):
                raise _bundle_invalid("metadata display_origin contains a path")
            if re.search(r"(?i)^[a-z]:", value):
                raise _bundle_invalid("metadata display_origin contains an absolute path")
        lowered = value.lower()
        for marker in ("canonical_url", "cookie", "header", "password", "token", "query"):
            if marker in lowered:
                raise _bundle_invalid("metadata contains private retrieval data")


def _reject_invalid_id(source_id: str) -> None:
    if not _SOURCE_ID_RE.fullmatch(source_id):
        raise _bundle_invalid("source identifier must be 64 lowercase hexadecimal characters")


def _bundle_invalid(message: str) -> IntegrityError:
    return IntegrityError(
        message,
        remediation="re-ingest the source or inspect the private bundle for recovery",
    )
