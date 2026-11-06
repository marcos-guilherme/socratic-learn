from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from learning_tutor import PROTOCOL_VERSION
from learning_tutor.__main__ import main
from learning_tutor.conformance import Diagnostic
from learning_tutor.doctor import diagnose, format_diagnostics
from learning_tutor.install import RECEIPT_PATH, apply_install, plan_install
from learning_tutor.manifest import serialize_json


class DoctorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = Path(__file__).resolve().parents[1]

    def _installed(
        self,
        target: str = "generic",
        *,
        existing_claude: bool = False,
    ) -> Path:
        project = self.root / f"{target}-{len(tuple(self.root.iterdir()))}"
        project.mkdir()
        if existing_claude:
            (project / "CLAUDE.md").write_text(
                "# User-owned Claude instructions\n",
                encoding="utf-8",
            )
        apply_install(plan_install(self.source, project, target, False))
        return project

    @staticmethod
    def _receipt(project: Path) -> tuple[Path, dict[str, object]]:
        path = project / RECEIPT_PATH
        return path, json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_receipt(path: Path, receipt: dict[str, object]) -> None:
        path.write_bytes(serialize_json(receipt))

    @staticmethod
    def _codes(diagnostics: list[Diagnostic]) -> list[str]:
        return [item.code for item in diagnostics]

    def test_all_target_discovery_paths_are_healthy(self) -> None:
        cases = (
            ("generic", ".learning-tutor/loader.md"),
            ("cursor", ".cursor/skills/learning-tutor/SKILL.md"),
            ("claude-code", "CLAUDE.md"),
            ("pi", ".pi/skills/learning-tutor/SKILL.md"),
        )
        for target, discovery_path in cases:
            with self.subTest(target=target):
                project = self._installed(target)
                self.assertTrue((project / discovery_path).is_file())
                self.assertEqual([], diagnose(project))

    def test_claude_user_file_is_not_treated_as_owned_loader(self) -> None:
        project = self._installed("claude-code", existing_claude=True)
        receipt_path, receipt = self._receipt(project)

        self.assertNotIn("CLAUDE.md", receipt["owned_paths"])
        self.assertEqual([], diagnose(project))
        self.assertEqual(
            "# User-owned Claude instructions\n",
            (project / "CLAUDE.md").read_text(encoding="utf-8"),
        )
        self.assertTrue(receipt_path.is_file())

    def test_missing_receipt_diagnoses_partial_install_without_mutation(self) -> None:
        project = self._installed()
        receipt_path = project / RECEIPT_PATH
        receipt_path.unlink()
        before = {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }

        diagnostics = diagnose(project)

        self.assertEqual(
            Diagnostic(
                "missing-receipt",
                RECEIPT_PATH,
                "installation files exist but the ownership receipt is missing",
                "preserve the partial installation and recovery artifacts, then reinstall only after manual review",
            ),
            diagnostics[0],
        )
        after = {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_invalid_receipt_schema_is_actionable(self) -> None:
        project = self._installed()
        receipt_path, receipt = self._receipt(project)
        receipt["schema_version"] = 2
        self._write_receipt(receipt_path, receipt)

        diagnostic = diagnose(project)[0]

        self.assertEqual("invalid-receipt", diagnostic.code)
        self.assertEqual(RECEIPT_PATH, diagnostic.path)
        self.assertIn("schema version", diagnostic.message)
        self.assertIn("reinstall", diagnostic.remediation)

    def test_changed_and_missing_owned_files_are_distinct(self) -> None:
        changed = self._installed()
        (changed / ".learning-tutor/loader.md").write_text(
            "changed\n",
            encoding="utf-8",
        )
        self.assertIn("owned-file-changed", self._codes(diagnose(changed)))

        missing = self._installed()
        (missing / ".learning-tutor/loader.md").unlink()
        diagnostics = diagnose(missing)
        self.assertIn("owned-file-missing", self._codes(diagnostics))
        item = next(item for item in diagnostics if item.code == "owned-file-missing")
        self.assertEqual(".learning-tutor/loader.md", item.path)

    def test_bundle_hash_is_checked_against_installed_manifest(self) -> None:
        project = self._installed()
        manifest_path = project / ".learning-tutor/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundle"]["sha256"] = "0" * 64
        manifest_path.write_bytes(serialize_json(manifest))

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "bundle-hash-mismatch")
        self.assertEqual(".learning-tutor/learning-tutor.prompt.md", item.path)
        self.assertIn("manifest", item.message)

    def test_receipt_protocol_mismatch_is_reported(self) -> None:
        project = self._installed()
        receipt_path, receipt = self._receipt(project)
        receipt["protocol_version"] = "0.9.0"
        self._write_receipt(receipt_path, receipt)

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "protocol-mismatch")
        self.assertEqual(RECEIPT_PATH, item.path)
        self.assertIn(PROTOCOL_VERSION, item.message)

    def test_broken_loader_reference_is_reported(self) -> None:
        project = self._installed()
        loader = project / ".learning-tutor/loader.md"
        loader.write_text(
            loader.read_text(encoding="utf-8").replace(
                ".learning-tutor/learning-tutor.prompt.md",
                ".learning-tutor/missing.prompt.md",
            ),
            encoding="utf-8",
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "broken-loader-link")
        self.assertEqual(".learning-tutor/loader.md", item.path)

    def test_wrong_native_discovery_path_is_reported(self) -> None:
        project = self._installed("cursor")
        cursor_skill = project / ".cursor/skills/learning-tutor/SKILL.md"
        wrong_skill = project / ".pi/skills/learning-tutor/SKILL.md"
        wrong_skill.parent.mkdir(parents=True)
        cursor_skill.replace(wrong_skill)

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "wrong-native-discovery-path")
        self.assertEqual(".cursor/skills/learning-tutor/SKILL.md", item.path)
        self.assertIn(".pi/skills/learning-tutor/SKILL.md", item.message)

    def test_missing_nested_ignore_rule_is_reported(self) -> None:
        project = self._installed()
        (project / ".learning-tutor/.gitignore").write_text(
            "workspace/*\n",
            encoding="utf-8",
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "missing-private-ignore-rule")
        self.assertEqual(".learning-tutor/.gitignore", item.path)
        self.assertIn("!workspace/.gitkeep", item.message)

    def test_tracked_private_file_is_reported_in_git_repository(self) -> None:
        project = self._installed()
        subprocess.run(
            ["git", "init", "-q", str(project)],
            check=True,
            capture_output=True,
        )
        private = project / ".learning-tutor/workspace/private.md"
        private.write_text("private\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(project), "add", "-f", ".learning-tutor/workspace/private.md"],
            check=True,
            capture_output=True,
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "tracked-private-file")
        self.assertEqual(".learning-tutor/workspace/private.md", item.path)

    def test_git_failure_in_detected_repository_is_explicit(self) -> None:
        project = self._installed()
        (project / ".git").mkdir()
        failure = subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="",
            stderr="fatal: injected failure\n",
        )

        with mock.patch("learning_tutor.doctor.subprocess.run", return_value=failure):
            diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "git-check-failed")
        self.assertEqual(".git", item.path)
        self.assertIn("injected failure", item.message)

    def test_diagnostics_and_formatting_are_deterministic(self) -> None:
        project = self._installed()
        (project / ".learning-tutor/loader.md").unlink()
        (project / ".learning-tutor/.gitignore").write_text("", encoding="utf-8")
        receipt_path, receipt = self._receipt(project)
        receipt["protocol_version"] = "0.9.0"
        self._write_receipt(receipt_path, receipt)

        first = diagnose(project)
        second = diagnose(project)

        keys = [(item.code, item.path) for item in first]
        self.assertEqual(sorted(keys), keys)
        self.assertEqual(first, second)
        self.assertEqual(format_diagnostics(first), format_diagnostics(second))
        self.assertTrue(format_diagnostics(first).endswith("\n"))

    def test_cli_reports_healthy_and_unhealthy_statuses(self) -> None:
        project = self._installed()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, main(["doctor", str(project)]))
        self.assertEqual("Installation healthy.\n", stdout.getvalue())

        (project / ".learning-tutor/loader.md").unlink()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(4, main(["doctor", str(project)]))
        self.assertIn("[owned-file-missing]", stdout.getvalue())
        self.assertIn("Remediation:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
