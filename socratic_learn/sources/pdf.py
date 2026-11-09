"""Deterministic PDF text extraction."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from socratic_learn.errors import SourceError
from socratic_learn.sources.model import ExtractedDocument, ExtractedSection
from socratic_learn.sources.normalize import MIN_NON_WHITESPACE_CODE_POINTS, normalize_text

PDF_SIGNATURE = b"%PDF-"
SIGNATURE_SCAN_BYTES = 1024
MAX_PDF_PAGES = 500

_OCR_REMEDIATION = "Provide a textual PDF export or re-scan with OCR outside Socratic Learn."
_SHORT_TEXT_REMEDIATION = "Choose a source with more extractable text."


def extract_pdf(raw: bytes, *, title: str) -> ExtractedDocument:
    """Extract labeled page sections from a textual PDF."""
    prefix = raw[:SIGNATURE_SCAN_BYTES]
    signature_at = prefix.find(PDF_SIGNATURE)
    if signature_at == -1:
        raise SourceError(
            "file is missing a PDF signature in the first 1024 bytes",
            remediation="Choose a regular PDF file.",
        )
    payload = raw[signature_at:]

    try:
        reader = PdfReader(BytesIO(payload), strict=False)
    except PdfReadError:
        raise SourceError(
            "PDF content could not be parsed",
            remediation="Repair or re-export the PDF, then try again.",
        ) from None
    except Exception:
        raise SourceError(
            "PDF content could not be parsed",
            remediation="Repair or re-export the PDF, then try again.",
        ) from None

    if reader.is_encrypted:
        password_result = reader.decrypt("")
        if password_result == 0:
            raise SourceError(
                "encrypted PDF requires a non-empty password",
                remediation="Remove encryption or export an unprotected copy.",
            )

    if len(reader.pages) > MAX_PDF_PAGES:
        raise SourceError(
            f"PDF exceeds the {MAX_PDF_PAGES}-page limit",
            remediation=f"Split the document to at most {MAX_PDF_PAGES} pages.",
        )

    sections: list[ExtractedSection] = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue
        normalized_page = normalize_text(page_text, require_meaningful=False)
        if normalized_page.strip():
            sections.append(ExtractedSection(label=f"Page {index}", text=normalized_page))

    combined = "\n\n".join(section.text for section in sections)
    if not combined.strip():
        raise SourceError(
            "PDF has no extractable text; scanned or image-only PDFs are not supported",
            remediation=_OCR_REMEDIATION,
        )

    normalize_text(combined, require_meaningful=False)
    non_whitespace = sum(1 for character in combined if not character.isspace())
    if non_whitespace < MIN_NON_WHITESPACE_CODE_POINTS:
        if non_whitespace < 40:
            raise SourceError(
                f"PDF has fewer than {MIN_NON_WHITESPACE_CODE_POINTS} extractable characters; "
                "scanned or image-only content is likely and OCR is not supported",
                remediation=_OCR_REMEDIATION,
            )
        raise SourceError(
            f"source has fewer than {MIN_NON_WHITESPACE_CODE_POINTS} meaningful characters",
            remediation=_SHORT_TEXT_REMEDIATION,
        )

    return ExtractedDocument(
        title=title,
        media_type="application/pdf",
        sections=tuple(sections),
    )
