from __future__ import annotations

import os
import stat
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from socratic_learn import __version__
from socratic_learn.errors import FilesystemError, IntegrityError, SourceError
from socratic_learn.sources.http import MAX_RAW_BYTES
from socratic_learn.sources.ids import source_id_for_local, source_id_for_url
from socratic_learn.sources.ingest import ingest_source
from socratic_learn.sources.model import ExtractedDocument, ExtractedSection, FetchedBytes, SourceRequest
from socratic_learn.sources.bundle import validate_source_bundle
from tests.pdf_fixture import build_text_pdf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
TEST_HOST = "93.184.216.34"


def _meaningful_page(prefix: str = "Evidence") -> str:
    return f"{prefix} paragraph. " + "word " * 45


def _pad_html(html: str) -> str:
    filler = "<p>" + "content " * 40 + "</p>"
    return html.replace("</article>", filler + "</article>", 1)


class LocalIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.records = Path(self._temporary.name) / "records"
        self.records.mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_local_pdf_end_to_end_bundle_layout(self) -> None:
        pdf_dir = Path(self._temporary.name) / "pdfs"
        pdf_dir.mkdir()
        pdf_path = pdf_dir / "nested" / "deep" / "paper.pdf"
        pdf_path.parent.mkdir(parents=True)
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        pdf_path.write_bytes(raw)
        result = ingest_source(
            self.records,
            SourceRequest(str(pdf_path.resolve()), "local_pdf"),
        )
        self.assertFalse(result.reused)
        self.assertEqual(result.source_id, source_id_for_local(raw))
        metadata = validate_source_bundle(result.bundle_path, result.source_id)
        self.assertEqual("paper.pdf", metadata.display_origin)
        text = (result.bundle_path / "metadata.json").read_text("utf-8")
        self.assertNotIn("nested", text)
        self.assertNotIn("deep", text)
        self.assertNotIn("?", text)

    def test_reuses_valid_bundle_without_changing_mtimes(self) -> None:
        pdf_path = self.records / "paper.pdf"
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        pdf_path.write_bytes(raw)
        request = SourceRequest(str(pdf_path), "local_pdf")
        first = ingest_source(self.records, request)
        snapshots = {
            path: path.stat().st_mtime_ns
            for path in first.bundle_path.rglob("*")
            if path.is_file()
        }
        second = ingest_source(self.records, request)
        self.assertTrue(second.reused)
        for path, mtime in snapshots.items():
            self.assertEqual(mtime, path.stat().st_mtime_ns)

    def test_rejects_invalid_existing_bundle_without_mutation(self) -> None:
        pdf_path = self.records / "paper.pdf"
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        pdf_path.write_bytes(raw)
        request = SourceRequest(str(pdf_path), "local_pdf")
        first = ingest_source(self.records, request)
        broken = first.bundle_path / "metadata.json"
        original = broken.read_bytes()
        broken.write_bytes(b"{}\n")
        with self.assertRaises(IntegrityError):
            ingest_source(self.records, request)
        self.assertEqual(b"{}\n", broken.read_bytes())
        broken.write_bytes(original)

    def test_rejects_local_symlink(self) -> None:
        if os.name == "nt":
            self.skipTest("POSIX symlink leaf required")
        target = self.records / "real.pdf"
        target.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        link = self.records / "linked.pdf"
        link.symlink_to(target)
        with self.assertRaises(SourceError):
            ingest_source(self.records, SourceRequest(str(link), "local_pdf"))

    def test_rejects_oversized_local_input(self) -> None:
        pdf_path = self.records / "huge.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * (MAX_RAW_BYTES + 1))
        with self.assertRaises(SourceError):
            ingest_source(self.records, SourceRequest(str(pdf_path), "local_pdf"))


class UrlIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.records = Path(self._temporary.name) / "records"
        self.records.mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_url_html_end_to_end_without_persisting_query(self) -> None:
        html = _pad_html(
            "<html><head><title>URL Article</title></head>"
            "<body><article><p>URL article paragraph with enough content.</p>"
            "</article></body></html>"
        )
        raw = html.encode("utf-8")
        canonical = "http://example.com/article?token=secret"
        display = "http://example.com/article"
        fetched = FetchedBytes(
            raw=raw,
            canonical_url=canonical,
            display_origin=display,
            media_type="text/html",
        )

        with mock.patch(
            "socratic_learn.sources.ingest.fetch_url",
            return_value=fetched,
        ) as fetch_mock:
            result = ingest_source(
                self.records,
                SourceRequest("http://example.com/article?token=secret", "url"),
            )
        fetch_mock.assert_called_once()
        self.assertEqual(f"Socratic-Learn/{__version__}", fetch_mock.call_args.kwargs["user_agent"])
        self.assertEqual(
            result.source_id,
            source_id_for_url(canonical, raw),
        )
        metadata = validate_source_bundle(result.bundle_path, result.source_id)
        self.assertEqual(display, metadata.display_origin)
        index = (result.bundle_path / "index.md").read_text("utf-8")
        self.assertIn("URL Article / 1", index)
        self.assertNotIn("token", (result.bundle_path / "metadata.json").read_text("utf-8"))

    def test_url_pdf_dispatch(self) -> None:
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        canonical = "https://example.com/paper.pdf"
        fetched = FetchedBytes(
            raw=raw,
            canonical_url=canonical,
            display_origin=canonical,
            media_type="application/pdf",
        )
        with mock.patch("socratic_learn.sources.ingest.fetch_url", return_value=fetched):
            result = ingest_source(
                self.records,
                SourceRequest(canonical, "url"),
            )
        metadata = validate_source_bundle(result.bundle_path, result.source_id)
        self.assertEqual("application/pdf", metadata.media_type)


class IngestFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.records = Path(self._temporary.name) / "records"
        self.records.mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_maps_extraction_failure_to_source_error(self) -> None:
        pdf_path = self.records / "tiny.pdf"
        pdf_path.write_bytes(build_text_pdf(("short",)))
        with self.assertRaises(SourceError):
            ingest_source(self.records, SourceRequest(str(pdf_path), "local_pdf"))

    def test_cleans_staging_after_handled_publish_failure(self) -> None:
        pdf_path = self.records / "paper.pdf"
        pdf_path.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        with mock.patch(
            "socratic_learn.sources.ingest.publish_tracked_directory",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaises(FilesystemError):
                ingest_source(
                    self.records,
                    SourceRequest(str(pdf_path), "local_pdf"),
                )
        staging_dirs = list((self.records / "sources").glob(".staging-*"))
        self.assertEqual([], staging_dirs)

    def test_preserves_staging_on_identity_mismatch(self) -> None:
        from socratic_learn.safe_fs import PostMutationIdentityError

        pdf_path = self.records / "paper.pdf"
        pdf_path.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        with mock.patch(
            "socratic_learn.sources.ingest.publish_tracked_directory",
            side_effect=PostMutationIdentityError("ambiguous"),
        ):
            with self.assertRaises(IntegrityError):
                ingest_source(
                    self.records,
                    SourceRequest(str(pdf_path), "local_pdf"),
                )
        self.assertTrue(any((self.records / "sources").glob(".staging-*")))

    def test_preserves_staging_when_cleanup_identity_changes(self) -> None:
        from socratic_learn.safe_fs import IdentityMismatchError

        pdf_path = self.records / "paper.pdf"
        pdf_path.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        with mock.patch(
            "socratic_learn.sources.ingest.publish_tracked_directory",
            side_effect=OSError("disk full"),
        ), mock.patch(
            "socratic_learn.sources.ingest.remove_tracked_tree",
            side_effect=IdentityMismatchError("staging changed"),
        ):
            with self.assertRaises(IntegrityError) as context:
                ingest_source(
                    self.records,
                    SourceRequest(str(pdf_path), "local_pdf"),
                )
        self.assertIn("staging", str(context.exception).lower())
        self.assertTrue(any((self.records / "sources").glob(".staging-*")))


class LocalPdfIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.records = Path(self._temporary.name) / "records"
        self.records.mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    @unittest.skipUnless(os.name != "nt", "POSIX symlink identity regression")
    def test_rejects_symlink_path_without_following(self) -> None:
        target = self.records / "real.pdf"
        target.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        link = self.records / "linked.pdf"
        link.symlink_to(target)
        with self.assertRaises(SourceError):
            ingest_source(self.records, SourceRequest(str(link), "local_pdf"))

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point regression")
    def test_rejects_reparse_backed_local_pdf(self) -> None:
        vault = self.records / "vault"
        vault.mkdir()
        pdf_path = vault / "paper.pdf"
        pdf_path.write_bytes(build_text_pdf((_meaningful_page(), _meaningful_page("More"))))
        junction = self.records / "linked"
        import _winapi

        try:
            _winapi.CreateJunction(str(vault), str(junction))
        except OSError as error:
            self.skipTest(f"junction creation unavailable: {error}")
        with self.assertRaises(SourceError):
            ingest_source(self.records, SourceRequest(str(junction / "paper.pdf"), "local_pdf"))

    def test_rejects_identity_change_before_read(self) -> None:
        from socratic_learn.safe_fs import PathIdentity
        from socratic_learn.sources import ingest as ingest_module

        pdf_path = self.records / "paper.pdf"
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        pdf_path.write_bytes(raw)
        bogus = PathIdentity(0, 1)

        with mock.patch.object(ingest_module, "status_identity", return_value=bogus):
            with self.assertRaises(SourceError) as context:
                ingest_source(self.records, SourceRequest(str(pdf_path), "local_pdf"))
        self.assertIn("changed", str(context.exception).lower())


class HtmlBundleHeadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.records = Path(self._temporary.name) / "records"
        self.records.mkdir()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def test_url_bundle_uses_heading_labels_and_chunk_sequences(self) -> None:
        html = _pad_html(
            "<html><head><title>URL Article</title></head><body><article>"
            "<p>Lead paragraph before headings for the title section.</p>"
            "<h2>Section Alpha</h2><p>Alpha body with enough words for extraction.</p>"
            "<h2>Section Beta</h2><p>Beta body with enough words for extraction.</p>"
            "</article></body></html>"
        )
        raw = html.encode("utf-8")
        fetched = FetchedBytes(
            raw=raw,
            canonical_url="http://example.com/article",
            display_origin="http://example.com/article",
            media_type="text/html",
        )
        with mock.patch("socratic_learn.sources.ingest.fetch_url", return_value=fetched):
            result = ingest_source(
                self.records,
                SourceRequest("http://example.com/article", "url"),
            )
        index = (result.bundle_path / "index.md").read_text("utf-8")
        self.assertIn("URL Article / 1", index)
        self.assertIn("Section Alpha / 1", index)
        self.assertIn("Section Beta / 1", index)
        metadata = validate_source_bundle(result.bundle_path, result.source_id)
        self.assertGreaterEqual(metadata.section_count, 3)


if __name__ == "__main__":
    unittest.main()
