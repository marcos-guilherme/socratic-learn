from __future__ import annotations

import contextlib
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

    def test_only_generic_target_is_implemented(self) -> None:
        for target in ("cursor", "claude-code", "pi", "unknown"):
            with self.subTest(target=target):
                with self.assertRaises(UsageError):
                    plan_install(self.source, self.project, target, False)

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

    def test_initial_commit_failure_preserves_preexisting_paths(self) -> None:
        sentinel = self.project / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        plan = plan_install(self.source, self.project, "generic", False)
        real_replace = os.replace

        def fail_commit(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            if ".learning-tutor-stage-" in str(source):
                raise OSError("injected commit failure")
            real_replace(source, destination)

        with mock.patch("learning_tutor.install.os.replace", side_effect=fail_commit):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual("keep", sentinel.read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".learning-tutor").exists())

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
        real_replace = os.replace
        committed = 0

        def fail_commit(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
            nonlocal committed
            if ".learning-tutor-stage-" in str(source) and ".learning-tutor" in str(destination):
                committed += 1
                if committed == 2:
                    raise OSError("injected update commit failure")
            real_replace(source, destination)

        with mock.patch("learning_tutor.install.os.replace", side_effect=fail_commit):
            with self.assertRaises(FilesystemError):
                apply_install(plan)

        self.assertEqual(before, self._snapshot())

    def test_rollback_failure_keeps_backup_and_reports_recovery_path(self) -> None:
        self._install()
        plan = plan_install(self.source, self.project, "generic", True)
        real_replace = os.replace

        def fail_commit_and_rollback(
            source: str | os.PathLike[str],
            destination: str | os.PathLike[str],
        ) -> None:
            source_path = Path(source)
            destination_path = Path(destination)
            if ".learning-tutor-stage-" in str(source_path):
                raise OSError("injected commit failure")
            if ".learning-tutor-backup-" in str(source_path):
                raise OSError("injected rollback failure")
            real_replace(source_path, destination_path)

        with mock.patch("learning_tutor.install.os.replace", side_effect=fail_commit_and_rollback):
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
