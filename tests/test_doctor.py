from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from socratic_learn import PROTOCOL_VERSION
from socratic_learn.__main__ import main
from socratic_learn.conformance import Diagnostic
from socratic_learn.doctor import diagnose, format_diagnostics
from socratic_learn.errors import FilesystemError
from socratic_learn.install import (
    RECEIPT_PATH,
    _claude_snippet,
    apply_install,
    load_receipt,
    plan_install,
)
from socratic_learn.manifest import serialize_json
from tests.legacy_install_fixture import (
    create_valid_legacy_install,
    snapshot_tree,
)


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

    def test_doctor_reports_legacy_migration_without_mutation(self) -> None:
        project = self.root / "legacy"
        project.mkdir()
        create_valid_legacy_install(project, target="cursor")
        before = snapshot_tree(project)

        diagnostics = diagnose(project)

        self.assertIn("legacy-installation", self._codes(diagnostics))
        self.assertEqual(before, snapshot_tree(project))

    def test_doctor_reports_both_installation_roots_as_collision(self) -> None:
        project = self._installed()
        create_valid_legacy_install(project, target="generic")

        diagnostics = diagnose(project)

        self.assertIn("installation-root-collision", self._codes(diagnostics))

    def test_all_target_discovery_paths_are_healthy(self) -> None:
        cases = (
            ("generic", ".socratic-learn/loader.md"),
            ("cursor", ".cursor/skills/socratic-learn/SKILL.md"),
            ("claude-code", "CLAUDE.md"),
            ("pi", ".pi/skills/socratic-learn/SKILL.md"),
        )
        for target, discovery_path in cases:
            with self.subTest(target=target):
                project = self._installed(target)
                self.assertTrue((project / discovery_path).is_file())
                self.assertEqual([], diagnose(project))

    def test_claude_user_file_is_not_treated_as_owned_loader(self) -> None:
        project = self._installed("claude-code", existing_claude=True)
        receipt_path, receipt = self._receipt(project)
        original = (project / "CLAUDE.md").read_bytes()

        self.assertNotIn("CLAUDE.md", receipt["owned_paths"])
        diagnostic = next(
            item
            for item in diagnose(project)
            if item.code == "manual-integration-required"
        )
        self.assertEqual("CLAUDE.md", diagnostic.path)
        self.assertEqual(
            "append the exact emitted loader snippet to CLAUDE.md without replacing existing content",
            diagnostic.remediation,
        )
        self.assertEqual(original, (project / "CLAUDE.md").read_bytes())

        with (project / "CLAUDE.md").open("a", encoding="utf-8", newline="") as stream:
            stream.write("\r\n" + _claude_snippet().replace("\n", "\r\n"))

        self.assertEqual([], diagnose(project))
        self.assertTrue(receipt_path.is_file())

    def test_schema_two_receipts_remain_exact_and_update_compatible(self) -> None:
        receipt_keys = {
            "schema_version",
            "product",
            "protocol_version",
            "target",
            "owned_paths",
            "hashes",
        }
        cases = (
            ("generic", False),
            ("cursor", False),
            ("claude-code", False),
            ("claude-code", True),
            ("pi", False),
        )
        for index, (target, manual_claude) in enumerate(cases):
            with self.subTest(target=target, manual_claude=manual_claude):
                project = self.root / f"legacy-{index}-{target}"
                project.mkdir()
                if manual_claude:
                    (project / "CLAUDE.md").write_text(
                        "# User-owned Claude instructions\n",
                        encoding="utf-8",
                    )
                apply_install(plan_install(self.source, project, target, False))
                receipt_path, canonical_receipt = self._receipt(project)
                self.assertEqual(2, canonical_receipt["schema_version"])
                self.assertEqual("socratic-learn", canonical_receipt["product"])
                self.assertEqual(receipt_keys, set(canonical_receipt))
                self._write_receipt(receipt_path, canonical_receipt)
                if manual_claude:
                    with (project / "CLAUDE.md").open(
                        "a",
                        encoding="utf-8",
                        newline="",
                    ) as stream:
                        stream.write("\n" + _claude_snippet())

                self.assertEqual(receipt_keys, set(load_receipt(project)))
                self.assertEqual([], diagnose(project))

                apply_install(plan_install(self.source, project, target, True))

                self.assertEqual(receipt_keys, set(load_receipt(project)))
                self.assertEqual(receipt_keys, set(self._receipt(project)[1]))
                self.assertEqual([], diagnose(project))

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

    def test_partial_install_without_receipt_still_reports_unsafe_paths(self) -> None:
        project = self._installed()
        (project / RECEIPT_PATH).unlink()
        manifest = project / ".socratic-learn/manifest.json"
        real_stat = Path.stat

        def marked_stat(path: Path, *, follow_symlinks: bool = True):
            status = real_stat(path, follow_symlinks=follow_symlinks)
            if path != manifest or follow_symlinks:
                return status
            return SimpleNamespace(
                st_mode=status.st_mode,
                st_file_attributes=getattr(
                    stat,
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    1024,
                ),
            )

        with mock.patch("pathlib.Path.stat", autospec=True, side_effect=marked_stat):
            diagnostics = diagnose(project)

        self.assertIn("missing-receipt", self._codes(diagnostics))
        item = next(item for item in diagnostics if item.code == "unsafe-managed-path")
        self.assertEqual(".socratic-learn/manifest.json", item.path)

    def test_invalid_receipt_schema_is_actionable(self) -> None:
        project = self._installed()
        receipt_path, receipt = self._receipt(project)
        receipt["schema_version"] = 3
        self._write_receipt(receipt_path, receipt)

        diagnostic = diagnose(project)[0]

        self.assertEqual("invalid-receipt", diagnostic.code)
        self.assertEqual(RECEIPT_PATH, diagnostic.path)
        self.assertIn("schema version", diagnostic.message)
        self.assertIn("reinstall", diagnostic.remediation)

    def test_changed_and_missing_owned_files_are_distinct(self) -> None:
        changed = self._installed()
        (changed / ".socratic-learn/loader.md").write_text(
            "changed\n",
            encoding="utf-8",
        )
        self.assertIn("owned-file-changed", self._codes(diagnose(changed)))

        missing = self._installed()
        (missing / ".socratic-learn/loader.md").unlink()
        diagnostics = diagnose(missing)
        self.assertIn("owned-file-missing", self._codes(diagnostics))
        item = next(item for item in diagnostics if item.code == "owned-file-missing")
        self.assertEqual(".socratic-learn/loader.md", item.path)

    def test_bundle_hash_is_checked_against_installed_manifest(self) -> None:
        project = self._installed()
        manifest_path = project / ".socratic-learn/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundle"]["sha256"] = "0" * 64
        manifest_path.write_bytes(serialize_json(manifest))

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "bundle-hash-mismatch")
        self.assertEqual(".socratic-learn/socratic-learn.prompt.md", item.path)
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
        loader = project / ".socratic-learn/loader.md"
        loader.write_text(
            loader.read_text(encoding="utf-8").replace(
                ".socratic-learn/socratic-learn.prompt.md",
                ".socratic-learn/missing.prompt.md",
            ),
            encoding="utf-8",
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "broken-loader-link")
        self.assertEqual(".socratic-learn/loader.md", item.path)

    def test_wrong_native_discovery_path_is_reported(self) -> None:
        project = self._installed("cursor")
        cursor_skill = project / ".cursor/skills/socratic-learn/SKILL.md"
        wrong_skill = project / ".pi/skills/socratic-learn/SKILL.md"
        wrong_skill.parent.mkdir(parents=True)
        cursor_skill.replace(wrong_skill)

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "wrong-native-discovery-path")
        self.assertEqual(".cursor/skills/socratic-learn/SKILL.md", item.path)
        self.assertIn(".pi/skills/socratic-learn/SKILL.md", item.message)

    def test_wrong_known_discovery_paths_are_reported_for_every_owned_target(self) -> None:
        cases = (
            ("generic", ".socratic-learn/loader.md", ".cursor/skills/socratic-learn/SKILL.md"),
            ("cursor", ".cursor/skills/socratic-learn/SKILL.md", ".pi/skills/socratic-learn/SKILL.md"),
            ("claude-code", "CLAUDE.md", ".pi/skills/socratic-learn/SKILL.md"),
            ("pi", ".pi/skills/socratic-learn/SKILL.md", ".cursor/skills/socratic-learn/SKILL.md"),
        )
        for target, expected, wrong in cases:
            with self.subTest(target=target):
                project = self._installed(target)
                expected_path = project / expected
                wrong_path = project / wrong
                wrong_path.parent.mkdir(parents=True, exist_ok=True)
                if wrong_path.exists():
                    wrong_path.unlink()
                expected_path.replace(wrong_path)

                item = next(
                    item
                    for item in diagnose(project)
                    if item.code == "wrong-native-discovery-path"
                )
                self.assertEqual(expected, item.path)
                self.assertIn(wrong, item.message)

    def test_unreadable_wrong_discovery_candidate_is_actionable(self) -> None:
        project = self._installed("cursor")
        expected = project / ".cursor/skills/socratic-learn/SKILL.md"
        candidate = project / ".pi/skills/socratic-learn/SKILL.md"
        candidate.parent.mkdir(parents=True)
        expected.replace(candidate)
        candidate_status = candidate.stat()
        candidate_identity = (candidate_status.st_dev, candidate_status.st_ino)
        doctor_module = __import__(
            "socratic_learn.doctor",
            fromlist=["_read_descriptor"],
        )
        real_read_descriptor = doctor_module._read_descriptor

        def deny_candidate(descriptor: int) -> bytes:
            status = os.fstat(descriptor)
            if (status.st_dev, status.st_ino) == candidate_identity:
                raise PermissionError("injected candidate denial")
            return real_read_descriptor(descriptor)

        with mock.patch(
            "socratic_learn.doctor._read_descriptor",
            side_effect=deny_candidate,
        ):
            diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "managed-path-unreadable")
        self.assertEqual(".pi/skills/socratic-learn/SKILL.md", item.path)
        self.assertIn("injected candidate denial", item.message)

    def test_reparse_managed_path_is_rejected_before_read(self) -> None:
        project = self._installed()
        manifest = project / ".socratic-learn/manifest.json"
        real_stat = Path.stat
        real_read_bytes = Path.read_bytes
        read_attempted = False

        def marked_stat(path: Path, *, follow_symlinks: bool = True):
            status = real_stat(path, follow_symlinks=follow_symlinks)
            if path != manifest or follow_symlinks:
                return status
            return SimpleNamespace(
                st_mode=status.st_mode,
                st_file_attributes=getattr(
                    stat,
                    "FILE_ATTRIBUTE_REPARSE_POINT",
                    1024,
                ),
            )

        def guarded_read(path: Path) -> bytes:
            nonlocal read_attempted
            if path == manifest:
                read_attempted = True
            return real_read_bytes(path)

        with (
            mock.patch("pathlib.Path.stat", autospec=True, side_effect=marked_stat),
            mock.patch("pathlib.Path.read_bytes", autospec=True, side_effect=guarded_read),
        ):
            diagnostics = diagnose(project)

        self.assertFalse(read_attempted)
        item = next(item for item in diagnostics if item.code == "unsafe-managed-path")
        self.assertEqual(".socratic-learn/manifest.json", item.path)
        self.assertEqual(
            1,
            sum(
                item.code == "unsafe-managed-path"
                and item.path == ".socratic-learn/manifest.json"
                for item in diagnostics
            ),
        )

    def test_external_managed_symlink_is_rejected_without_reading_target(self) -> None:
        project = self._installed()
        manifest = project / ".socratic-learn/manifest.json"
        outside = self.root / "outside-manifest.json"
        outside.write_text('{"external": true}\n', encoding="utf-8")
        manifest.unlink()
        try:
            manifest.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"file symlinks unavailable: {error}")

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "unsafe-managed-path")
        self.assertEqual(".socratic-learn/manifest.json", item.path)
        self.assertEqual('{"external": true}\n', outside.read_text(encoding="utf-8"))

    def test_file_symlink_swap_before_open_never_consumes_external_bytes(self) -> None:
        project = self._installed()
        receipt = project / RECEIPT_PATH
        detached = project / "detached-receipt.json"
        outside = self.root / "outside-receipt.json"
        outside.write_bytes(b"external bytes must not be consumed")
        consumed_external = False

        def swap_file(current_project: Path, relative: str, path: Path) -> None:
            if relative != RECEIPT_PATH or detached.exists():
                return
            receipt.replace(detached)
            try:
                receipt.symlink_to(outside)
            except OSError as error:
                detached.replace(receipt)
                self.skipTest(f"file symlinks unavailable: {error}")

        doctor_module = __import__(
            "socratic_learn.doctor",
            fromlist=["_read_descriptor"],
        )
        real_read_descriptor = doctor_module._read_descriptor
        outside_identity = (outside.stat().st_dev, outside.stat().st_ino)

        def track_descriptor(descriptor: int) -> bytes:
            nonlocal consumed_external
            status = os.fstat(descriptor)
            if (status.st_dev, status.st_ino) == outside_identity:
                consumed_external = True
            return real_read_descriptor(descriptor)

        with (
            mock.patch(
                "socratic_learn.doctor._before_managed_open",
                side_effect=swap_file,
            ),
            mock.patch(
                "socratic_learn.doctor._read_descriptor",
                side_effect=track_descriptor,
            ),
        ):
            diagnostics = diagnose(project)

        self.assertFalse(consumed_external)
        self.assertIn("unsafe-managed-path", self._codes(diagnostics))
        self.assertEqual(b"external bytes must not be consumed", outside.read_bytes())

    def test_parent_swap_before_open_never_consumes_replacement_bytes(self) -> None:
        project = self._installed()
        install_root = project / ".socratic-learn"
        detached = project / "detached-socratic-learn"
        replacement_receipt = install_root / "install.json"
        consumed_replacement = False

        def swap_parent(current_project: Path, relative: str, path: Path) -> None:
            if relative != RECEIPT_PATH or detached.exists():
                return
            install_root.replace(detached)
            install_root.mkdir()
            replacement_receipt.write_bytes(b"replacement bytes must not be consumed")

        doctor_module = __import__(
            "socratic_learn.doctor",
            fromlist=["_read_descriptor"],
        )
        real_read_descriptor = doctor_module._read_descriptor

        def track_descriptor(descriptor: int) -> bytes:
            nonlocal consumed_replacement
            status = os.fstat(descriptor)
            if replacement_receipt.exists():
                replacement_status = replacement_receipt.stat()
                if (status.st_dev, status.st_ino) == (
                    replacement_status.st_dev,
                    replacement_status.st_ino,
                ):
                    consumed_replacement = True
            return real_read_descriptor(descriptor)

        with (
            mock.patch(
                "socratic_learn.doctor._before_managed_open",
                side_effect=swap_parent,
            ),
            mock.patch(
                "socratic_learn.doctor._read_descriptor",
                side_effect=track_descriptor,
            ),
        ):
            diagnostics = diagnose(project)

        self.assertFalse(consumed_replacement)
        self.assertIn("unsafe-managed-path", self._codes(diagnostics))
        self.assertEqual(
            b"replacement bytes must not be consumed",
            replacement_receipt.read_bytes(),
        )

    def test_missing_nested_ignore_rule_is_reported(self) -> None:
        project = self._installed()
        (project / ".socratic-learn/.gitignore").write_text(
            "workspace/*\n",
            encoding="utf-8",
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "missing-private-ignore-rule")
        self.assertEqual(".socratic-learn/.gitignore", item.path)
        self.assertIn("!workspace/.gitkeep", item.message)

    def test_tracked_private_file_is_reported_in_git_repository(self) -> None:
        project = self._installed()
        subprocess.run(
            ["git", "init", "-q", str(project)],
            check=True,
            capture_output=True,
        )
        private = project / ".socratic-learn/workspace/private.md"
        private.write_text("private\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(project), "add", "-f", ".socratic-learn/workspace/private.md"],
            check=True,
            capture_output=True,
        )

        diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "tracked-private-file")
        self.assertEqual(".socratic-learn/workspace/private.md", item.path)

    def test_git_failure_in_detected_repository_is_explicit(self) -> None:
        project = self._installed()
        (project / ".git").mkdir()
        failure = subprocess.CompletedProcess(
            args=["git"],
            returncode=128,
            stdout="",
            stderr="fatal: injected failure\n",
        )

        with mock.patch("socratic_learn.doctor.subprocess.run", return_value=failure):
            diagnostics = diagnose(project)

        item = next(item for item in diagnostics if item.code == "git-check-failed")
        self.assertEqual(".git", item.path)
        self.assertIn("injected failure", item.message)

    def test_diagnostics_and_formatting_are_deterministic(self) -> None:
        project = self._installed()
        (project / ".socratic-learn/loader.md").unlink()
        (project / ".socratic-learn/.gitignore").write_text("", encoding="utf-8")
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

        (project / ".socratic-learn/loader.md").unlink()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(4, main(["doctor", str(project)]))
        self.assertIn("[owned-file-missing]", stdout.getvalue())
        self.assertIn("Remediation:", stdout.getvalue())

    def test_cli_wraps_doctor_stdout_write_and_flush_failures(self) -> None:
        project = self._installed()

        class FailingStdout:
            def __init__(self, failure: str) -> None:
                self.failure = failure

            def write(self, value: str) -> int:
                if self.failure == "write":
                    raise OSError("injected stdout write failure")
                return len(value)

            def flush(self) -> None:
                if self.failure == "flush":
                    raise OSError("injected stdout flush failure")

        for failure in ("write", "flush"):
            with self.subTest(failure=failure):
                stderr = io.StringIO()
                with (
                    mock.patch("sys.stdout", FailingStdout(failure)),
                    contextlib.redirect_stderr(stderr),
                ):
                    self.assertEqual(5, main(["doctor", str(project)]))
                message = stderr.getvalue()
                self.assertIn("doctor output could not be written", message)
                self.assertIn("path: <stdout>", message)
                self.assertIn("check standard output and retry", message)

        (project / ".socratic-learn/loader.md").unlink()
        stderr = io.StringIO()
        with (
            mock.patch("sys.stdout", FailingStdout("write")),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(5, main(["doctor", str(project)]))

    def test_cli_does_not_mask_doctor_stdout_programmer_errors(self) -> None:
        project = self._installed()
        stream = mock.Mock()
        stream.write.side_effect = RuntimeError("programmer failure")

        with mock.patch("sys.stdout", stream):
            with self.assertRaisesRegex(RuntimeError, "programmer failure"):
                main(["doctor", str(project)])


if __name__ == "__main__":
    unittest.main()
