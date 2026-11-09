"""Source ingestion contracts and normalization utilities."""

from socratic_learn.sources.html import extract_html
from socratic_learn.sources.http import (
    MAX_RAW_BYTES,
    MAX_REDIRECTS,
    SOCKET_TIMEOUT_SECONDS,
    canonicalize_url,
    fetch_url,
)
from socratic_learn.sources.ids import source_id_for_local, source_id_for_url
from socratic_learn.sources.pdf import extract_pdf
from socratic_learn.sources.model import (
    BundleMetadata,
    ExtractedDocument,
    ExtractedSection,
    FetchedBytes,
    IngestedSource,
    SourceKind,
    SourceRequest,
)
from socratic_learn.sources.normalize import (
    DEFAULT_SECTION_CHUNK_LIMIT,
    MAX_NORMALIZED_CODE_POINTS,
    MIN_NON_WHITESPACE_CODE_POINTS,
    chunk_section,
    normalize_text,
)

__all__ = [
    "DEFAULT_SECTION_CHUNK_LIMIT",
    "MAX_RAW_BYTES",
    "MAX_REDIRECTS",
    "MAX_NORMALIZED_CODE_POINTS",
    "MIN_NON_WHITESPACE_CODE_POINTS",
    "SOCKET_TIMEOUT_SECONDS",
    "BundleMetadata",
    "ExtractedDocument",
    "ExtractedSection",
    "FetchedBytes",
    "IngestedSource",
    "SourceKind",
    "SourceRequest",
    "canonicalize_url",
    "chunk_section",
    "extract_html",
    "fetch_url",
    "extract_pdf",
    "normalize_text",
    "source_id_for_local",
    "source_id_for_url",
]
