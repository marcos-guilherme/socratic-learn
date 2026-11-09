from __future__ import annotations

import dataclasses
import hashlib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from socratic_learn.errors import LearningTutorError, SourceError
from socratic_learn.sources.ids import source_id_for_local, source_id_for_url
from socratic_learn.sources.model import (
    BundleMetadata,
    ExtractedDocument,
    ExtractedSection,
    FetchedBytes,
    IngestedSource,
    SourceKind,
    SourceRequest,
)


class SourceErrorTests(unittest.TestCase):
    def test_source_error_is_learning_tutor_error_with_exit_code_six(self) -> None:
        error = SourceError("rejected source")
        self.assertIsInstance(error, LearningTutorError)
        self.assertEqual(6, error.exit_code)


class SourceIdentityTests(unittest.TestCase):
    def test_local_id_uses_domain_separator_and_raw_bytes_only(self) -> None:
        raw = b"%PDF-1.4 minimal"
        expected = hashlib.sha256(b"local-pdf\0" + raw).hexdigest()
        self.assertEqual(expected, source_id_for_local(raw))
        self.assertEqual(expected, source_id_for_local(raw))

    def test_url_id_is_sensitive_to_canonical_url_query(self) -> None:
        raw = b"<html>article</html>"
        without_query = hashlib.sha256(
            b"url\0" + b"https://example.com/article\0" + raw
        ).hexdigest()
        with_query = hashlib.sha256(
            b"url\0" + b"https://example.com/article?tab=1\0" + raw
        ).hexdigest()
        self.assertNotEqual(without_query, with_query)
        self.assertEqual(
            without_query,
            source_id_for_url("https://example.com/article", raw),
        )
        self.assertEqual(
            with_query,
            source_id_for_url("https://example.com/article?tab=1", raw),
        )


class FrozenSourceModelTests(unittest.TestCase):
    def test_source_request_is_frozen(self) -> None:
        request = SourceRequest("paper.pdf", "local_pdf")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            request.origin = "other.pdf"  # type: ignore[misc]

    def test_source_kind_literal_values(self) -> None:
        url_request = SourceRequest("https://example.com", "url")
        local_request = SourceRequest("article.pdf", "local_pdf")
        self.assertEqual("url", url_request.kind)
        self.assertEqual("local_pdf", local_request.kind)
        self.assertIn(url_request.kind, ("url", "local_pdf"))
        self.assertIn(local_request.kind, ("url", "local_pdf"))

    def test_extracted_document_contract(self) -> None:
        section = ExtractedSection(label="Introduction", text="Body")
        document = ExtractedDocument(
            title="Sample",
            media_type="application/pdf",
            sections=(section,),
        )
        self.assertEqual("Sample", document.title)
        self.assertEqual("application/pdf", document.media_type)
        self.assertEqual(section, document.sections[0])

    def test_fetched_bytes_transport_shape(self) -> None:
        payload = FetchedBytes(
            raw=b"content",
            canonical_url="https://example.com/article?token=secret",
            display_origin="https://example.com/article",
            media_type="text/html",
        )
        self.assertEqual(b"content", payload.raw)
        self.assertIn("?token=", payload.canonical_url)
        self.assertNotIn("?", payload.display_origin)

    def test_bundle_metadata_matches_persisted_responsibilities(self) -> None:
        timestamp = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
        metadata = BundleMetadata(
            schema_version=1,
            source_id="a" * 64,
            title="Article",
            display_origin="article.pdf",
            media_type="application/pdf",
            raw_sha256="b" * 64,
            extracted_at=timestamp,
            section_count=3,
            normalized_characters=1200,
        )
        self.assertEqual(1, metadata.schema_version)
        self.assertEqual(timestamp, metadata.extracted_at)

    def test_ingested_source_references_bundle_location(self) -> None:
        metadata = BundleMetadata(
            schema_version=1,
            source_id="c" * 64,
            title="Article",
            display_origin="https://example.com",
            media_type="text/html",
            raw_sha256="d" * 64,
            extracted_at=datetime(2026, 11, 8, tzinfo=timezone.utc),
            section_count=1,
            normalized_characters=500,
        )
        ingested = IngestedSource(
            bundle_path=Path("/records/sources") / ("c" * 64),
            source_id="c" * 64,
            metadata=metadata,
            reused=False,
        )
        self.assertEqual(ingested.source_id, ingested.metadata.source_id)
        self.assertFalse(ingested.reused)
