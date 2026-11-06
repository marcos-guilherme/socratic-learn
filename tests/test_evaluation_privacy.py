from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from evaluation.report import validate_baseline_report
from evaluation.sanitize import assert_tracked_safe


class EvaluationPrivacyTests(unittest.TestCase):
    def test_no_raw_semantic_run_is_tracked(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files", ".semantic-runs"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual([], tracked)

    def test_tracked_evaluation_assets_are_sanitized(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files", "evaluation"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        for relative in sorted(tracked):
            path = root / relative
            if path.suffix not in {".json", ".md", ".py"}:
                continue
            with self.subTest(path=relative):
                self.assertFalse(path.is_symlink())
                text = path.read_text(encoding="utf-8")
                assert_tracked_safe(text, forbidden_literals=())
                if relative.startswith("evaluation/reports/"):
                    validate_baseline_report(text)

    def test_canonical_protocol_is_not_an_evaluation_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        evaluation_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "evaluation").rglob("*.py")
        )
        self.assertNotIn("write_distribution(", evaluation_text)
