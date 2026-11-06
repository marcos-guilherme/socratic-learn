from __future__ import annotations

import contextlib
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from socratic_learn import PROTOCOL_VERSION
from socratic_learn.build import (
    CANONICAL_SOURCES,
    build_distribution,
    write_distribution,
)
from socratic_learn.__main__ import main
from socratic_learn.errors import CollisionError, FilesystemError, IntegrityError
from socratic_learn.export import export_prompt
from socratic_learn.manifest import sha256_bytes


class BuildTests(unittest.TestCase):
    def make_repository(self, *, newline: str = "\n") -> tuple[TemporaryDirectory, Path]:
        temporary = TemporaryDirectory()
        root = Path(temporary.name)
        contents = {
            "core/pedagogy.md": (
                "# Pedagogy\n\n"
                "Universal pedagogy.\n\n"
                "## Responsive Socratic dialogue\n\n"
                "Each question derives from the learner's preceding answer.\n"
                "Use direct exposition when information is not deducible. "
                "After exposition, return control through an active application."
            ),
            "core/session-protocol.md": (
                "# Session Protocol\n\n"
                "## 1. Define an observable outcome\n\n"
                "Set a performance that can be observed.\n\n"
                "## 2. Diagnose relevant prerequisites\n\n"
                "Diagnose only relevant prerequisites.\n\n"
                "## 3. Present and approve a dependency path\n\n"
                "Wait until the learner approves the path.\n\n"
                "## 4. Teach one node at a time\n\n"
                "Teach one approved node.\n\n"
                "## 5. Close and persist\n\n"
                "Close with diagnostic evidence, application evidence, and remaining gaps.\n"
                "Keep private state under workspace/ and out of version control.\n\n"
                "## Capability fallbacks\n\n"
                "Without structured quiz support, ask conversational questions.\n"
                "Without web access, mark claims unverified.\n"
                "Without filesystem access, return a Markdown record.\n"
                "Without subagents or parallel work, research sequentially.\n"
                "Without diagram rendering, use a textual edge list.\n"
                "Without cross-session memory, ask for a prior summary.\n\n"
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
            "core/assessment.md": (
                "# Assessment\n\n"
                "Use at most six diagnostic questions and stop early when evidence "
                "is sufficient."
            ),
            "core/evidence-policy.md": (
                "# Evidence Policy\n\n"
                "For mathematical claims, state the domain and hypotheses and classify "
                "each as a definition, theorem, or approximation.\n"
                "For volatile claims, verify against a primary source."
            ),
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

    def test_lf_and_crlf_repositories_build_byte_identically(self) -> None:
        lf_temporary, lf_root = self.make_repository(newline="\n")
        crlf_temporary, crlf_root = self.make_repository(newline="\r\n")
        self.addCleanup(lf_temporary.cleanup)
        self.addCleanup(crlf_temporary.cleanup)

        self.assertEqual(
            build_distribution(lf_root),
            build_distribution(crlf_root),
        )

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

        with mock.patch("socratic_learn.build.CANONICAL_SOURCES", (absolute,)):
            with self.assertRaisesRegex(IntegrityError, "relative"):
                build_distribution(root)

    def test_source_symlink_cannot_escape_repository(self) -> None:
        temporary, root = self.make_repository()
        outside_temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(outside_temporary.cleanup)
        relative = CANONICAL_SOURCES[0]
        source = root / relative
        outside = Path(outside_temporary.name) / "outside.md"
        outside.write_text("# Escaped\n", encoding="utf-8")
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"file symlinks unavailable: {error}")

        with self.assertRaises(IntegrityError) as raised:
            build_distribution(root)

        self.assertIn(relative, str(raised.exception))
        self.assertIn("repository", str(raised.exception))
        self.assertTrue(raised.exception.remediation)

    def test_header_contains_protocol_and_relative_sources(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertTrue(text.startswith("# Socratic Learn\n"))
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

    def test_malformed_curriculum_node_heading_rejects_entire_build(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        curriculum = root / "curricula/ai/map.md"
        curriculum.write_text(
            curriculum.read_text(encoding="utf-8")
            + "\n### Unsupported heading without identifier separator\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(IntegrityError, "curriculum node heading"):
            build_distribution(root)

    def test_indented_level_three_curriculum_heading_is_indexed(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        curriculum = root / "curricula/ai/map.md"
        curriculum.write_text(
            curriculum.read_text(encoding="utf-8").replace(
                "### learning — Learning",
                "   ### learning — Learning",
            ),
            encoding="utf-8",
        )

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertIn("- learning — Learning", text)

    def test_malformed_indented_level_three_heading_is_rejected(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        curriculum = root / "curricula/ai/map.md"
        curriculum.write_text(
            curriculum.read_text(encoding="utf-8")
            + "\n  ### malformed node heading\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(IntegrityError, "curriculum node heading"):
            build_distribution(root)

    def test_level_four_heading_is_ignored_by_curriculum_index(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        curriculum = root / "curricula/ai/map.md"
        curriculum.write_text(
            curriculum.read_text(encoding="utf-8")
            + "\n#### implementation detail\n",
            encoding="utf-8",
        )

        text = build_distribution(root).bundle.decode("utf-8")

        self.assertIn("- learning — Learning", text)

    def test_manifest_hashes_match_normalized_sources_and_bundle(self) -> None:
        temporary, root = self.make_repository(newline="\r\n")
        lf_temporary, lf_root = self.make_repository(newline="\n")
        self.addCleanup(temporary.cleanup)
        self.addCleanup(lf_temporary.cleanup)

        result = build_distribution(root)
        manifest = json.loads(result.manifest)
        lf_manifest = json.loads(build_distribution(lf_root).manifest)

        self.assertEqual(sha256_bytes(result.bundle), manifest["bundle"]["sha256"])
        self.assertEqual(lf_manifest["sources"], manifest["sources"])
        self.assertEqual(
            sha256_bytes(
                b"# Pedagogy\n\n"
                b"Universal pedagogy.\n\n"
                b"## Responsive Socratic dialogue\n\n"
                b"Each question derives from the learner's preceding answer.\n"
                b"Use direct exposition when information is not deducible. "
                b"After exposition, return control through an active application.\n"
            ),
            manifest["sources"][0]["sha256"],
        )

    def test_write_distribution_writes_exact_dist_bytes(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)

        bundle_path, manifest_path = write_distribution(root, result)

        self.assertEqual(root / "dist/socratic-learn.prompt.md", bundle_path)
        self.assertEqual(root / "dist/manifest.json", manifest_path)
        self.assertEqual(result.bundle, bundle_path.read_bytes())
        self.assertEqual(result.manifest, manifest_path.read_bytes())

    def test_write_distribution_rejects_symlinked_dist(self) -> None:
        temporary, root = self.make_repository()
        outside_temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(outside_temporary.cleanup)
        outside = Path(outside_temporary.name)
        try:
            (root / "dist").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks unavailable: {error}")

        with self.assertRaises(IntegrityError) as raised:
            write_distribution(root, build_distribution(root))

        self.assertIn("dist", str(raised.exception))
        self.assertTrue(raised.exception.remediation)
        self.assertEqual([], list(outside.iterdir()))

    def test_second_artifact_write_failure_preserves_old_distribution(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        old_result = build_distribution(root)
        bundle_path, manifest_path = write_distribution(root, old_result)
        old_bytes = (bundle_path.read_bytes(), manifest_path.read_bytes())
        pedagogy = root / CANONICAL_SOURCES[0]
        pedagogy.write_text(
            pedagogy.read_text(encoding="utf-8") + "\nChanged.\n",
            encoding="utf-8",
        )
        new_result = build_distribution(root)
        real_write = __import__(
            "socratic_learn.build", fromlist=["_atomic_write"]
        )._atomic_write
        calls = 0

        def fail_second(path: Path, data: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise FilesystemError(
                    "injected second artifact failure",
                    path=path,
                    remediation="retry the build",
                )
            real_write(path, data)

        with mock.patch("socratic_learn.build._atomic_write", side_effect=fail_second):
            with self.assertRaises(FilesystemError) as raised:
                write_distribution(root, new_result)

        self.assertIn("manifest.json", str(raised.exception.path))
        self.assertTrue(raised.exception.remediation)
        self.assertEqual(old_bytes[0], bundle_path.read_bytes())
        self.assertEqual(old_bytes[1], manifest_path.read_bytes())

    def test_public_filesystem_failures_include_path_and_remediation(self) -> None:
        def source_read_case(root: Path):
            patcher = mock.patch.object(
                Path,
                "read_bytes",
                autospec=True,
                side_effect=OSError("source read denied"),
            )
            return patcher, lambda: build_distribution(root), "core/pedagogy.md"

        def stage_write_case(root: Path):
            result = build_distribution(root)
            patcher = mock.patch(
                "socratic_learn.build.tempfile.NamedTemporaryFile",
                side_effect=OSError("stage write denied"),
            )
            return patcher, lambda: write_distribution(root, result), "prompt.md"

        def distribution_operation_case(root: Path):
            result = build_distribution(root)
            patcher = mock.patch(
                "socratic_learn.build.tempfile.mkdtemp",
                side_effect=OSError("stage directory denied"),
            )
            return patcher, lambda: write_distribution(root, result), "dist"

        def manifest_read_case(root: Path):
            result = build_distribution(root)
            write_distribution(root, result)
            patcher = mock.patch.object(
                Path,
                "read_bytes",
                autospec=True,
                side_effect=OSError("manifest read denied"),
            )
            return patcher, lambda: export_prompt(root=root), "manifest.json"

        def bundle_read_case(root: Path):
            result = build_distribution(root)
            write_distribution(root, result)
            real_read = Path.read_bytes

            def fail_bundle(path: Path) -> bytes:
                if path.name == "socratic-learn.prompt.md":
                    raise OSError("bundle read denied")
                return real_read(path)

            patcher = mock.patch.object(
                Path,
                "read_bytes",
                autospec=True,
                side_effect=fail_bundle,
            )
            return patcher, lambda: export_prompt(root=root), "prompt.md"

        def output_parent_case(root: Path):
            result = build_distribution(root)
            write_distribution(root, result)
            output = root / "out/prompt.md"
            patcher = mock.patch.object(
                Path,
                "mkdir",
                autospec=True,
                side_effect=OSError("output parent denied"),
            )
            return patcher, lambda: export_prompt(output, root=root), "out"

        def output_write_case(root: Path):
            result = build_distribution(root)
            write_distribution(root, result)
            output = root / "prompt-copy.md"
            patcher = mock.patch(
                "socratic_learn.build.tempfile.NamedTemporaryFile",
                side_effect=OSError("output write denied"),
            )
            return patcher, lambda: export_prompt(output, root=root), "prompt-copy.md"

        cases = (
            ("source read", source_read_case),
            ("staged artifact write", stage_write_case),
            ("distribution operation", distribution_operation_case),
            ("manifest artifact read", manifest_read_case),
            ("bundle artifact read", bundle_read_case),
            ("output parent creation", output_parent_case),
            ("output write", output_write_case),
        )
        for name, prepare in cases:
            with self.subTest(path=name):
                temporary, root = self.make_repository()
                try:
                    patcher, operation, expected_path = prepare(root)
                    with patcher:
                        with self.assertRaises(FilesystemError) as raised:
                            operation()
                    self.assertIn(expected_path, str(raised.exception.path))
                    self.assertTrue(raised.exception.remediation)
                finally:
                    temporary.cleanup()

    @unittest.skipUnless(__import__("os").name == "nt", "requires Windows handle rename")
    def test_directory_swap_failure_rolls_back_complete_old_distribution(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        old_result = build_distribution(root)
        bundle_path, manifest_path = write_distribution(root, old_result)
        old_bytes = (bundle_path.read_bytes(), manifest_path.read_bytes())
        assessment = root / CANONICAL_SOURCES[2]
        assessment.write_text(
            assessment.read_text(encoding="utf-8") + "\nChanged.\n",
            encoding="utf-8",
        )
        new_result = build_distribution(root)
        safe_fs = __import__(
            "socratic_learn.safe_fs",
            fromlist=["_windows_handle_rename_no_replace"],
        )
        real_replace = safe_fs._windows_handle_rename_no_replace
        injected = False

        def fail_new_directory(source_descriptor, destination: Path) -> None:
            nonlocal injected
            if not injected and destination.name == "dist":
                injected = True
                raise OSError("injected directory swap failure")
            real_replace(source_descriptor, destination)

        with mock.patch(
            "socratic_learn.safe_fs._windows_handle_rename_no_replace",
            side_effect=fail_new_directory,
        ):
            with self.assertRaisesRegex(FilesystemError, "swap") as raised:
                write_distribution(root, new_result)

        self.assertIn("dist", str(raised.exception.path))
        self.assertTrue(raised.exception.remediation)
        self.assertEqual(old_bytes[0], bundle_path.read_bytes())
        self.assertEqual(old_bytes[1], manifest_path.read_bytes())

    def test_dist_swap_preserves_raced_directory_replacement(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        old_result = build_distribution(root)
        write_distribution(root, old_result)
        dist = root / "dist"
        detached = root / "detached-dist"
        injected = False

        def replace_dist_before_backup(source, destination):
            nonlocal injected
            if (
                not injected
                and source == dist
                and Path(destination).name.startswith(".dist-backup-")
            ):
                injected = True
                dist.rename(detached)
                dist.mkdir()
                (dist / "external.txt").write_bytes(b"external dist winner")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_replace",
                side_effect=replace_dist_before_backup,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            write_distribution(root, old_result)

        self.assertEqual(b"external dist winner", (dist / "external.txt").read_bytes())
        self.assertTrue((detached / "manifest.json").is_file())
        self.assertIn("preserv", str(raised.exception).lower())

    def test_dist_backup_cleanup_preserves_raced_replacement(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        detached = root / "detached-backup"
        replacement: Path | None = None

        def replace_backup_before_cleanup(directory):
            nonlocal replacement
            backup = directory.path
            if backup.name.startswith(".dist-backup-"):
                backup.rename(detached)
                backup.mkdir()
                replacement = backup
                (backup / "external.txt").write_bytes(b"external backup winner")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_identity_cleanup",
                side_effect=replace_backup_before_cleanup,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            write_distribution(root, result)

        assert replacement is not None
        self.assertEqual(
            b"external backup winner",
            (replacement / "external.txt").read_bytes(),
        )
        self.assertTrue(detached.is_dir())
        self.assertIn(str(replacement), str(raised.exception))

    def test_dist_backup_with_unknown_content_is_preserved(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        unknown = root / "dist/user-owned.txt"
        unknown.write_bytes(b"user owned")

        with self.assertRaisesRegex(FilesystemError, "preserv") as raised:
            write_distribution(root, result)

        backups = [
            path for path in root.iterdir() if path.name.startswith(".dist-backup-")
        ]
        self.assertEqual(1, len(backups))
        self.assertEqual(b"user owned", (backups[0] / "user-owned.txt").read_bytes())
        self.assertIn(str(backups[0]), str(raised.exception))

    def test_dist_with_symlink_child_is_preserved_before_replacement(self) -> None:
        temporary, root = self.make_repository()
        outside_temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(outside_temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        dist = root / "dist"
        outside = Path(outside_temporary.name) / "outside.txt"
        outside.write_bytes(b"outside")
        link = dist / "user-link"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"file symlinks/reparse points unavailable: {error}")

        with self.assertRaises(FilesystemError) as raised:
            write_distribution(root, result)

        self.assertTrue(link.is_symlink())
        self.assertEqual(b"outside", outside.read_bytes())
        self.assertEqual(dist, raised.exception.path)
        self.assertIn(str(dist), raised.exception.remediation or "")
        self.assertIn("ownership", raised.exception.remediation or "")
        self.assertFalse(
            any(path.name.startswith(".dist-backup-") for path in root.iterdir())
        )

    def test_untrackable_dist_reports_preserved_recovery_path_without_assertion(
        self,
    ) -> None:
        for reason in (
            "tracked tree contains a link or reparse point",
            "tracked tree contains an unsupported entry type",
        ):
            with self.subTest(reason=reason):
                temporary, root = self.make_repository()
                try:
                    result = build_distribution(root)
                    write_distribution(root, result)
                    dist = root / "dist"
                    real_track = __import__(
                        "socratic_learn.build",
                        fromlist=["track_directory"],
                    ).track_directory

                    def reject_untrackable(path: Path):
                        if path == dist or path.name.startswith(".dist-backup-"):
                            raise OSError(reason)
                        return real_track(path)

                    with mock.patch(
                        "socratic_learn.build.track_directory",
                        side_effect=reject_untrackable,
                    ):
                        with self.assertRaises(FilesystemError) as raised:
                            write_distribution(root, result)

                    self.assertEqual(dist, raised.exception.path)
                    self.assertIn(str(dist), raised.exception.remediation or "")
                    self.assertIn("ownership", raised.exception.remediation or "")
                    self.assertTrue((dist / "manifest.json").is_file())
                    self.assertFalse(
                        any(
                            path.name.startswith(".dist-backup-")
                            for path in root.iterdir()
                        )
                    )
                finally:
                    temporary.cleanup()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_dist_with_unsupported_child_type_is_preserved_before_replacement(
        self,
    ) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        dist = root / "dist"
        unsupported = dist / "user-fifo"
        os.mkfifo(unsupported)

        with self.assertRaises(FilesystemError) as raised:
            write_distribution(root, result)

        self.assertTrue(unsupported.exists())
        self.assertEqual(dist, raised.exception.path)
        self.assertIn(str(dist), raised.exception.remediation or "")
        self.assertIn("unsupported", raised.exception.remediation or "")
        self.assertFalse(
            any(path.name.startswith(".dist-backup-") for path in root.iterdir())
        )

    def test_dist_backup_unknown_child_at_cleanup_preserves_complete_tree(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        inserted: Path | None = None

        def insert_unknown(directory) -> None:
            nonlocal inserted
            if directory.path.name.startswith(".dist-backup-"):
                inserted = directory.path / "external.txt"
                inserted.write_bytes(b"external")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_identity_cleanup",
                side_effect=insert_unknown,
            ),
            self.assertRaisesRegex(FilesystemError, "cleanup"),
        ):
            write_distribution(root, result)

        assert inserted is not None
        self.assertEqual(b"external", inserted.read_bytes())
        self.assertTrue((inserted.parent / "manifest.json").is_file())
        self.assertTrue((inserted.parent / "socratic-learn.prompt.md").is_file())

    def test_export_prompt_writes_exact_validated_bundle(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output = root / "out/prompt.md"

        export_prompt(output, root=root)

        self.assertEqual(result.bundle, output.read_bytes())

    def test_export_rejects_existing_output_without_overwrite(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output = root / "prompt.md"
        output.write_bytes(b"existing")

        with self.assertRaises(CollisionError):
            export_prompt(output, root=root)

        self.assertEqual(b"existing", output.read_bytes())

    def test_export_raced_output_is_preserved(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output = root / "out/prompt.md"

        def race_output(_source: Path, destination: Path) -> None:
            if destination == output:
                output.write_bytes(b"race winner")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_replace",
                side_effect=race_output,
            ),
            self.assertRaises(CollisionError),
        ):
            export_prompt(output, root=root)

        self.assertEqual(b"race winner", output.read_bytes())

    def test_export_parent_replacement_is_not_adopted(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output_parent = root / "out"
        output_parent.mkdir()
        output = output_parent / "prompt.md"
        detached = root / "detached-out"
        build_module = __import__("socratic_learn.build", fromlist=["_atomic_write"])
        real_write = build_module._atomic_write

        def replace_parent(path: Path, data: bytes, **kwargs: object) -> None:
            output_parent.rename(detached)
            output_parent.mkdir()
            (output_parent / "external.txt").write_bytes(b"external")
            real_write(path, data, **kwargs)

        with (
            mock.patch(
                "socratic_learn.export._atomic_write",
                side_effect=replace_parent,
            ),
            self.assertRaises(FilesystemError),
        ):
            export_prompt(output, root=root)

        self.assertEqual(
            b"external",
            (output_parent / "external.txt").read_bytes(),
        )
        self.assertFalse(output.exists())
        self.assertFalse((detached / "prompt.md").exists())

    def test_export_output_must_remain_inside_repository(self) -> None:
        temporary, root = self.make_repository()
        outside_temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(outside_temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)
        output = Path(outside_temporary.name) / "prompt.md"

        with self.assertRaises(IntegrityError) as raised:
            export_prompt(output, root=root)

        self.assertIn("repository", str(raised.exception))
        self.assertTrue(raised.exception.remediation)
        self.assertFalse(output.exists())

    def test_export_prompt_writes_exact_bundle_bytes_to_stdout(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        write_distribution(root, result)

        stdout = mock.Mock()
        stdout.buffer = BytesIO()
        with mock.patch("socratic_learn.export.sys.stdout", stdout):
            export_prompt(root=root)

        self.assertEqual(result.bundle, stdout.buffer.getvalue())

    def test_export_prompt_rejects_bundle_hash_mismatch(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        result = build_distribution(root)
        bundle_path, _ = write_distribution(root, result)
        bundle_path.write_bytes(b"tampered\n")

        with self.assertRaisesRegex(IntegrityError, "hash"):
            export_prompt(root=root)

    def test_cli_stdout_io_failures_return_actionable_filesystem_error(self) -> None:
        class FailingTextStdout:
            def __init__(self, operation: str) -> None:
                self.operation = operation

            def write(self, data: str) -> int:
                if self.operation == "write":
                    raise BrokenPipeError("injected text write failure")
                return len(data)

            def flush(self) -> None:
                if self.operation == "flush":
                    raise OSError("injected text flush failure")

        class FailingBinaryBuffer:
            def __init__(self, operation: str) -> None:
                self.operation = operation

            def write(self, data: bytes) -> int:
                if self.operation == "write":
                    raise BrokenPipeError("injected binary write failure")
                return len(data)

            def flush(self) -> None:
                if self.operation == "flush":
                    raise OSError("injected binary flush failure")

        class BinaryStdout:
            def __init__(self, operation: str) -> None:
                self.buffer = FailingBinaryBuffer(operation)

        for command, operation in (
            ("build", "write"),
            ("build", "flush"),
            ("export", "write"),
            ("export", "flush"),
        ):
            with self.subTest(command=command, operation=operation):
                temporary, root = self.make_repository()
                try:
                    if command == "export":
                        write_distribution(root, build_distribution(root))
                    stderr = StringIO()
                    stdout = (
                        FailingTextStdout(operation)
                        if command == "build"
                        else BinaryStdout(operation)
                    )
                    cwd_patch = mock.patch(
                        f"socratic_learn.{command}.Path.cwd",
                        return_value=root,
                    )
                    stdout_patch = mock.patch("sys.stdout", stdout)
                    with cwd_patch, stdout_patch, contextlib.redirect_stderr(stderr):
                        exit_code = main(
                            ["build"] if command == "build" else ["export", "prompt"]
                        )

                    message = stderr.getvalue()
                    self.assertEqual(5, exit_code)
                    self.assertIn("path: <stdout>", message)
                    self.assertIn("remediation:", message)
                    self.assertNotIn("Traceback", message)
                finally:
                    temporary.cleanup()

    def test_stdout_programmer_errors_are_not_masked(self) -> None:
        class ProgrammerErrorTextStdout:
            def write(self, data: str) -> int:
                raise RuntimeError("text programmer error")

            def flush(self) -> None:
                raise AssertionError("unreachable")

        class ProgrammerErrorBinaryBuffer:
            def write(self, data: bytes) -> int:
                raise RuntimeError("binary programmer error")

            def flush(self) -> None:
                raise AssertionError("unreachable")

        stdout = mock.Mock()
        stdout.buffer = ProgrammerErrorBinaryBuffer()
        cases = (
            (
                "build",
                ProgrammerErrorTextStdout(),
                ["build"],
                "text programmer error",
            ),
            (
                "export",
                stdout,
                ["export", "prompt"],
                "binary programmer error",
            ),
        )
        for command, failing_stdout, argv, expected in cases:
            with self.subTest(command=command):
                temporary, root = self.make_repository()
                try:
                    if command == "export":
                        write_distribution(root, build_distribution(root))
                    with (
                        mock.patch(
                            f"socratic_learn.{command}.Path.cwd",
                            return_value=root,
                        ),
                        mock.patch("sys.stdout", failing_stdout),
                        self.assertRaisesRegex(RuntimeError, expected),
                    ):
                        main(argv)
                finally:
                    temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
