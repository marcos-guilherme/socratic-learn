from __future__ import annotations

import unittest
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from socratic_learn.errors import SourceError
from socratic_learn.sources.model import ExtractedDocument
from socratic_learn.sources.pdf import extract_pdf
from tests.pdf_fixture import build_text_pdf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"


def _meaningful_page(prefix: str = "Evidence") -> str:
    return f"{prefix} paragraph. " + "word " * 45


def _long_document(pages: int = 2) -> bytes:
    return build_text_pdf(tuple(_meaningful_page("Evidence") for _ in range(pages)))


class PdfSignatureTests(unittest.TestCase):
    def test_accepts_pdf_signature_within_first_1024_bytes(self) -> None:
        raw = b"x" * 512 + _long_document(2)
        document = extract_pdf(raw, title="offset.pdf")
        self.assertIsInstance(document, ExtractedDocument)
        self.assertEqual("application/pdf", document.media_type)

    def test_rejects_missing_pdf_signature_beyond_first_1024_bytes(self) -> None:
        raw = b"x" * 1024 + b"%PDF-1.4\n"
        with self.assertRaises(SourceError) as context:
            extract_pdf(raw, title="missing.pdf")
        self.assertNotIn("Traceback", str(context.exception))


class PdfTextualExtractionTests(unittest.TestCase):
    def test_extracts_textual_pages_with_stable_labels(self) -> None:
        raw = _long_document(2)
        document = extract_pdf(raw, title="paper.pdf")
        self.assertEqual("paper.pdf", document.title)
        self.assertEqual("application/pdf", document.media_type)
        self.assertEqual(("Page 1", "Page 2"), tuple(section.label for section in document.sections))
        self.assertIn("Evidence", document.sections[0].text)

    def test_reads_committed_minimal_fixture(self) -> None:
        raw = (FIXTURES / "minimal-text.pdf").read_bytes()
        document = extract_pdf(raw, title="minimal-text.pdf")
        self.assertGreaterEqual(len(document.sections), 1)
        combined = "\n".join(section.text for section in document.sections)
        self.assertIn("Evidence", combined)


class PdfFailureTests(unittest.TestCase):
    def test_rejects_malformed_pdf_with_sanitized_error(self) -> None:
        with self.assertRaises(SourceError) as context:
            extract_pdf(b"%PDF-1.4\nnot a real pdf", title="broken.pdf")
        message = str(context.exception)
        self.assertNotRegex(message, r"(?i)pypdf|pdfreader|bytesio")
        self.assertIn("remediation:", message)

    def test_permits_empty_password_decryption(self) -> None:
        raw = (FIXTURES / "encrypted.pdf").read_bytes()
        document = extract_pdf(raw, title="encrypted.pdf")
        combined = "\n".join(section.text for section in document.sections)
        self.assertIn("Encrypted page content", combined)

    def test_rejects_non_empty_encryption_password(self) -> None:
        base = build_text_pdf((_meaningful_page(),))
        reader = PdfReader(BytesIO(base))
        writer = PdfWriter()
        writer.append(reader)
        writer.encrypt(user_password="secret", owner_password="owner")
        buffer = BytesIO()
        writer.write(buffer)
        with self.assertRaises(SourceError) as context:
            extract_pdf(buffer.getvalue(), title="locked.pdf")
        self.assertIn("encrypt", str(context.exception).lower())

    def test_rejects_more_than_five_hundred_pages_before_extraction(self) -> None:
        raw = build_text_pdf(tuple("x" for _ in range(501)))
        with self.assertRaises(SourceError) as context:
            extract_pdf(raw, title="huge.pdf")
        self.assertIn("500", str(context.exception))

    def test_rejects_image_only_pdf_with_ocr_guidance(self) -> None:
        raw = (FIXTURES / "image-only.pdf").read_bytes()
        with self.assertRaises(SourceError) as context:
            extract_pdf(raw, title="scan.pdf")
        message = str(context.exception).lower()
        self.assertIn("ocr", message)

    def test_rejects_under_two_hundred_characters_across_pages(self) -> None:
        raw = build_text_pdf(("short",))
        with self.assertRaises(SourceError) as context:
            extract_pdf(raw, title="tiny.pdf")
        self.assertIn("200", str(context.exception))


if __name__ == "__main__":
    unittest.main()
