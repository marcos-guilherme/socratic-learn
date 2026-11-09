from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import unittest
from datetime import datetime, timezone
from pathlib import Path

from socratic_learn.errors import IntegrityError
from socratic_learn.sources.bundle import (
    BUNDLE_SCHEMA_VERSION,
    build_bundle_tree,
    canonical_metadata_bytes,
    validate_source_bundle,
)
from socratic_learn.sources.ids import source_id_for_local
from socratic_learn.sources.model import BundleMetadata, ExtractedDocument, ExtractedSection
from socratic_learn.sources.normalize import DEFAULT_SECTION_CHUNK_LIMIT
from tests.pdf_fixture import build_text_pdf

_SOURCE_ID = re.compile(r"^[0-9a-f]{64}$")


def _meaningful_page(prefix: str = "Evidence") -> str:
    return f"{prefix} paragraph. " + "word " * 45


class BundleLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _write_minimal_bundle(
        self, *, source_id: str | None = None, parent: Path | None = None
    ) -> Path:
        pages = (_meaningful_page(), _meaningful_page("More"))
        raw = build_text_pdf(pages)
        source_id = source_id or source_id_for_local(raw)
        base = parent or self.root
        bundle_path = base / source_id
        bundle_path.mkdir()
        extracted_at = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
        document = __import__(
            "socratic_learn.sources.pdf", fromlist=["extract_pdf"]
        ).extract_pdf(raw, title="paper.pdf")
        metadata = build_bundle_tree(
            bundle_path,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin="paper.pdf",
            extracted_at=extracted_at,
        )
        self.assertEqual(source_id, metadata.source_id)
        return bundle_path

    def test_exact_bundle_tree_and_lowercase_id(self) -> None:
        bundle_path = self._write_minimal_bundle()
        source_id = bundle_path.name
        self.assertRegex(source_id, _SOURCE_ID)
        entries = {path.name for path in bundle_path.iterdir()}
        self.assertEqual({"metadata.json", "index.md", "original.bin", "sections"}, entries)
        chunk_names = sorted(path.name for path in (bundle_path / "sections").iterdir())
        self.assertTrue(chunk_names)
        self.assertTrue(all(name.endswith(".txt") for name in chunk_names))

    def test_metadata_is_canonical_without_query_or_directory_paths(self) -> None:
        bundle_path = self._write_minimal_bundle()
        metadata_bytes = (bundle_path / "metadata.json").read_bytes()
        payload = json.loads(metadata_bytes.decode("utf-8"))
        serialized = canonical_metadata_bytes(
            BundleMetadata(
                schema_version=payload["schema_version"],
                source_id=payload["source_id"],
                title=payload["title"],
                display_origin=payload["display_origin"],
                media_type=payload["media_type"],
                raw_sha256=payload["raw_sha256"],
                extracted_at=datetime.fromisoformat(payload["extracted_at"]),
                section_count=payload["section_count"],
                normalized_characters=payload["normalized_characters"],
            )
        )
        self.assertEqual(metadata_bytes, serialized)
        text = metadata_bytes.decode("utf-8")
        self.assertNotIn("?", text)
        self.assertNotIn("\\", text)
        self.assertNotIn("nested", text)
        self.assertEqual("paper.pdf", payload["display_origin"])

    def test_chunks_use_utf8_lf_nfc_and_respect_size_limit(self) -> None:
        decomposed = "e\u0301" * 6000
        text = decomposed + "\r\n" + ("paragraph " * 3000)
        raw = b"%PDF-1.4\nplaceholder"
        source_id = source_id_for_local(raw)
        bundle_path = self.root / source_id
        bundle_path.mkdir()
        document = ExtractedDocument(
            title="chunky.pdf",
            media_type="application/pdf",
            sections=(ExtractedSection(label="Page 1", text=text.replace("\r\n", "\n")),),
        )
        build_bundle_tree(
            bundle_path,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin="chunky.pdf",
            extracted_at=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        )
        for chunk_path in sorted((bundle_path / "sections").glob("*.txt")):
            data = chunk_path.read_bytes()
            self.assertNotIn(b"\r", data)
            decoded = data.decode("utf-8")
            self.assertEqual(decoded, unicodedata.normalize("NFC", decoded))
            self.assertLessEqual(len(decoded), DEFAULT_SECTION_CHUNK_LIMIT)

    def test_index_lists_pdf_page_labels_with_chunk_sequence(self) -> None:
        raw = build_text_pdf((_meaningful_page("One"), _meaningful_page("Two")))
        source_id = source_id_for_local(raw)
        bundle_path = self.root / source_id
        bundle_path.mkdir()
        document = __import__(
            "socratic_learn.sources.pdf", fromlist=["extract_pdf"]
        ).extract_pdf(raw, title="two.pdf")
        build_bundle_tree(
            bundle_path,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin="two.pdf",
            extracted_at=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        )
        index = (bundle_path / "index.md").read_text("utf-8")
        self.assertIn("Page 1 / 1", index)
        self.assertIn("Page 2 / 1", index)
        self.assertIn("sections/0001.txt", index)
        self.assertIn("sections/0002.txt", index)

    def test_validate_returns_metadata_and_checks_raw_hash(self) -> None:
        bundle_path = self._write_minimal_bundle()
        metadata = validate_source_bundle(bundle_path, bundle_path.name)
        self.assertIsInstance(metadata, BundleMetadata)
        self.assertEqual(BUNDLE_SCHEMA_VERSION, metadata.schema_version)
        raw = (bundle_path / "original.bin").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), metadata.raw_sha256)

    def test_rejects_source_id_mismatch_and_malformed_id(self) -> None:
        bundle_path = self._write_minimal_bundle()
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, "A" * 64)
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, "not-hex")

    def test_rejects_missing_entries_and_extra_files(self) -> None:
        bundle_path = self._write_minimal_bundle()
        shutil.rmtree(bundle_path / "sections")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)
        scratch = self.root / "extra-case"
        scratch.mkdir()
        bundle_path = self._write_minimal_bundle(parent=scratch)
        (bundle_path / "extra.txt").write_text("nope", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    def test_rejects_chunk_gaps_and_oversize_chunks(self) -> None:
        gap_root = self.root / "gap-case"
        gap_root.mkdir()
        bundle_path = self._write_minimal_bundle(parent=gap_root)
        (bundle_path / "sections" / "0003.txt").write_text("gap", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)
        oversize_root = self.root / "oversize-case"
        oversize_root.mkdir()
        bundle_path = self._write_minimal_bundle(parent=oversize_root)
        oversized = "x" * (DEFAULT_SECTION_CHUNK_LIMIT + 1)
        (bundle_path / "sections" / "0001.txt").write_text(oversized, encoding="utf-8")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    def test_rejects_noncanonical_metadata_and_private_path_fields(self) -> None:
        bundle_path = self._write_minimal_bundle()
        metadata_path = bundle_path / "metadata.json"
        payload = json.loads(metadata_path.read_text("utf-8"))
        payload["canonical_url"] = "https://example.com?secret=1"
        metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)
        private_root = self.root / "private-case"
        private_root.mkdir()
        bundle_path = self._write_minimal_bundle(parent=private_root)
        payload = json.loads((bundle_path / "metadata.json").read_text("utf-8"))
        payload["display_origin"] = r"C:\secret\paper.pdf"
        (bundle_path / "metadata.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    def test_rejects_invalid_timestamp_and_wrong_media_type(self) -> None:
        timestamp_root = self.root / "timestamp-case"
        timestamp_root.mkdir()
        bundle_path = self._write_minimal_bundle(parent=timestamp_root)
        payload = json.loads((bundle_path / "metadata.json").read_text("utf-8"))
        payload["extracted_at"] = "2026-11-08T12:00:00"
        (bundle_path / "metadata.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)
        media_root = self.root / "media-case"
        media_root.mkdir()
        bundle_path = self._write_minimal_bundle(parent=media_root)
        payload = json.loads((bundle_path / "metadata.json").read_text("utf-8"))
        payload["media_type"] = "text/plain"
        (bundle_path / "metadata.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    def test_accepts_legitimate_title_with_token_substring(self) -> None:
        raw = build_text_pdf((_meaningful_page(), _meaningful_page("More")))
        source_id = source_id_for_local(raw)
        bundle_root = self.root / "title-token"
        bundle_root.mkdir()
        document = ExtractedDocument(
            title="Token Economy Primer",
            media_type="application/pdf",
            sections=(
                ExtractedSection(label="Page 1", text=_meaningful_page()),
                ExtractedSection(label="Page 2", text=_meaningful_page("More")),
            ),
        )
        build_bundle_tree(
            bundle_root,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin="token-primer.pdf",
            extracted_at=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        )
        metadata = validate_source_bundle(bundle_root, source_id)
        self.assertEqual("Token Economy Primer", metadata.title)

    def test_rejects_tampered_normalized_character_count(self) -> None:
        bundle_path = self._write_minimal_bundle()
        payload = json.loads((bundle_path / "metadata.json").read_text("utf-8"))
        payload["normalized_characters"] = payload["normalized_characters"] + 10
        (bundle_path / "metadata.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError) as context:
            validate_source_bundle(bundle_path, bundle_path.name)
        self.assertIn("normalized_characters", str(context.exception))

    def test_rejects_tampered_section_count(self) -> None:
        bundle_path = self._write_minimal_bundle()
        payload = json.loads((bundle_path / "metadata.json").read_text("utf-8"))
        payload["section_count"] = payload["section_count"] + 1
        (bundle_path / "metadata.json").write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError) as context:
            validate_source_bundle(bundle_path, bundle_path.name)
        self.assertIn("section_count", str(context.exception))

    def test_rejects_index_sequence_not_starting_at_one(self) -> None:
        bundle_path = self._write_minimal_bundle()
        index_path = bundle_path / "index.md"
        index_text = index_path.read_text("utf-8")
        index_path.write_text(
            index_text.replace("Page 1 / 1", "Page 1 / 2", 1),
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    def test_rejects_index_sequence_gap_within_section(self) -> None:
        raw = build_text_pdf((_meaningful_page("One"),))
        long_text = _meaningful_page("Chunky") + (" overflow " * 2500)
        source_id = source_id_for_local(raw)
        bundle_path = self.root / "sequence-gap" / source_id
        bundle_path.mkdir(parents=True)
        document = ExtractedDocument(
            title="chunky.pdf",
            media_type="application/pdf",
            sections=(ExtractedSection(label="Page 1", text=long_text),),
        )
        build_bundle_tree(
            bundle_path,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin="chunky.pdf",
            extracted_at=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        )
        index = (bundle_path / "index.md").read_text("utf-8")
        (bundle_path / "index.md").write_text(
            index.replace("Page 1 / 2", "Page 1 / 4", 1),
            encoding="utf-8",
        )
        with self.assertRaises(IntegrityError) as context:
            validate_source_bundle(bundle_path, source_id)
        self.assertIn("contiguous", str(context.exception))

    @unittest.skipUnless(os.name != "nt", "POSIX symlink regression")
    def test_rejects_symlinked_chunk_file(self) -> None:
        bundle_path = self._write_minimal_bundle()
        real = bundle_path / "sections" / "0001.txt"
        payload = real.read_text("utf-8")
        real.unlink()
        decoy = bundle_path / "sections" / "decoy.txt"
        decoy.write_text(payload, encoding="utf-8")
        (bundle_path / "sections" / "0001.txt").symlink_to(decoy)
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)

    @unittest.skipUnless(os.name == "nt", "Windows reparse-point regression")
    def test_rejects_reparse_backed_sections_directory(self) -> None:
        bundle_path = self._write_minimal_bundle()
        external = self.root / "external-sections"
        external.mkdir()
        for chunk in (bundle_path / "sections").iterdir():
            shutil.copy2(chunk, external / chunk.name)
        shutil.rmtree(bundle_path / "sections")
        junction = bundle_path / "sections"
        junction_result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(external)],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction_result.returncode != 0:
            self.skipTest("junction creation unavailable")
        with self.assertRaises(IntegrityError):
            validate_source_bundle(bundle_path, bundle_path.name)


if __name__ == "__main__":
    unittest.main()
