from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from learning_tutor import PROTOCOL_VERSION
from learning_tutor.errors import CollisionError, FilesystemError, IntegrityError, UsageError
from learning_tutor.install import (
    OWNED_PATHS,
    apply_install,
    load_receipt,
    plan_install,
)
from learning_tutor.manifest import sha256_bytes
from learning_tutor.__main__ import main


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.project = self.root / "project"
        self.source.mkdir()
        self.project.mkdir()
        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\n")

    def _make_distribution(self, prompt: bytes) -> None:
        dist = self.source / "dist"
        dist.mkdir(exist_ok=True)
        manifest = {
            "bundle": {
                "path": "learning-tutor.prompt.md",
                "sha256": sha256_bytes(prompt),
            },
            "capability_fallbacks": {
                "cross_session_memory": "Ask for a prior summary and state what is unknown.",
                "diagram_rendering": "Use Mermaid if available or a textual edge list.",
                "filesystem": "Return the complete session record as Markdown.",
                "structured_quiz": "Ask one question at a time in conversation.",
                "subagents": "Research and teach sequentially.",
                "web": "Mark volatile claims unverified and prefer stable content.",
            },
            "conformance": {
                "required_diagnostic_codes": [
                    "active-return-after-exposition",
                    "bounded-diagnosis",
                    "capability-fallbacks",
                    "evidence-based-closure",
                    "exposition-fallback",
                    "mathematical-assumptions-classification",
                    "observable-outcome",
                    "plan-approval-before-teaching",
                    "private-state",
                    "responsive-socratic-follow-up",
                    "volatile-primary-source-verification",
                ],
                "version": 1,
            },
            "language": "en",
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": 1,
            "session_headings": [
                "## Outcome",
                "## Diagnostic evidence",
                "## Approved dependency path",
                "## Concepts established",
                "## Application evidence",
                "## Remaining gaps",
                "## Next step",
                "## Sources",
            ],
            "sources": [{"path": "core/test.md", "sha256": "0" * 64}],
            "targets": ["generic", "cursor", "claude-code", "pi"],
        }
        (dist / "learning-tutor.prompt.md").write_bytes(prompt)
        (dist / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _install(self) -> None:
        apply_install(plan_install(self.source, self.project, "generic", False))

    def _snapshot(self) -> dict[str, bytes]:
        install_root = self.project / ".learning-tutor"
        return {
            path.relative_to(install_root).as_posix(): path.read_bytes()
            for path in install_root.rglob("*")
            if path.is_file()
        }

    def test_planning_rejects_nonexistent_and_non_directory_projects(self) -> None:
        missing = self.root / "missing"
        file_project = self.root / "file-project"
        file_project.write_text("user data", encoding="utf-8")

        for project in (missing, file_project):
            with self.subTest(project=project.name):
                with self.assertRaises(IntegrityError):
                    plan_install(self.source, project, "generic", False)

    def test_clean_plan_is_frozen_complete_and_side_effect_free(self) -> None:
        before = set(self.root.rglob("*"))

        plan = plan_install(self.source, self.project, "generic", False)

        self.assertEqual(tuple(OWNED_PATHS), tuple(file.path for file in plan.files))
        self.assertEqual(before, set(self.root.rglob("*")))
        with self.assertRaises((AttributeError, TypeError)):
            plan.target = "cursor"  # type: ignore[misc]

    def test_initial_collision_is_rejected_without_mutation(self) -> None:
        collision = self.project / ".learning-tutor"
        collision.write_text("pre-existing", encoding="utf-8")

        with self.assertRaises(CollisionError):
            plan_install(self.source, self.project, "generic", False)

        self.assertEqual("pre-existing", collision.read_text(encoding="utf-8"))

    def test_generic_layout_loader_ignore_and_receipt_are_exact(self) -> None:
        self._install()

        install_root = self.project / ".learning-tutor"
        self.assertEqual(
            "workspace/*\n!workspace/.gitkeep\n",
            (install_root / ".gitignore").read_text(encoding="utf-8"),
        )
        loader = (install_root / "loader.md").read_text(encoding="utf-8")
        self.assertIn(".learning-tutor/learning-tutor.prompt.md", loader)
        self.assertEqual(b"", (install_root / "workspace/.gitkeep").read_bytes())
        receipt = load_receipt(self.project)
        self.assertEqual(list(OWNED_PATHS), receipt["owned_paths"])
        self.assertNotIn(".learning-tutor/install.json", receipt["hashes"])
        self.assertEqual(set(OWNED_PATHS) - {".learning-tutor/install.json"}, set(receipt["hashes"]))
        for relative, digest in receipt["hashes"].items():
            self.assertEqual(
                digest,
                sha256_bytes((self.project / relative).read_bytes()),
            )

    def test_unknown_target_is_rejected(self) -> None:
        with self.assertRaises(UsageError):
            plan_install(self.source, self.project, "unknown", False)

    def test_cursor_and_pi_clean_installs_own_thin_resolving_skills(self) -> None:
        targets = {
            "cursor": ".cursor/skills/learning-tutor/SKILL.md",
            "pi": ".pi/skills/learning-tutor/SKILL.md",
        }
        for target, skill_path in targets.items():
            with self.subTest(target=target):
                project = self.root / target
                project.mkdir()

                plan = plan_install(self.source, project, target, False)
                apply_install(plan)

                skill = project / skill_path
                text = skill.read_text(encoding="utf-8")
                self.assertIn("../../../.learning-tutor/learning-tutor.prompt.md", text)
                self.assertIn("../../../.learning-tutor/workspace/", text)
                self.assertNotIn("## Responsive Socratic dialogue", text)
                self.assertNotIn("## Connected foundations", text)
                self.assertEqual(
                    project / ".learning-tutor/learning-tutor.prompt.md",
                    (skill.parent / "../../../.learning-tutor/learning-tutor.prompt.md").resolve(),
                )
                receipt = load_receipt(project)
                self.assertEqual(target, receipt["target"])
                self.assertIn(skill_path, receipt["owned_paths"])

    def test_native_skill_destination_collisions_abort_before_mutation(self) -> None:
        for target, relative in (
            ("cursor", ".cursor/skills/learning-tutor"),
            ("pi", ".pi/skills/learning-tutor"),
        ):
            for kind in ("empty-directory", "file"):
                with self.subTest(target=target, kind=kind):
                    project = self.root / f"{target}-{kind}"
                    project.mkdir()
                    collision = project / relative
                    collision.parent.mkdir(parents=True)
                    if kind == "empty-directory":
                        collision.mkdir()
                    else:
                        collision.write_bytes(b"user data")
                    before = {
                        path.relative_to(project).as_posix(): (
                            None if path.is_dir() else path.read_bytes()
                        )
                        for path in project.rglob("*")
                    }

                    with self.assertRaises(CollisionError):
                        plan_install(self.source, project, target, False)

                    after = {
                        path.relative_to(project).as_posix(): (
                            None if path.is_dir() else path.read_bytes()
                        )
                        for path in project.rglob("*")
                    }
                    self.assertEqual(before, after)
                    self.assertFalse((project / ".learning-tutor").exists())

    def test_native_skill_ancestor_file_collision_aborts_before_mutation(self) -> None:
        for target, relative in (("cursor", ".cursor"), ("pi", ".pi")):
            with self.subTest(target=target):
                project = self.root / f"{target}-ancestor"
                project.mkdir()
                collision = project / relative
                collision.write_bytes(b"user data")

                with self.assertRaises(CollisionError):
                    plan_install(self.source, project, target, False)

                self.assertEqual(b"user data", collision.read_bytes())
                self.assertFalse((project / ".learning-tutor").exists())

    def test_claude_absent_root_is_owned_thin_loader_and_updates(self) -> None:
        plan = plan_install(self.source, self.project, "claude-code", False)
        self.assertIsNone(plan.emitted_snippet)
        apply_install(plan)

        claude = self.project / "CLAUDE.md"
        first = claude.read_bytes()
        self.assertIn(b".learning-tutor/learning-tutor.prompt.md", first)
        self.assertNotIn(b"## Responsive Socratic dialogue", first)
        self.assertIn("CLAUDE.md", load_receipt(self.project)["owned_paths"])

        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\nChanged.\n")
        update = plan_install(self.source, self.project, "claude-code", True)
        self.assertIsNone(update.emitted_snippet)
        apply_install(update)

        self.assertEqual(first, claude.read_bytes())
        self.assertIn("CLAUDE.md", load_receipt(self.project)["owned_paths"])

    def test_claude_existing_root_is_preserved_and_never_owned(self) -> None:
        original = b"# User instructions\r\nKeep this byte-exact.\r\n"
        claude = self.project / "CLAUDE.md"
        claude.write_bytes(original)

        plan = plan_install(self.source, self.project, "claude-code", False)
        self.assertEqual(
            (
                "Read and follow `.learning-tutor/learning-tutor.prompt.md` before "
                "starting any learning session.\n\n"
                "Capability mapping:\n"
                "- Use configured web tools for primary-source verification; "
                "otherwise mark volatile claims unverified in conversation.\n"
                "- Use configured filesystem tools to keep private learner state "
                "under `.learning-tutor/workspace/` and out of version control; "
                "otherwise return the record in conversation.\n"
            ),
            plan.emitted_snippet,
        )
        self.assertNotIn("CLAUDE.md", tuple(file.path for file in plan.files))
        apply_install(plan)

        self.assertEqual(original, claude.read_bytes())
        self.assertNotIn("CLAUDE.md", load_receipt(self.project)["owned_paths"])

        update = plan_install(self.source, self.project, "claude-code", True)
        self.assertEqual(plan.emitted_snippet, update.emitted_snippet)
        apply_install(update)

        self.assertEqual(original, claude.read_bytes())
        self.assertNotIn("CLAUDE.md", load_receipt(self.project)["owned_paths"])

    def test_claude_root_directory_collision_aborts_before_mutation(self) -> None:
        (self.project / "CLAUDE.md").mkdir()

        with self.assertRaises(CollisionError):
            plan_install(self.source, self.project, "claude-code", False)

        self.assertTrue((self.project / "CLAUDE.md").is_dir())
        self.assertFalse((self.project / ".learning-tutor").exists())

    def test_target_templates_never_enter_universal_prompt(self) -> None:
        marker = "before starting any learning session"
        prompt = (self.source / "dist/learning-tutor.prompt.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(marker, prompt)
        for target in ("cursor", "claude-code", "pi"):
            plan = plan_install(self.source, self.project, target, False)
            target_text = "\n".join(
                file.content.decode("utf-8")
                for file in plan.files
                if file.path not in OWNED_PATHS
            )
            if plan.emitted_snippet is not None:
                target_text += plan.emitted_snippet
            self.assertIn(marker, target_text.lower())

    def test_target_templates_map_capabilities_without_copying_pedagogy(self) -> None:
        expected = {
            "cursor": (
                "structured question",
                "conversation",
                "web",
                "primary sources",
                "mermaid",
                "text",
                "filesystem",
            ),
            "pi": (
                "optional quiz",
                "preference question",
                "conversation",
                "research",
                "web",
                "visual makers",
                "md-log",
                "filesystem",
            ),
            "claude-code": (
                "configured web",
                "configured filesystem",
                "conversation",
            ),
        }
        forbidden = (
            "responsive socratic",
            "connected foundations",
            "diagnostic budget",
            "mastery evidence",
        )
        for target, phrases in expected.items():
            with self.subTest(target=target):
                plan = plan_install(self.source, self.project, target, False)
                text = "\n".join(
                    file.content.decode("utf-8")
                    for file in plan.files
                    if file.path not in OWNED_PATHS
                ).lower()
                self.assertTrue(all(phrase in text for phrase in phrases))
                self.assertTrue(all(phrase not in text for phrase in forbidden))
                if target in ("cursor", "pi"):
                    self.assertTrue(text.startswith("---\nname: learning-tutor\n"))
                    self.assertIn("description:", text)

    def test_commit_time_destination_races_preserve_external_bytes(self) -> None:
        cases = (
            ("cursor", ".cursor/skills/learning-tutor/SKILL.md"),
            ("pi", ".pi/skills/learning-tutor/SKILL.md"),
            ("claude-code", "CLAUDE.md"),
        )
        install_module = __import__("learning_tutor.install", fromlist=["_stage"])
        real_stage = install_module._stage
        for target, relative in cases:
            with self.subTest(target=target):
                project = self.root / f"{target}-race"
                project.mkdir()
                plan = plan_install(self.source, project, target, False)
                external = project / relative

                def stage_then_race(current_plan):
                    staged = real_stage(current_plan)
                    external.parent.mkdir(parents=True, exist_ok=True)
                    external.write_bytes(b"external race winner")
                    return staged

                with mock.patch(
                    "learning_tutor.install._stage",
                    side_effect=stage_then_race,
                ):
                    with self.assertRaises(CollisionError):
                        apply_install(plan)

                self.assertEqual(b"external race winner", external.read_bytes())
                self.assertFalse((project / ".learning-tutor").exists())
                self.assertFalse(
                    any(
                        path.name.startswith(
                            (".learning-tutor-stage-", ".learning-tutor-backup-")
                        )
                        for path in project.iterdir()
                    )
                )

    def test_hard_link_identity_race_preserves_external_replacement(self) -> None:
        plan = plan_install(self.source, self.project, "claude-code", False)
        claude = self.project / "CLAUDE.md"
        real_link = os.link

        def replace_after_link(source, destination, *args, **kwargs):
            real_link(source, destination, *args, **kwargs)
            if Path(destination) == claude:
                claude.unlink()
                claude.write_bytes(b"external replacement")

        with mock.patch(
            "learning_tutor.install.os.link",
            side_effect=replace_after_link,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertEqual(b"external replacement", claude.read_bytes())
        self.assertFalse((self.project / ".learning-tutor").exists())
        self.assertIn("CLAUDE.md", str(raised.exception))

    def test_initial_rollback_unlinks_only_matching_installer_identity(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        skill = self.project / ".cursor/skills/learning-tutor/SKILL.md"
        install_module = __import__(
            "learning_tutor.install",
            fromlist=["_link_staged_file", "_rollback_initial"],
        )
        real_link_staged = install_module._link_staged_file
        real_rollback = install_module._rollback_initial

        def fail_after_external_link(source: Path, destination: Path):
            linked = real_link_staged(source, destination)
            if destination != skill:
                raise OSError("injected failure after native link")
            return linked

        def replace_before_rollback(linked_files, created_directories):
            skill.unlink()
            skill.write_bytes(b"external before rollback")
            return real_rollback(linked_files, created_directories)

        with (
            mock.patch(
                "learning_tutor.install._link_staged_file",
                side_effect=fail_after_external_link,
            ),
            mock.patch(
                "learning_tutor.install._rollback_initial",
                side_effect=replace_before_rollback,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertEqual(b"external before rollback", skill.read_bytes())
        self.assertIn(str(skill), str(raised.exception))

    def test_initial_rollback_preserves_replaced_created_directory(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        native_directory = self.project / ".cursor/skills/learning-tutor"
        external = native_directory / "external.txt"
        install_module = __import__(
            "learning_tutor.install",
            fromlist=["_link_staged_file", "_rollback_initial"],
        )
        real_link_staged = install_module._link_staged_file
        real_rollback = install_module._rollback_initial

        def fail_after_native_link(source: Path, destination: Path):
            linked = real_link_staged(source, destination)
            if destination != native_directory / "SKILL.md":
                raise OSError("injected failure after native link")
            return linked

        def replace_directory_before_rollback(linked_files, created_directories):
            (native_directory / "SKILL.md").unlink()
            native_directory.rmdir()
            native_directory.mkdir()
            external.write_bytes(b"external directory replacement")
            return real_rollback(linked_files, created_directories)

        with (
            mock.patch(
                "learning_tutor.install._link_staged_file",
                side_effect=fail_after_native_link,
            ),
            mock.patch(
                "learning_tutor.install._rollback_initial",
                side_effect=replace_directory_before_rollback,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertEqual(b"external directory replacement", external.read_bytes())
        self.assertIn(str(native_directory), str(raised.exception))

    def test_commit_time_empty_native_directory_races_abort(self) -> None:
        install_module = __import__("learning_tutor.install", fromlist=["_stage"])
        real_stage = install_module._stage
        for target, relative in (
            ("cursor", ".cursor/skills/learning-tutor"),
            ("pi", ".pi/skills/learning-tutor"),
        ):
            with self.subTest(target=target):
                project = self.root / f"{target}-directory-race"
                project.mkdir()
                plan = plan_install(self.source, project, target, False)
                external_directory = project / relative

                def stage_then_race(current_plan):
                    staged = real_stage(current_plan)
                    external_directory.mkdir(parents=True)
                    return staged

                with mock.patch(
                    "learning_tutor.install._stage",
                    side_effect=stage_then_race,
                ):
                    with self.assertRaises(CollisionError):
                        apply_install(plan)

                self.assertEqual([], list(external_directory.iterdir()))
                self.assertFalse((project / ".learning-tutor").exists())

    def test_generic_package_race_during_staging_preserves_external_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__("learning_tutor.install", fromlist=["_stage"])
        real_stage = install_module._stage
        external_root = self.project / ".learning-tutor"
        sentinel = external_root / "external.txt"

        def stage_then_race(current_plan):
            staged = real_stage(current_plan)
            external_root.mkdir()
            sentinel.write_bytes(b"external race winner")
            return staged

        with mock.patch("learning_tutor.install._stage", side_effect=stage_then_race):
            with self.assertRaises(CollisionError):
                apply_install(plan)

        self.assertEqual(b"external race winner", sentinel.read_bytes())
        self.assertEqual(["external.txt"], [path.name for path in external_root.iterdir()])
        self.assertFalse(
            any(
                path.name.startswith(
                    (".learning-tutor-stage-", ".learning-tutor-backup-")
                )
                for path in self.project.iterdir()
            )
        )

    def test_update_hashes_post_staging_backup_bytes(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__("learning_tutor.install", fromlist=["_stage"])
        real_stage = install_module._stage
        manifest = self.project / ".learning-tutor/manifest.json"

        def stage_then_modify(current_plan):
            staged = real_stage(current_plan)
            manifest.write_bytes(b"changed after preflight")
            return staged

        with mock.patch(
            "learning_tutor.install._stage",
            side_effect=stage_then_modify,
        ):
            with self.assertRaises(IntegrityError):
                apply_install(plan)

        self.assertEqual(b"changed after preflight", manifest.read_bytes())
        self.assertFalse(
            any(
                path.name.startswith(
                    (".learning-tutor-stage-", ".learning-tutor-backup-")
                )
                for path in self.project.iterdir()
            )
        )

    def test_update_hashes_bytes_after_atomic_backup_move(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        manifest = self.project / ".learning-tutor/manifest.json"
        real_replace = os.replace
        injected = False

        def mutate_during_backup(source, destination):
            nonlocal injected
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                not injected
                and source_path == manifest
                and ".learning-tutor-backup-" in str(destination_path)
            ):
                injected = True
                source_path.write_bytes(b"mutated during backup move")
            real_replace(source_path, destination_path)

        with mock.patch(
            "learning_tutor.install.os.replace",
            side_effect=mutate_during_backup,
        ):
            with self.assertRaises(IntegrityError):
                apply_install(plan)

        self.assertEqual(b"mutated during backup move", manifest.read_bytes())
        self.assertFalse(
            any(
                path.name.startswith(
                    (".learning-tutor-stage-", ".learning-tutor-backup-")
                )
                for path in self.project.iterdir()
            )
        )

    def test_update_restore_preserves_external_destination_and_backup(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        manifest = self.project / ".learning-tutor/manifest.json"
        real_replace = os.replace
        real_link = os.link
        injected_backup_mutation = False
        injected_restore_collision = False

        def mutate_during_backup(source, destination):
            nonlocal injected_backup_mutation
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                not injected_backup_mutation
                and source_path == manifest
                and ".learning-tutor-backup-" in str(destination_path)
            ):
                injected_backup_mutation = True
                source_path.write_bytes(b"mismatched backup bytes")
            real_replace(source_path, destination_path)

        def collide_during_restore(source, destination, *args, **kwargs):
            nonlocal injected_restore_collision
            source_path = Path(source)
            destination_path = Path(destination)
            if (
                not injected_restore_collision
                and ".learning-tutor-backup-" in str(source_path)
                and destination_path == manifest
            ):
                injected_restore_collision = True
                destination_path.write_bytes(b"external restore winner")
            real_link(source, destination, *args, **kwargs)

        with (
            mock.patch(
                "learning_tutor.install.os.replace",
                side_effect=mutate_during_backup,
            ),
            mock.patch(
                "learning_tutor.install.os.link",
                side_effect=collide_during_restore,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".learning-tutor-backup-")
        ]
        self.assertEqual(b"external restore winner", manifest.read_bytes())
        self.assertEqual(1, len(backups))
        backup_manifest = backups[0] / ".learning-tutor/manifest.json"
        self.assertEqual(b"mismatched backup bytes", backup_manifest.read_bytes())
        self.assertIn(str(manifest), str(raised.exception))
        self.assertIn(str(backup_manifest), str(raised.exception))

    def test_native_target_update_preserves_ownership_and_private_state(self) -> None:
        for target, skill_path in (
            ("cursor", ".cursor/skills/learning-tutor/SKILL.md"),
            ("pi", ".pi/skills/learning-tutor/SKILL.md"),
        ):
            with self.subTest(target=target):
                project = self.root / f"{target}-update"
                project.mkdir()
                apply_install(plan_install(self.source, project, target, False))
                private = project / ".learning-tutor/workspace/private.md"
                private.write_bytes(b"private")

                apply_install(plan_install(self.source, project, target, True))

                self.assertEqual(b"private", private.read_bytes())
                self.assertIn(skill_path, load_receipt(project)["owned_paths"])

    def test_update_rejects_a_different_requested_target(self) -> None:
        apply_install(plan_install(self.source, self.project, "cursor", False))

        with self.assertRaises(IntegrityError):
            plan_install(self.source, self.project, "pi", True)

        self.assertTrue(
            (self.project / ".cursor/skills/learning-tutor/SKILL.md").is_file()
        )
        self.assertFalse((self.project / ".pi").exists())

    def test_native_initial_commit_failure_removes_created_target_directories(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)

        def fail_native_move(
            source: Path,
            destination: Path,
        ):
            if str(destination).endswith(
                os.path.join(".cursor", "skills", "learning-tutor", "SKILL.md")
            ):
                raise OSError("injected native move failure")
            raise AssertionError("native destination must be linked first")

        with mock.patch(
            "learning_tutor.install._link_staged_file",
            side_effect=fail_native_move,
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertFalse((self.project / ".learning-tutor").exists())
        self.assertFalse((self.project / ".cursor").exists())

    def test_unchanged_update_replaces_managed_files_and_preserves_private_state(self) -> None:
        self._install()
        private = self.project / ".learning-tutor/workspace/private.md"
        private.write_text("private", encoding="utf-8")
        new_prompt = b"# Universal Learning Tutor\nProtocol: 1.0.0\nUpdated.\n"
        self._make_distribution(new_prompt)

        apply_install(plan_install(self.source, self.project, "generic", True))

        self.assertEqual(
            new_prompt,
            (self.project / ".learning-tutor/learning-tutor.prompt.md").read_bytes(),
        )
        self.assertEqual("private", private.read_text(encoding="utf-8"))

    def test_update_refuses_modified_or_missing_owned_file_before_mutation(self) -> None:
        for state in ("modified", "missing"):
            with self.subTest(state=state):
                if (self.project / ".learning-tutor").exists():
                    import shutil

                    shutil.rmtree(self.project / ".learning-tutor")
                self._install()
                managed = self.project / ".learning-tutor/loader.md"
                if state == "modified":
                    managed.write_text("user edit\n", encoding="utf-8")
                else:
                    managed.unlink()
                before = set(self.root.iterdir())

                with self.assertRaises(IntegrityError):
                    plan_install(self.source, self.project, "generic", True)

                self.assertEqual(before, set(self.root.iterdir()))
                self.assertFalse(any(path.name.startswith(".learning-tutor-stage-") for path in self.project.iterdir()))
                self.assertFalse(any(path.name.startswith(".learning-tutor-backup-") for path in self.project.iterdir()))

    def test_update_refuses_missing_invalid_or_escaping_receipt(self) -> None:
        for state in ("missing", "invalid", "escape"):
            with self.subTest(state=state):
                if (self.project / ".learning-tutor").exists():
                    import shutil

                    shutil.rmtree(self.project / ".learning-tutor")
                self._install()
                receipt_path = self.project / ".learning-tutor/install.json"
                if state == "missing":
                    receipt_path.unlink()
                elif state == "invalid":
                    receipt_path.write_text("{", encoding="utf-8")
                else:
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    receipt["owned_paths"].append("../escape")
                    receipt["hashes"]["../escape"] = "0" * 64
                    receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")

                with self.assertRaises(IntegrityError):
                    plan_install(self.source, self.project, "generic", True)

                self.assertFalse((self.root / "escape").exists())

    def test_update_refuses_unowned_target_collision(self) -> None:
        self._install()
        receipt_path = self.project / ".learning-tutor/install.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned_paths"].remove(".learning-tutor/loader.md")
        receipt["hashes"].pop(".learning-tutor/loader.md")
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(CollisionError):
            plan_install(self.source, self.project, "generic", True)

        self.assertTrue((self.project / ".learning-tutor/loader.md").exists())

    def test_staging_failure_removes_only_operation_paths(self) -> None:
        sentinel = self.project / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        plan = plan_install(self.source, self.project, "generic", False)

        with mock.patch(
            "learning_tutor.install._write_staged_file",
            side_effect=OSError("injected staging failure"),
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".learning-tutor").exists())
        self.assertFalse(any(path.name.startswith(".learning-tutor-stage-") for path in self.project.iterdir()))

    def test_staged_hash_mismatch_cleans_actual_stage_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        bad_file = replace(plan.files[0], sha256="0" * 64)
        bad_plan = replace(plan, files=(bad_file, *plan.files[1:]))

        with self.assertRaisesRegex(IntegrityError, "staged file hash"):
            apply_install(bad_plan)

        self.assertFalse((self.project / ".learning-tutor").exists())
        self.assertFalse(
            any(
                path.name.startswith(".learning-tutor-stage-")
                for path in self.project.iterdir()
            )
        )

    def test_staging_and_cleanup_failure_reports_original_and_recovery_path(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)

        with (
            mock.patch(
                "learning_tutor.install._write_staged_file",
                side_effect=OSError("injected staging write failure"),
            ),
            mock.patch(
                "learning_tutor.install._remove_created_tree",
                side_effect=PermissionError("injected locked stage"),
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        message = str(raised.exception)
        self.assertIn("injected staging write failure", message)
        self.assertIn("injected locked stage", message)
        self.assertIn(".learning-tutor-stage-", message)
        stages = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".learning-tutor-stage-")
        ]
        self.assertEqual(1, len(stages))
        self.assertEqual(stages[0], Path(raised.exception.path))

    def test_initial_commit_failure_preserves_preexisting_paths(self) -> None:
        sentinel = self.project / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        plan = plan_install(self.source, self.project, "generic", False)

        with mock.patch(
            "learning_tutor.install._link_staged_file",
            side_effect=OSError("injected commit failure"),
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".learning-tutor").exists())

    def test_initial_cleanup_failure_reports_locked_partial_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__(
            "learning_tutor.install",
            fromlist=["_link_staged_file"],
        )
        real_link = install_module._link_staged_file
        real_rmdir = Path.rmdir
        links = 0

        def fail_second_link(source: Path, destination: Path):
            nonlocal links
            links += 1
            if links == 2:
                raise OSError("injected initial commit failure")
            return real_link(source, destination)

        def lock_install_root(path: Path) -> None:
            if path == self.project / ".learning-tutor":
                raise PermissionError("injected locked install path")
            real_rmdir(path)

        with (
            mock.patch(
                "learning_tutor.install._link_staged_file",
                side_effect=fail_second_link,
            ),
            mock.patch(
                "pathlib.Path.rmdir",
                side_effect=lock_install_root,
                autospec=True,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertIn("injected initial commit failure", str(raised.exception))
        self.assertIn("injected locked install path", str(raised.exception))
        self.assertEqual(self.project / ".learning-tutor", Path(raised.exception.path))
        self.assertTrue((self.project / ".learning-tutor").is_dir())
        self.assertFalse(
            any(
                path.name.startswith(".learning-tutor-stage-")
                for path in self.project.iterdir()
            )
        )

    def test_backup_failure_restores_every_old_file(self) -> None:
        self._install()
        before = self._snapshot()
        plan = plan_install(self.source, self.project, "generic", True)
        real_replace = os.replace
        backup_moves = 0

        def fail_backup(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            nonlocal backup_moves
            if ".learning-tutor-backup-" in str(destination):
                backup_moves += 1
                if backup_moves == 2:
                    raise OSError("injected backup failure")
            real_replace(source, destination)

        with mock.patch("learning_tutor.install.os.replace", side_effect=fail_backup):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual(before, self._snapshot())

    def test_update_commit_failure_rolls_back_every_old_file(self) -> None:
        self._install()
        before = self._snapshot()
        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\nNew.\n")
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__(
            "learning_tutor.install",
            fromlist=["_link_staged_file"],
        )
        real_link = install_module._link_staged_file
        committed = 0

        def fail_commit(source: Path, destination: Path):
            nonlocal committed
            committed += 1
            if committed == 2:
                raise OSError("injected update commit failure")
            return real_link(source, destination)

        with mock.patch(
            "learning_tutor.install._link_staged_file",
            side_effect=fail_commit,
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual(before, self._snapshot())

    def test_integrity_error_after_first_update_move_rolls_back(self) -> None:
        self._install()
        before = self._snapshot()
        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\nNew.\n")
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__("learning_tutor.install", fromlist=["_project_path"])
        real_project_path = install_module._project_path
        real_link = install_module._link_staged_file
        first_commit_completed = False
        injected = False

        def track_commit(
            source: Path,
            destination: Path,
        ):
            nonlocal first_commit_completed
            linked = real_link(source, destination)
            first_commit_completed = True
            return linked

        def race_on_second_commit(project: Path, relative: str) -> Path:
            nonlocal injected
            if (
                first_commit_completed
                and not injected
                and relative == plan.files[1].path
            ):
                injected = True
                raise IntegrityError(
                    "injected symlink race",
                    path=relative,
                    remediation="retry",
                )
            return real_project_path(project, relative)

        with (
            mock.patch(
                "learning_tutor.install._link_staged_file",
                side_effect=track_commit,
            ),
            mock.patch(
                "learning_tutor.install._project_path",
                side_effect=race_on_second_commit,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertIn("injected symlink race", str(raised.exception))
        self.assertEqual(before, self._snapshot())
        self.assertFalse(
            any(
                path.name.startswith((".learning-tutor-stage-", ".learning-tutor-backup-"))
                for path in self.project.iterdir()
            )
        )

    def test_update_rollback_removes_only_operation_created_parent(self) -> None:
        self._install()
        workspace = self.project / ".learning-tutor/workspace"
        (workspace / ".gitkeep").unlink()
        workspace.rmdir()
        receipt_path = self.project / ".learning-tutor/install.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned_paths"].remove(".learning-tutor/workspace/.gitkeep")
        receipt["hashes"].pop(".learning-tutor/workspace/.gitkeep")
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__(
            "learning_tutor.install",
            fromlist=["_link_staged_file"],
        )
        real_link_staged = install_module._link_staged_file

        def fail_after_parent_creation(source: Path, destination: Path):
            if destination.name == ".gitkeep":
                raise OSError("injected commit failure after parent creation")
            return real_link_staged(source, destination)

        with mock.patch(
            "learning_tutor.install._link_staged_file",
            side_effect=fail_after_parent_creation,
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertFalse(workspace.exists())
        self.assertTrue((self.project / ".learning-tutor/loader.md").is_file())

    def test_rollback_failure_keeps_backup_and_reports_recovery_path(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        real_link = os.link

        def fail_commit_and_rollback(
            source: str | os.PathLike[str],
            destination: str | os.PathLike[str],
            *args,
            **kwargs,
        ) -> None:
            source_path = Path(source)
            if ".learning-tutor-stage-" in str(source_path):
                raise OSError("injected commit failure")
            if ".learning-tutor-backup-" in str(source_path):
                raise OSError("injected rollback failure")
            real_link(source, destination, *args, **kwargs)

        with mock.patch(
            "learning_tutor.install.os.link",
            side_effect=fail_commit_and_rollback,
        ):
            with self.assertRaisesRegex(FilesystemError, "rollback") as raised:
                apply_install(plan)

        self.assertIn(".learning-tutor-backup-", raised.exception.remediation or "")
        self.assertTrue(any(path.name.startswith(".learning-tutor-backup-") for path in self.project.iterdir()))

    def test_cli_prints_loader_and_update_transition(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch("learning_tutor.install.Path.cwd", return_value=self.source),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(0, main(["install", "generic", str(self.project)]))
        self.assertIn(".learning-tutor/learning-tutor.prompt.md", stdout.getvalue())

        stdout = io.StringIO()
        with (
            mock.patch("learning_tutor.install.Path.cwd", return_value=self.source),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(0, main(["install", "generic", str(self.project), "--update"]))
        self.assertIn(f"{PROTOCOL_VERSION} -> {PROTOCOL_VERSION}", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
