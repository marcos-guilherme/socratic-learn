from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.sanitize import (
    RedactionRule,
    assert_tracked_safe,
    sanitize_json,
    write_private,
)


class EvaluationSanitizeTests(unittest.TestCase):
    def test_recursive_redaction_preserves_json_shape(self) -> None:
        value = {
            "session_id": "provider-secret-id",
            "nested": ["C:/Users/Marcos/private", {"token": "Bearer abc123"}],
        }
        rules = (
            RedactionRule("provider-secret-id", "REDACTED_SESSION_ID"),
            RedactionRule("C:/Users/Marcos/private", "REDACTED_RUN_ROOT"),
            RedactionRule("Bearer abc123", "REDACTED_SECRET"),
        )
        self.assertEqual(
            {
                "session_id": "REDACTED_SESSION_ID",
                "nested": ["REDACTED_RUN_ROOT", {"token": "REDACTED_SECRET"}],
            },
            sanitize_json(value, rules),
        )

    def test_tracked_text_rejects_secret_and_absolute_home(self) -> None:
        with self.assertRaises(ValueError):
            assert_tracked_safe(
                "authorization: Bearer abc123\nC:\\Users\\Marcos\\private",
                forbidden_literals=("abc123",),
            )

    def test_private_write_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(ValueError):
                write_private(root.parent / "escape.txt", b"x", private_root=root)
