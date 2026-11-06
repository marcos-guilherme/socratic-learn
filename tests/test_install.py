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

import socratic_learn.safe_fs as safe_fs
from socratic_learn import (
    MANIFEST_SCHEMA_VERSION,
    PRODUCT_ID,
    PROTOCOL_VERSION,
)
from socratic_learn.errors import CollisionError, FilesystemError, IntegrityError, UsageError
from socratic_learn.install import (
    OWNED_PATHS,
    apply_install,
    load_receipt,
    plan_install,
)
from socratic_learn.manifest import sha256_bytes
from socratic_learn.__main__ import main


class InstallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.project = self.root / "project"
        self.source.mkdir()
        self.project.mkdir()
        self._make_distribution(b"# Socratic Learn\nProtocol: 1.0.0\n")

    def assert_posix_same_principal_limit(self, error: BaseException) -> None:
        message = str(error).lower()
        self.assertNotIn("no external data was deleted", message)
        self.assertIn("posix", message)
        self.assertIn("same-principal", message)
        self.assertIn("leaf-entry", message)

    def _make_distribution(self, prompt: bytes) -> None:
        dist = self.source / "dist"
        dist.mkdir(exist_ok=True)
        manifest = {
            "bundle": {
                "path": "socratic-learn.prompt.md",
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
            "product": PRODUCT_ID,
            "protocol_version": PROTOCOL_VERSION,
            "schema_version": MANIFEST_SCHEMA_VERSION,
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
        (dist / "socratic-learn.prompt.md").write_bytes(prompt)
        (dist / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _install(self) -> None:
        apply_install(plan_install(self.source, self.project, "generic", False))

    def _snapshot(self) -> dict[str, bytes]:
        install_root = self.project / ".socratic-learn"
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
        collision = self.project / ".socratic-learn"
        collision.write_text("pre-existing", encoding="utf-8")

        with self.assertRaises(CollisionError):
            plan_install(self.source, self.project, "generic", False)

        self.assertEqual("pre-existing", collision.read_text(encoding="utf-8"))

    def test_generic_layout_loader_ignore_and_receipt_are_exact(self) -> None:
        self._install()

        install_root = self.project / ".socratic-learn"
        self.assertEqual(
            "workspace/*\n!workspace/.gitkeep\n",
            (install_root / ".gitignore").read_text(encoding="utf-8"),
        )
        loader = (install_root / "loader.md").read_text(encoding="utf-8")
        self.assertIn(".socratic-learn/socratic-learn.prompt.md", loader)
        self.assertEqual(b"", (install_root / "workspace/.gitkeep").read_bytes())
        receipt = load_receipt(self.project)
        self.assertEqual(2, receipt["schema_version"])
        self.assertEqual(PRODUCT_ID, receipt["product"])
        self.assertEqual(
            {
                "schema_version",
                "product",
                "protocol_version",
                "target",
                "owned_paths",
                "hashes",
            },
            set(receipt),
        )
        self.assertEqual(list(OWNED_PATHS), receipt["owned_paths"])
        self.assertNotIn(".socratic-learn/install.json", receipt["hashes"])
        self.assertEqual(set(OWNED_PATHS) - {".socratic-learn/install.json"}, set(receipt["hashes"]))
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
            "cursor": ".cursor/skills/socratic-learn/SKILL.md",
            "pi": ".pi/skills/socratic-learn/SKILL.md",
        }
        for target, skill_path in targets.items():
            with self.subTest(target=target):
                project = self.root / target
                project.mkdir()

                plan = plan_install(self.source, project, target, False)
                apply_install(plan)

                skill = project / skill_path
                text = skill.read_text(encoding="utf-8")
                self.assertIn("../../../.socratic-learn/socratic-learn.prompt.md", text)
                self.assertIn("../../../.socratic-learn/workspace/", text)
                self.assertNotIn("## Responsive Socratic dialogue", text)
                self.assertNotIn("## Connected foundations", text)
                self.assertEqual(
                    project / ".socratic-learn/socratic-learn.prompt.md",
                    (skill.parent / "../../../.socratic-learn/socratic-learn.prompt.md").resolve(),
                )
                receipt = load_receipt(project)
                self.assertEqual(target, receipt["target"])
                self.assertIn(skill_path, receipt["owned_paths"])

    def test_native_skill_destination_collisions_abort_before_mutation(self) -> None:
        for target, relative in (
            ("cursor", ".cursor/skills/socratic-learn"),
            ("pi", ".pi/skills/socratic-learn"),
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
                    self.assertFalse((project / ".socratic-learn").exists())

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
                self.assertFalse((project / ".socratic-learn").exists())

    def test_claude_absent_root_is_owned_thin_loader_and_updates(self) -> None:
        plan = plan_install(self.source, self.project, "claude-code", False)
        self.assertIsNone(plan.emitted_snippet)
        apply_install(plan)

        claude = self.project / "CLAUDE.md"
        first = claude.read_bytes()
        self.assertIn(b".socratic-learn/socratic-learn.prompt.md", first)
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
                "Read and follow `.socratic-learn/socratic-learn.prompt.md` before "
                "starting any learning session.\n\n"
                "Capability mapping:\n"
                "- Use configured web tools for primary-source verification; "
                "otherwise mark volatile claims unverified in conversation.\n"
                "- Use configured filesystem tools to keep private learner state "
                "under `.socratic-learn/workspace/` and out of version control; "
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
        self.assertFalse((self.project / ".socratic-learn").exists())

    def test_target_templates_never_enter_universal_prompt(self) -> None:
        marker = "before starting any learning session"
        prompt = (self.source / "dist/socratic-learn.prompt.md").read_text(
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
                    self.assertTrue(text.startswith("---\nname: socratic-learn\n"))
                    self.assertIn("description:", text)

    def test_commit_time_destination_races_preserve_external_bytes(self) -> None:
        cases = (
            ("cursor", ".cursor/skills/socratic-learn/SKILL.md"),
            ("pi", ".pi/skills/socratic-learn/SKILL.md"),
            ("claude-code", "CLAUDE.md"),
        )
        install_module = __import__("socratic_learn.install", fromlist=["_stage"])
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
                    "socratic_learn.install._stage",
                    side_effect=stage_then_race,
                ):
                    with self.assertRaises(CollisionError):
                        apply_install(plan)

                self.assertEqual(b"external race winner", external.read_bytes())
                self.assertFalse((project / ".socratic-learn").exists())
                self.assertFalse(
                    any(
                        path.name.startswith(
                            (".socratic-learn-stage-", ".socratic-learn-backup-")
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
            "socratic_learn.install.os.link",
            side_effect=replace_after_link,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertEqual(b"external replacement", claude.read_bytes())
        self.assertFalse((self.project / ".socratic-learn").exists())
        self.assertTrue(
            any(
                path.name.startswith(".socratic-learn-stage-")
                for path in self.project.iterdir()
            )
        )
        self.assertIn("CLAUDE.md", str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_failure_after_publication_preserves_partial_paths_and_stage(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link = install_module._link_staged_file
        publications = 0

        def fail_second_publication(source: Path, destination: Path):
            nonlocal publications
            publications += 1
            if publications == 2:
                raise OSError("injected failure after publication")
            return real_link(source, destination)

        with (
            mock.patch(
                "socratic_learn.install._link_staged_file",
                side_effect=fail_second_publication,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        manifest = self.project / ".socratic-learn/manifest.json"
        receipt = self.project / ".socratic-learn/install.json"
        stages = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-stage-")
        ]
        self.assertTrue(manifest.is_file())
        self.assertFalse(receipt.exists())
        self.assertEqual(1, len(stages))
        self.assertIn(str(manifest), str(raised.exception))
        self.assertIn(str(stages[0]), str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_update_failure_preserves_partial_paths_backups_and_stage(self) -> None:
        self._install()
        self._make_distribution(
            b"# Universal Learning Tutor\nProtocol: 1.0.0\nUpdated.\n"
        )
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link = install_module._link_staged_file
        publications = 0

        def fail_second_publication(source: Path, destination: Path):
            nonlocal publications
            publications += 1
            if publications == 2:
                raise OSError("injected update publication failure")
            return real_link(source, destination)

        with (
            mock.patch(
                "socratic_learn.install._link_staged_file",
                side_effect=fail_second_publication,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        stages = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-stage-")
        ]
        manifest = self.project / ".socratic-learn/manifest.json"
        receipt = self.project / ".socratic-learn/install.json"
        self.assertTrue(manifest.is_file())
        self.assertTrue(receipt.is_file())
        old_receipt = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertNotEqual(
            old_receipt["hashes"][".socratic-learn/manifest.json"],
            sha256_bytes(manifest.read_bytes()),
        )
        self.assertEqual(1, len(backups))
        self.assertEqual(1, len(stages))
        self.assertIn(str(manifest), str(raised.exception))
        self.assertIn(str(backups[0]), str(raised.exception))
        self.assertIn(str(stages[0]), str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_successful_installs_leave_no_private_transaction_artifacts(self) -> None:
        for target in ("generic", "cursor", "claude-code", "pi"):
            with self.subTest(target=target):
                project = self.root / f"clean-{target}"
                project.mkdir()
                apply_install(plan_install(self.source, project, target, False))

                self.assertTrue((project / ".socratic-learn/install.json").is_file())
                self.assertFalse(
                    any(
                        path.name.startswith(
                            (".socratic-learn-stage-", ".socratic-learn-backup-")
                        )
                        for path in project.iterdir()
                    )
                )

    def test_parent_replacement_before_link_preserves_external_tree(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        parent = self.project / ".cursor/skills/socratic-learn"
        detached = self.project / "detached-before-link"
        sentinel = parent / "external.txt"
        injected = False

        def replace_parent(source: Path, destination: Path) -> None:
            nonlocal injected
            if injected or destination.parent != parent:
                return
            injected = True
            parent.rename(detached)
            parent.mkdir()
            sentinel.write_bytes(b"external parent before link")

        with (
            mock.patch(
                "socratic_learn.install._before_link_publication",
                side_effect=replace_parent,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        if os.name == "nt":
            self.assertTrue(parent.is_dir())
            self.assertFalse(detached.exists())
            self.assertFalse(sentinel.exists())
        else:
            self.assertEqual(b"external parent before link", sentinel.read_bytes())
            linked = detached / "SKILL.md"
            if linked.exists():
                self.assertIn("parent chain", str(raised.exception).lower())
        self.assertFalse((self.project / ".socratic-learn").exists())

    def test_parent_replacement_after_link_preserves_external_tree(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        parent = self.project / ".cursor/skills/socratic-learn"
        detached = self.project / "detached-after-link"
        sentinel = parent / "external.txt"
        injected = False

        def replace_parent(source: Path, destination: Path) -> None:
            nonlocal injected
            if injected or destination.parent != parent:
                return
            injected = True
            parent.rename(detached)
            parent.mkdir()
            sentinel.write_bytes(b"external parent after link")

        with (
            mock.patch(
                "socratic_learn.install._after_link_publication",
                side_effect=replace_parent,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        if os.name == "nt":
            self.assertTrue(parent.is_dir())
            self.assertFalse(detached.exists())
            self.assertFalse(sentinel.exists())
            self.assertTrue((parent / "SKILL.md").is_file())
        else:
            self.assertEqual(b"external parent after link", sentinel.read_bytes())
            linked = detached / "SKILL.md"
            if linked.exists():
                self.assertIn("parent chain", str(raised.exception).lower())
        self.assertFalse((self.project / ".socratic-learn").exists())

    def test_parent_symlink_swap_preserves_external_directory(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        parent = self.project / ".cursor/skills/socratic-learn"
        detached = self.project / "detached-symlink-parent"
        outside = self.root / "outside-parent"
        outside.mkdir()
        sentinel = outside / "external.txt"
        sentinel.write_bytes(b"outside pre-existing bytes")
        injected = False

        def replace_parent_with_symlink(source: Path, destination: Path) -> None:
            nonlocal injected
            if injected or destination.parent != parent:
                return
            injected = True
            parent.rename(detached)
            try:
                parent.symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")

        with (
            mock.patch(
                "socratic_learn.install._before_link_publication",
                side_effect=replace_parent_with_symlink,
            ),
            self.assertRaises(FilesystemError),
        ):
            apply_install(plan)

        self.assertEqual(b"outside pre-existing bytes", sentinel.read_bytes())
        self.assertFalse((outside / "SKILL.md").exists())

    def test_failure_never_deletes_external_replacement_of_published_file(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        skill = self.project / ".cursor/skills/socratic-learn/SKILL.md"
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link_staged = install_module._link_staged_file
        publications = 0

        def fail_after_external_link(source: Path, destination: Path):
            nonlocal publications
            publications += 1
            if publications == 2:
                skill.unlink()
                skill.write_bytes(b"external before former cleanup")
                raise OSError("injected failure after external replacement")
            linked = real_link_staged(source, destination)
            return linked

        with (
            mock.patch(
                "socratic_learn.install._link_staged_file",
                side_effect=fail_after_external_link,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertEqual(b"external before former cleanup", skill.read_bytes())
        self.assertIn(str(skill), str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_failure_never_deletes_replaced_published_directory(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        native_directory = self.project / ".cursor/skills/socratic-learn"
        external = native_directory / "external.txt"
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link_staged = install_module._link_staged_file
        publications = 0

        def fail_after_native_link(source: Path, destination: Path):
            nonlocal publications
            publications += 1
            if publications == 2:
                (native_directory / "SKILL.md").unlink()
                native_directory.rmdir()
                native_directory.mkdir()
                external.write_bytes(b"external directory replacement")
                raise OSError("injected failure after directory replacement")
            linked = real_link_staged(source, destination)
            return linked

        with (
            mock.patch(
                "socratic_learn.install._link_staged_file",
                side_effect=fail_after_native_link,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertEqual(b"external directory replacement", external.read_bytes())
        self.assertIn(str(native_directory), str(raised.exception))

    def test_commit_time_empty_native_directory_races_abort(self) -> None:
        install_module = __import__("socratic_learn.install", fromlist=["_stage"])
        real_stage = install_module._stage
        for target, relative in (
            ("cursor", ".cursor/skills/socratic-learn"),
            ("pi", ".pi/skills/socratic-learn"),
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
                    "socratic_learn.install._stage",
                    side_effect=stage_then_race,
                ):
                    with self.assertRaises(CollisionError):
                        apply_install(plan)

                self.assertEqual([], list(external_directory.iterdir()))
                self.assertFalse((project / ".socratic-learn").exists())

    def test_generic_package_race_during_staging_preserves_external_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__("socratic_learn.install", fromlist=["_stage"])
        real_stage = install_module._stage
        external_root = self.project / ".socratic-learn"
        sentinel = external_root / "external.txt"

        def stage_then_race(current_plan):
            staged = real_stage(current_plan)
            external_root.mkdir()
            sentinel.write_bytes(b"external race winner")
            return staged

        with mock.patch("socratic_learn.install._stage", side_effect=stage_then_race):
            with self.assertRaises(CollisionError):
                apply_install(plan)

        self.assertEqual(b"external race winner", sentinel.read_bytes())
        self.assertEqual(["external.txt"], [path.name for path in external_root.iterdir()])
        self.assertFalse(
            any(
                path.name.startswith(
                    (".socratic-learn-stage-", ".socratic-learn-backup-")
                )
                for path in self.project.iterdir()
            )
        )

    def test_update_hashes_post_staging_backup_bytes(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__("socratic_learn.install", fromlist=["_stage"])
        real_stage = install_module._stage
        manifest = self.project / ".socratic-learn/manifest.json"

        def stage_then_modify(current_plan):
            staged = real_stage(current_plan)
            manifest.write_bytes(b"changed after preflight")
            return staged

        with mock.patch(
            "socratic_learn.install._stage",
            side_effect=stage_then_modify,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(1, len(backups))
        backup_manifest = backups[0] / ".socratic-learn/manifest.json"
        self.assertEqual(b"changed after preflight", backup_manifest.read_bytes())
        self.assertFalse(manifest.exists())
        self.assertIn(str(backup_manifest), str(raised.exception))
        self.assertTrue(
            any(path.name.startswith(".socratic-learn-stage-") for path in self.project.iterdir())
        )

    @unittest.skipUnless(os.name == "nt", "requires Windows source handle binding")
    def test_update_backup_rejects_final_source_replacement(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        manifest = self.project / ".socratic-learn/manifest.json"
        detached = self.project / "detached-manifest"
        original = manifest.read_bytes()
        injected = False

        def replace_source(source: Path, destination: Path) -> None:
            nonlocal injected
            if (
                not injected
                and source == manifest
                and destination.name == "manifest.json"
                and ".socratic-learn-backup-" in str(destination)
            ):
                injected = True
                manifest.rename(detached)
                manifest.write_bytes(b"external source replacement")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_replace",
                side_effect=replace_source,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(1, len(backups))
        backup_manifest = backups[0] / ".socratic-learn/manifest.json"
        self.assertTrue(injected)
        self.assertEqual(original, detached.read_bytes())
        self.assertEqual(b"external source replacement", manifest.read_bytes())
        self.assertFalse(backup_manifest.exists())
        self.assertIn(str(backup_manifest), str(raised.exception))
        self.assertTrue(
            any(path.name.startswith(".socratic-learn-stage-") for path in self.project.iterdir())
        )

    def test_update_identity_failure_after_backup_move_preserves_only_copy(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        relative = plan.previous_receipt.owned_paths[0]
        source = self.project.joinpath(*relative.split("/"))
        original = source.read_bytes()
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_path_identity"],
        )
        real_identity = install_module._path_identity

        def fail_backup_identity(path: Path):
            if (
                ".socratic-learn-backup-" in str(path)
                and path.as_posix().endswith(relative)
            ):
                raise OSError("injected backup identity failure")
            return real_identity(path)

        with (
            mock.patch(
                "socratic_learn.install._path_identity",
                side_effect=fail_backup_identity,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(1, len(backups))
        preserved = backups[0].joinpath(*relative.split("/"))
        self.assertEqual(original, preserved.read_bytes())
        self.assertFalse(source.exists())
        self.assertIn(str(backups[0]), str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_update_read_failure_after_backup_move_preserves_only_copy(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        relative = plan.previous_receipt.owned_paths[0]
        source = self.project.joinpath(*relative.split("/"))
        original = source.read_bytes()
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_read_bytes"],
        )
        real_read = install_module._read_bytes

        def fail_backup_read(path: Path, label: str):
            if label == "backup file":
                raise OSError("injected backup read failure")
            return real_read(path, label)

        with (
            mock.patch(
                "socratic_learn.install._read_bytes",
                side_effect=fail_backup_read,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(1, len(backups))
        preserved = backups[0].joinpath(*relative.split("/"))
        self.assertEqual(original, preserved.read_bytes())
        self.assertFalse(source.exists())
        self.assertIn(str(backups[0]), str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_update_restore_preserves_external_destination_and_backup(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        manifest = self.project / ".socratic-learn/manifest.json"
        real_link = os.link
        injected_restore_collision = False

        def fail_publication_and_collide_during_restore(
            source, destination, *args, **kwargs
        ):
            nonlocal injected_restore_collision
            source_path = Path(source)
            destination_path = Path(destination)
            if ".socratic-learn-stage-" in str(source_path):
                raise OSError("injected publication failure")
            if (
                not injected_restore_collision
                and ".socratic-learn-backup-" in str(source_path)
                and destination_path == manifest
            ):
                injected_restore_collision = True
                destination_path.write_bytes(b"external restore winner")
            real_link(source, destination, *args, **kwargs)

        with (
            mock.patch(
                "socratic_learn.install.os.link",
                side_effect=fail_publication_and_collide_during_restore,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(b"external restore winner", manifest.read_bytes())
        self.assertEqual(1, len(backups))
        backup_manifest = backups[0] / ".socratic-learn/manifest.json"
        self.assertTrue(backup_manifest.is_file())
        self.assertIn(str(manifest), str(raised.exception))
        self.assertIn(str(backup_manifest), str(raised.exception))

    def test_native_target_update_preserves_ownership_and_private_state(self) -> None:
        for target, skill_path in (
            ("cursor", ".cursor/skills/socratic-learn/SKILL.md"),
            ("pi", ".pi/skills/socratic-learn/SKILL.md"),
        ):
            with self.subTest(target=target):
                project = self.root / f"{target}-update"
                project.mkdir()
                apply_install(plan_install(self.source, project, target, False))
                private = project / ".socratic-learn/workspace/private.md"
                private.write_bytes(b"private")

                apply_install(plan_install(self.source, project, target, True))

                self.assertEqual(b"private", private.read_bytes())
                self.assertIn(skill_path, load_receipt(project)["owned_paths"])

    def test_update_rejects_a_different_requested_target(self) -> None:
        apply_install(plan_install(self.source, self.project, "cursor", False))

        with self.assertRaises(IntegrityError):
            plan_install(self.source, self.project, "pi", True)

        self.assertTrue(
            (self.project / ".cursor/skills/socratic-learn/SKILL.md").is_file()
        )
        self.assertFalse((self.project / ".pi").exists())

    def test_native_initial_commit_failure_preserves_published_directories(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)

        def fail_native_move(
            source: Path,
            destination: Path,
        ):
            if str(destination).endswith(
                os.path.join(".cursor", "skills", "socratic-learn", "SKILL.md")
            ):
                raise OSError("injected native move failure")
            raise AssertionError("native destination must be linked first")

        with mock.patch(
            "socratic_learn.install._link_staged_file",
            side_effect=fail_native_move,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertFalse((self.project / ".socratic-learn").exists())
        self.assertTrue((self.project / ".cursor/skills/socratic-learn").is_dir())
        self.assertIn(".cursor", str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)

    def test_unchanged_update_replaces_managed_files_and_preserves_private_state(self) -> None:
        self._install()
        private = self.project / ".socratic-learn/workspace/private.md"
        private.write_text("private", encoding="utf-8")
        new_prompt = b"# Universal Learning Tutor\nProtocol: 1.0.0\nUpdated.\n"
        self._make_distribution(new_prompt)

        apply_install(plan_install(self.source, self.project, "generic", True))

        self.assertEqual(
            new_prompt,
            (self.project / ".socratic-learn/socratic-learn.prompt.md").read_bytes(),
        )
        self.assertEqual("private", private.read_text(encoding="utf-8"))

    def test_update_unsupported_atomic_move_cleans_prepublication_state(self) -> None:
        self._install()
        before = self._snapshot()
        plan = plan_install(self.source, self.project, "generic", True)

        with (
            mock.patch(
                "socratic_learn.install.identity_bound_replace",
                side_effect=safe_fs.AtomicNoReplaceUnsupportedError(
                    "renameat2 with RENAME_NOREPLACE is unavailable"
                ),
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertEqual(before, self._snapshot())
        self.assertIn("RENAME_NOREPLACE", str(raised.exception))
        self.assertFalse(
            any(
                path.name.startswith(".socratic-learn-stage-")
                or path.name.startswith(".socratic-learn-backup-")
                for path in self.project.iterdir()
            )
        )

    def test_update_refuses_modified_or_missing_owned_file_before_mutation(self) -> None:
        for state in ("modified", "missing"):
            with self.subTest(state=state):
                if (self.project / ".socratic-learn").exists():
                    import shutil

                    shutil.rmtree(self.project / ".socratic-learn")
                self._install()
                managed = self.project / ".socratic-learn/loader.md"
                if state == "modified":
                    managed.write_text("user edit\n", encoding="utf-8")
                else:
                    managed.unlink()
                before = set(self.root.iterdir())

                with self.assertRaises(IntegrityError):
                    plan_install(self.source, self.project, "generic", True)

                self.assertEqual(before, set(self.root.iterdir()))
                self.assertFalse(any(path.name.startswith(".socratic-learn-stage-") for path in self.project.iterdir()))
                self.assertFalse(any(path.name.startswith(".socratic-learn-backup-") for path in self.project.iterdir()))

    def test_update_refuses_missing_invalid_or_escaping_receipt(self) -> None:
        for state in ("missing", "invalid", "escape"):
            with self.subTest(state=state):
                if (self.project / ".socratic-learn").exists():
                    import shutil

                    shutil.rmtree(self.project / ".socratic-learn")
                self._install()
                receipt_path = self.project / ".socratic-learn/install.json"
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
        receipt_path = self.project / ".socratic-learn/install.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned_paths"].remove(".socratic-learn/loader.md")
        receipt["hashes"].pop(".socratic-learn/loader.md")
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(CollisionError):
            plan_install(self.source, self.project, "generic", True)

        self.assertTrue((self.project / ".socratic-learn/loader.md").exists())

    def test_staging_failure_removes_only_operation_paths(self) -> None:
        sentinel = self.project / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        plan = plan_install(self.source, self.project, "generic", False)

        with mock.patch(
            "socratic_learn.install._write_staged_file",
            side_effect=OSError("injected staging failure"),
        ):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".socratic-learn").exists())
        self.assertFalse(any(path.name.startswith(".socratic-learn-stage-") for path in self.project.iterdir()))

    def test_staging_cleanup_preserves_raced_directory_replacement(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        detached = self.project / "detached-stage"
        replacement: Path | None = None

        def replace_stage_before_cleanup(directory):
            nonlocal replacement
            stage = directory.path
            stage.rename(detached)
            stage.mkdir()
            replacement = stage
            (stage / "external.txt").write_bytes(b"external stage replacement")

        with (
            mock.patch(
                "socratic_learn.install._write_staged_file",
                side_effect=OSError("injected staging failure"),
            ),
            mock.patch(
                "socratic_learn.safe_fs._before_identity_cleanup",
                side_effect=replace_stage_before_cleanup,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        assert replacement is not None
        self.assertEqual(
            b"external stage replacement",
            (replacement / "external.txt").read_bytes(),
        )
        self.assertTrue(detached.is_dir())
        self.assertIn(str(replacement), str(raised.exception))

    def test_staging_cleanup_unknown_child_preserves_complete_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_write_staged_file"],
        )
        real_write = install_module._write_staged_file
        writes = 0
        inserted: Path | None = None

        def fail_second(path: Path, content: bytes, *, root: Path) -> None:
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("injected staging failure")
            real_write(path, content, root=root)

        def insert_unknown(directory) -> None:
            nonlocal inserted
            inserted = directory.path / "external.txt"
            inserted.write_bytes(b"external")

        with (
            mock.patch(
                "socratic_learn.install._write_staged_file",
                side_effect=fail_second,
            ),
            mock.patch(
                "socratic_learn.safe_fs._before_identity_cleanup",
                side_effect=insert_unknown,
            ),
            self.assertRaises(FilesystemError),
        ):
            apply_install(plan)

        assert inserted is not None
        self.assertEqual(b"external", inserted.read_bytes())
        self.assertTrue((inserted.parent / ".socratic-learn/manifest.json").is_file())

    def test_parent_rename_diagnostic_reports_observed_identities_and_location(self) -> None:
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_parent_chain_publication_error"],
        )
        parent = self.project / "parent"
        parent.mkdir()
        source = parent / "source"
        source.write_bytes(b"source")
        destination = parent / "destination"
        parent_identity = safe_fs.path_identity(parent)
        source_identity = safe_fs.path_identity(source)
        detached = self.project / "renamed-parent"
        parent.rename(detached)
        parent.mkdir()

        error = install_module._parent_chain_publication_error(
            destination,
            project=self.project,
            source=source,
            source_identity=source_identity,
            original_parent=safe_fs.ParentIdentity(parent, parent_identity),
            published=True,
            original=OSError("injected parent rename"),
        )

        message = str(error)
        self.assertIn("original parent identity=", message)
        self.assertIn("observed parent identity=", message)
        self.assertIn("source expected identity=", message)
        self.assertIn("observed source identity=", message)
        self.assertIn("observed destination identity=", message)
        self.assertIn(str(detached), message)

    def test_staged_hash_mismatch_cleans_actual_stage_tree(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        bad_file = replace(plan.files[0], sha256="0" * 64)
        bad_plan = replace(plan, files=(bad_file, *plan.files[1:]))

        with self.assertRaisesRegex(IntegrityError, "staged file hash"):
            apply_install(bad_plan)

        self.assertFalse((self.project / ".socratic-learn").exists())
        self.assertFalse(
            any(
                path.name.startswith(".socratic-learn-stage-")
                for path in self.project.iterdir()
            )
        )

    def test_staging_and_cleanup_failure_reports_original_and_recovery_path(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)

        with (
            mock.patch(
                "socratic_learn.install._write_staged_file",
                side_effect=OSError("injected staging write failure"),
            ),
            mock.patch(
                "socratic_learn.install._remove_created_tree",
                side_effect=PermissionError("injected locked stage"),
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        message = str(raised.exception)
        self.assertIn("injected staging write failure", message)
        self.assertIn("injected locked stage", message)
        self.assertIn(".socratic-learn-stage-", message)
        stages = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-stage-")
        ]
        self.assertEqual(1, len(stages))
        self.assertEqual(stages[0], Path(raised.exception.path))

    def test_initial_commit_failure_preserves_preexisting_paths(self) -> None:
        sentinel = self.project / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        plan = plan_install(self.source, self.project, "generic", False)

        with mock.patch(
            "socratic_learn.install._link_staged_file",
            side_effect=OSError("injected commit failure"),
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertTrue((self.project / ".socratic-learn").is_dir())
        self.assert_posix_same_principal_limit(raised.exception)
        self.assertTrue(
            any(
                path.name.startswith(".socratic-learn-stage-")
                for path in self.project.iterdir()
            )
        )

    def test_initial_failure_after_publication_never_attempts_cleanup(self) -> None:
        plan = plan_install(self.source, self.project, "generic", False)
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link = install_module._link_staged_file
        links = 0

        def fail_second_link(source: Path, destination: Path):
            nonlocal links
            links += 1
            if links == 2:
                raise OSError("injected initial commit failure")
            return real_link(source, destination)

        with (
            mock.patch(
                "socratic_learn.install._link_staged_file",
                side_effect=fail_second_link,
            ),
            mock.patch(
                "pathlib.Path.rmdir",
                side_effect=AssertionError("published cleanup must not run"),
                autospec=True,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertIn("injected initial commit failure", str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)
        self.assertTrue((self.project / ".socratic-learn").is_dir())
        self.assertTrue(
            any(path.name.startswith(".socratic-learn-stage-") for path in self.project.iterdir())
        )

    def test_ambiguous_backup_move_failure_preserves_backup_tree(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        first_relative = plan.previous_receipt.owned_paths[0]
        first_source = self.project.joinpath(*first_relative.split("/"))
        first_bytes = first_source.read_bytes()
        safe_fs = __import__(
            "socratic_learn.safe_fs",
            fromlist=["_windows_handle_rename_no_replace"],
        )
        real_replace = safe_fs._windows_handle_rename_no_replace
        backup_moves = 0

        def fail_backup(source_descriptor: int, destination: Path) -> None:
            nonlocal backup_moves
            if ".socratic-learn-backup-" in str(destination):
                backup_moves += 1
                if backup_moves == 2:
                    raise OSError("injected backup failure")
            real_replace(source_descriptor, destination)

        with mock.patch(
            "socratic_learn.safe_fs._windows_handle_rename_no_replace",
            side_effect=fail_backup,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        backups = [
            path
            for path in self.project.iterdir()
            if path.name.startswith(".socratic-learn-backup-")
        ]
        self.assertEqual(1, len(backups))
        preserved = backups[0].joinpath(*first_relative.split("/"))
        self.assertEqual(first_bytes, preserved.read_bytes())
        self.assertFalse(first_source.exists())
        self.assertIn(str(backups[0]), str(raised.exception))

    def test_update_backup_move_binds_original_source_parent(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        managed = self.project / ".socratic-learn"
        detached = self.project / "detached-install"
        manifest = managed / "manifest.json"
        original = manifest.read_bytes()
        injected = False

        def replace_parent_before_backup(source, destination):
            nonlocal injected
            if (
                not injected
                and source == manifest
                and ".socratic-learn-backup-" in str(destination)
            ):
                injected = True
                managed.rename(detached)
                managed.mkdir()
                manifest.write_bytes(b"external backup race winner")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_replace",
                side_effect=replace_parent_before_backup,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        if os.name == "nt":
            self.assertEqual(original, manifest.read_bytes())
            self.assertFalse(detached.exists())
        else:
            self.assertEqual(b"external backup race winner", manifest.read_bytes())
            self.assertEqual(original, (detached / "manifest.json").read_bytes())
        self.assertIn("preserv", str(raised.exception).lower())

    def test_parent_mkdir_binds_original_ancestor(self) -> None:
        plan = plan_install(self.source, self.project, "cursor", False)
        cursor = self.project / ".cursor"
        detached = self.project / "detached-cursor"
        injected = False

        def replace_ancestor_before_mkdir(path: Path):
            nonlocal injected
            if not injected and path == cursor / "skills":
                injected = True
                cursor.rename(detached)
                cursor.mkdir()
                (cursor / "external.txt").write_bytes(b"external ancestor winner")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_mkdir",
                side_effect=replace_ancestor_before_mkdir,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        if os.name == "nt":
            self.assertTrue(cursor.is_dir())
            self.assertFalse(detached.exists())
            self.assertFalse((cursor / "external.txt").exists())
        else:
            self.assertEqual(
                b"external ancestor winner",
                (cursor / "external.txt").read_bytes(),
            )
        self.assertFalse((cursor / "skills").exists())
        self.assertIn("preserv", str(raised.exception).lower())

    def test_update_commit_failure_preserves_partial_recovery_state(self) -> None:
        self._install()
        before = self._snapshot()
        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\nNew.\n")
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__(
            "socratic_learn.install",
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
            "socratic_learn.install._link_staged_file",
            side_effect=fail_commit,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertNotEqual(before, self._snapshot())
        self.assert_posix_same_principal_limit(raised.exception)
        self.assertTrue(
            any(
                path.name.startswith((".socratic-learn-stage-", ".socratic-learn-backup-"))
                for path in self.project.iterdir()
            )
        )

    def test_integrity_error_after_first_update_publication_preserves_state(self) -> None:
        self._install()
        before = self._snapshot()
        self._make_distribution(b"# Universal Learning Tutor\nProtocol: 1.0.0\nNew.\n")
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__("socratic_learn.install", fromlist=["_project_path"])
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
                "socratic_learn.install._link_staged_file",
                side_effect=track_commit,
            ),
            mock.patch(
                "socratic_learn.install._project_path",
                side_effect=race_on_second_commit,
            ),
            self.assertRaises(FilesystemError) as raised,
        ):
            apply_install(plan)

        self.assertIn("injected symlink race", str(raised.exception))
        self.assertNotEqual(before, self._snapshot())
        self.assert_posix_same_principal_limit(raised.exception)
        self.assertTrue(
            any(
                path.name.startswith((".socratic-learn-stage-", ".socratic-learn-backup-"))
                for path in self.project.iterdir()
            )
        )

    def test_update_failure_preserves_operation_created_parent(self) -> None:
        self._install()
        workspace = self.project / ".socratic-learn/workspace"
        (workspace / ".gitkeep").unlink()
        workspace.rmdir()
        receipt_path = self.project / ".socratic-learn/install.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["owned_paths"].remove(".socratic-learn/workspace/.gitkeep")
        receipt["hashes"].pop(".socratic-learn/workspace/.gitkeep")
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        plan = plan_install(self.source, self.project, "generic", True)
        install_module = __import__(
            "socratic_learn.install",
            fromlist=["_link_staged_file"],
        )
        real_link_staged = install_module._link_staged_file

        def fail_after_parent_creation(source: Path, destination: Path):
            if destination.name == ".gitkeep":
                raise OSError("injected commit failure after parent creation")
            return real_link_staged(source, destination)

        with mock.patch(
            "socratic_learn.install._link_staged_file",
            side_effect=fail_after_parent_creation,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertTrue(workspace.is_dir())
        self.assertTrue((self.project / ".socratic-learn/loader.md").is_file())
        self.assertIn(str(workspace), str(raised.exception))

    def test_restore_failure_keeps_backup_and_reports_recovery_path(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        real_link = os.link

        def fail_commit_and_restore(
            source: str | os.PathLike[str],
            destination: str | os.PathLike[str],
            *args,
            **kwargs,
        ) -> None:
            source_path = Path(source)
            if ".socratic-learn-stage-" in str(source_path):
                raise OSError("injected commit failure")
            if ".socratic-learn-backup-" in str(source_path):
                raise OSError("injected restore failure")
            real_link(source, destination, *args, **kwargs)

        with mock.patch(
            "socratic_learn.install.os.link",
            side_effect=fail_commit_and_restore,
        ):
            with self.assertRaises(FilesystemError) as raised:
                apply_install(plan)

        self.assertIn(".socratic-learn-backup-", str(raised.exception))
        self.assert_posix_same_principal_limit(raised.exception)
        self.assertTrue(any(path.name.startswith(".socratic-learn-backup-") for path in self.project.iterdir()))

    def test_cli_prints_loader_and_update_transition(self) -> None:
        stdout = io.StringIO()
        with (
            mock.patch("socratic_learn.install.Path.cwd", return_value=self.source),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(0, main(["install", "generic", str(self.project)]))
        self.assertIn(".socratic-learn/socratic-learn.prompt.md", stdout.getvalue())

        stdout = io.StringIO()
        with (
            mock.patch("socratic_learn.install.Path.cwd", return_value=self.source),
            contextlib.redirect_stdout(stdout),
        ):
            self.assertEqual(0, main(["install", "generic", str(self.project), "--update"]))
        self.assertIn(f"{PROTOCOL_VERSION} -> {PROTOCOL_VERSION}", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
