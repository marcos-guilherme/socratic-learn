from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from learning_tutor import PROTOCOL_VERSION
from learning_tutor.build import (
    CANONICAL_SOURCES,
    build_distribution,
    write_distribution,
)
from learning_tutor.errors import IntegrityError
from learning_tutor.export import export_prompt
from learning_tutor.manifest import sha256_bytes


class BuildTests(unittest.TestCase):
    def make_repository(self, *, newline: str = "\n") -> tuple[TemporaryDirectory, Path]:
        temporary = TemporaryDirectory()
        root = Path(temporary.name)
        contents = {
            "core/pedagogy.md": "# Pedagogy\n\nUniversal pedagogy.",
            "core/session-protocol.md": (
                "# Session Protocol\n\n"
                "## Session record contract\n\n"
                "# Session: YYYY-MM-DD — Topic\n"
                "## Outcome\n"
                "## Diagnostic evidence\n"
                "## Approved dependency path\n"
                "## Concepts established\n"
                "## Application evidence\n"
                "## Remaining gaps\n"
                "## Next step\n"
                "## Sources"
            ),
            "core/assessment.md": "# Assessment\n\nAssess relevant prerequisites.",
            "core/evidence-policy.md": "# Evidence Policy\n\nClassify claims.",
            "curricula/mathematics/map.md": (
                "# Mathematics\n\n"
                "### algebra — Algebra\n"
                "- Outcome: Solve equations.\n\n"
                "### calculus — Calculus\n"
                "- Outcome: Analyze change."
            ),
            "curricula/ai/map.md": (
                "# AI\n\n"
                "### learning — Learning\n"
                "- Outcome: Fit models."
            ),
        }
        for relative, content in contents.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("\n\n" + content + "\n\n").replace("\n", newline).encode())

        adapter = root / "adapters/cursor/README.md"
        adapter.parent.mkdir(parents=True)
        adapter.write_text(
            "CURSOR_ONLY: create .cursor/rules and invoke Cursor skills.\n",
            encoding="utf-8",
        )
        return temporary, root

    def test_identical_builds_return_identical_bytes(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        first = build_distribution(root)
        second = build_distribution(root)

        self.assertEqual(first.bundle, second.bundle)
        self.assertEqual(first.manifest, second.manifest)

    def test_crlf_sources_normalize_to_lf(self) -> None:
        temporary, root = self.make_repository(newline="\r\n")
        self.addCleanup(temporary.cleanup)

        result = build_distribution(root)

        self.assertNotIn(b"\r", result.bundle)
        self.assertNotIn(b"\r", result.manifest)

    def test_missing_source_reports_relative_path(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        missing = CANONICAL_SOURCES[2]
        (root / missing).unlink()

        with self.assertRaisesRegex(IntegrityError, missing.replace("/", r"\/")):
            build_distribution(root)

    def test_invalid_utf8_fails_with_relative_path(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        relative = CANONICAL_SOURCES[0]
        (root / relative).write_bytes(b"\xff")

        with self.assertRaisesRegex(IntegrityError, relative.replace("/", r"\/")):
            build_distribution(root)

    def test_absolute_source_path_is_rejected(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        absolute = str((root / CANONICAL_SOURCES[0]).resolve())

        with mock.patch("learning_tutor.build.CANONICAL_SOURCES", (absolute,)):
            with self.assertRaisesRegex(IntegrityError, "relative"):
                build_distribution(root)

    def test_header_contains_protocol_and_relative_sources(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertIn(f"Protocol: {PROTOCOL_VERSION}", text)
        for relative in CANONICAL_SOURCES:
            self.assertIn(f"- {relative}", text)
        self.assertNotIn(str(root), text)

    def test_bundle_has_exactly_one_trailing_newline(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        bundle = build_distribution(root).bundle

        self.assertTrue(bundle.endswith(b"\n"))
        self.assertFalse(bundle.endswith(b"\n\n"))

    def test_adapter_instructions_do_not_enter_bundle(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertNotIn("CURSOR_ONLY", text)
        self.assertNotIn(".cursor/rules", text)
        self.assertNotIn("invoke Cursor skills", text)

    def test_curriculum_maps_become_compact_heading_indexes(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertIn("- algebra — Algebra", text)
        self.assertIn("- learning — Learning", text)
        self.assertNotIn("- Outcome: Solve equations.", text)

    def test_manifest_hashes_match_normalized_sources_and_bundle(self) -> None:
        temporary, root = self.make_repository(newline="\r\n")
        self.addCleanup(temporary.cleanup)

        result = build_distribution(root)
        manifest = json.loads(result.manifest)

        self.assertEqual(sha256_bytes(result.bundle), manifest["bundle"]["sha256"])
        for entry in manifest["sources"]:
            source = (root / entry["path"]).read_text(encoding="utf-8")
            normalized = source.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"
            self.assertEqual(
                sha256_bytes(normalized.encode("utf-8")),
                entry["sha256"],
            )

    def test_write_distribution_writes_exact_dist_bytes(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)

        bundle_path, manifest_path = write_distribution(root, result)

        self.assertEqual(root / "dist/learning-tutor.prompt.md", bundle_path)
        self.assertEqual(root / "dist/manifest.json", manifest_path)
        self.assertEqual(result.bundle, bundle_path.read_bytes())
        self.assertEqual(result.manifest, manifest_path.read_bytes())

    def test_export_prompt_writes_exact_validated_bundle(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output = root / "out/prompt.md"

        export_prompt(output, root=root)

        self.assertEqual(result.bundle, output.read_bytes())

    def test_export_prompt_rejects_bundle_hash_mismatch(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        bundle_path, _ = write_distribution(root, result)
        bundle_path.write_bytes(b"tampered\n")

        with self.assertRaisesRegex(IntegrityError, "hash"):
            export_prompt(root=root)


if __name__ == "__main__":
    unittest.main()
