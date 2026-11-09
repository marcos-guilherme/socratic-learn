"""Frozen transport and bundle models for source ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

SourceKind = Literal["url", "local_pdf"]


@dataclass(frozen=True)
class SourceRequest:
    origin: str
    kind: SourceKind
    allow_private_network: bool = False


@dataclass(frozen=True)
class ExtractedSection:
    label: str
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    title: str
    media_type: str
    sections: tuple[ExtractedSection, ...]


@dataclass(frozen=True)
class FetchedBytes:
    """Bounded HTTP retrieval result kept in memory until ingestion."""

    raw: bytes
    canonical_url: str
    display_origin: str
    media_type: str


@dataclass(frozen=True)
class BundleMetadata:
    """Parsed `metadata.json` fields for validation and host handoff."""

    schema_version: int
    source_id: str
    title: str
    display_origin: str
    media_type: str
    raw_sha256: str
    extracted_at: datetime
    section_count: int
    normalized_characters: int


@dataclass(frozen=True)
class IngestedSource:
    """Published bundle location plus whether an existing bundle was reused."""

    bundle_path: Path
    source_id: str
    metadata: BundleMetadata
    reused: bool
