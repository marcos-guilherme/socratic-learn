from __future__ import annotations

import unittest

from socratic_learn.errors import SourceError
from socratic_learn.sources.normalize import (
    DEFAULT_SECTION_CHUNK_LIMIT,
    MAX_NORMALIZED_CODE_POINTS,
    MIN_NON_WHITESPACE_CODE_POINTS,
    chunk_section,
    normalize_text,
)


def _meaningful_text(length: int) -> str:
    return ("word " * length).strip()


class NormalizeTextTests(unittest.TestCase):
    def test_applies_nfc_and_lf_line_endings(self) -> None:
        decomposed = "e\u0301\r\n"
        normalized = normalize_text(_meaningful_text(50) + "\n\n" + decomposed)
        self.assertIn("\u00e9\n", normalized)
        self.assertNotIn("\r", normalized)

    def test_collapses_horizontal_whitespace_and_preserves_paragraph_gap(self) -> None:
        text = "  leading\tand   trailing  \r\n\r\n\n\n\nsecond   paragraph  "
        text = _meaningful_text(50) + "\n\n" + text
        normalized = normalize_text(text)
        self.assertIn("\n\n", normalized)
        self.assertNotIn("   ", normalized)
        self.assertNotIn("\t", normalized)
        self.assertNotIn("\n\n\n", normalized)

    def test_rejects_fewer_than_two_hundred_non_whitespace_code_points(self) -> None:
        with self.assertRaises(SourceError):
            normalize_text("short text")

    def test_accepts_exactly_two_hundred_non_whitespace_code_points(self) -> None:
        text = "a" * MIN_NON_WHITESPACE_CODE_POINTS
        self.assertEqual(text, normalize_text(text))

    def test_rejects_more_than_five_million_normalized_code_points(self) -> None:
        text = "a" * (MAX_NORMALIZED_CODE_POINTS + 1)
        with self.assertRaises(SourceError):
            normalize_text(text)


class NormalizeTextFragmentTests(unittest.TestCase):
    def test_short_fragment_is_accepted_only_without_meaningful_requirement(self) -> None:
        fragment = "Page 1\r\n"
        with self.assertRaises(SourceError):
            normalize_text(fragment)
        self.assertEqual("Page 1\n", normalize_text(fragment, require_meaningful=False))

    def test_fragment_mode_applies_identical_transformation_steps(self) -> None:
        padding = _meaningful_text(50)
        body = "  spaced\twords  \r\n\r\n\n\nnext"
        full_text = f"{padding}\n\n{body}"
        padded = normalize_text(full_text)
        fragment = normalize_text(body, require_meaningful=False)
        suffix = padded.split("\n\n", 1)[1]
        self.assertEqual(suffix, fragment)

    def test_fragment_mode_still_rejects_maximum_size_overflow(self) -> None:
        text = "a" * (MAX_NORMALIZED_CODE_POINTS + 1)
        with self.assertRaises(SourceError):
            normalize_text(text, require_meaningful=False)


class ChunkSectionTests(unittest.TestCase):
    def test_returns_single_chunk_under_default_limit(self) -> None:
        text = _meaningful_text(100)
        chunks = chunk_section(text)
        self.assertEqual((text,), chunks)
        self.assertLessEqual(len(chunks[0]), DEFAULT_SECTION_CHUNK_LIMIT)

    def test_rejects_non_positive_limit(self) -> None:
        text = _meaningful_text(30)
        with self.assertRaises(SourceError):
            chunk_section(text, limit=0)

    def test_prefers_paragraph_boundaries(self) -> None:
        paragraph = "para " * 2000
        text = f"{paragraph}\n\n{paragraph}\n\n{paragraph}"
        chunks = chunk_section(text, limit=3500)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 3500)
        self.assertEqual(text, "".join(chunks))

    def test_splits_overlong_paragraph_at_unicode_whitespace(self) -> None:
        text = "x" + (" word" * 3000)
        chunks = chunk_section(text, limit=500)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 500)
        self.assertEqual(text, "".join(chunks))

    def test_allows_small_chunks_without_minimum_length(self) -> None:
        text = "a\n\n" + ("word " * 400)
        chunks = chunk_section(text, limit=30)
        self.assertTrue(any(len(chunk) < 200 for chunk in chunks))
        self.assertEqual(text, "".join(chunks))
