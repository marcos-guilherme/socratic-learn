from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from evaluation.isolation import (
    RULE_MARKERS,
    AboveHomeMarker,
    LocalRuleContamination,
    assert_no_local_rule_ancestors,
    assert_protocol_unchanged,
    capture_protocol_identity,
    create_run_layout,
    disclose_rule_markers,
    isolated_environment,
    load_runtime_context,
    remove_runtime_root,
    snapshot_learner_records,
)
from evaluation.antigravity import initial_bootstrap
from socratic_learn import PROTOCOL_VERSION
from socratic_learn.build import build_distribution
from socratic_learn.hosts import ADAPTERS, command_for


class EvaluationIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.outer = Path(temporary.name).resolve()
        self.user_home = self.outer / "home"
        self.repository = self.user_home / "projects" / "repo"
        self.repository.mkdir(parents=True)
        self.raw_root = self.repository / ".semantic-runs"
        self.runtime_base = self.user_home / "runtime"
        self.runtime_base.mkdir()

    def layout(self, scenario: str, **overrides: object):
        arguments = {
            "raw_root": self.raw_root,
            "runtime_base": self.runtime_base,
            "user_home": self.user_home,
        }
        arguments.update(overrides)
        return create_run_layout(self.repository, "suite", scenario, **arguments)

    def make_directory_link(self, target: Path, link: Path) -> None:
        try:
            if os.name == "nt":
                import _winapi

                _winapi.CreateJunction(str(target), str(link))
            else:
                link.symlink_to(target, target_is_directory=True)
        except (ImportError, OSError) as error:
            self.skipTest(f"directory links unavailable: {error}")

        def cleanup() -> None:
            if os.path.lexists(link):
                if link.is_symlink() or os.name == "nt":
                    os.unlink(link)
                else:
                    shutil.rmtree(link)

        self.addCleanup(cleanup)

    def test_raw_is_internal_and_runtime_is_external(self) -> None:
        layout = self.layout("conceptual-physics")

        self.assertEqual(self.raw_root / "suite" / "conceptual-physics", layout.run_dir)
        self.assertTrue(layout.raw.is_dir())
        self.assertTrue(layout.evaluator.is_dir())
        self.assertTrue(layout.raw.is_relative_to(layout.run_dir))
        self.assertEqual(self.runtime_base / "suite" / "conceptual-physics", layout.runtime_root)
        self.assertFalse(layout.owns_runtime_root)
        self.assertFalse(layout.home.is_relative_to(self.repository))
        self.assertFalse(layout.cwd.is_relative_to(self.repository))
        self.assertEqual(layout.home / "learning", layout.cwd)
        self.assertTrue(layout.protocol.is_file())

    def test_runtime_context_records_check_and_boundary_without_user_home(self) -> None:
        layout = self.layout("conceptual-physics")

        context = load_runtime_context(layout.run_dir)
        document = json.loads((layout.run_dir / "runtime-context.json").read_text("utf-8"))
        self.assertEqual(layout.runtime_root, context.runtime_root)
        self.assertTrue(context.runtime_outside_repository)
        self.assertTrue(context.local_rule_check_passed)
        self.assertEqual("user_home", context.rule_disclosure.boundary)
        self.assertEqual(
            {
                "runtime_root",
                "runtime_outside_repository",
                "local_rule_check_passed",
                "rule_boundary",
                "user_home_rule_paths",
                "above_home_markers",
            },
            set(document),
        )

    def test_scenarios_receive_separate_home_and_cwd(self) -> None:
        first = self.layout("conceptual-physics")
        second = self.layout("practical-programming")

        self.assertNotEqual(first.home, second.home)
        self.assertNotEqual(first.cwd, second.cwd)
        self.assertNotEqual(first.run_dir, second.run_dir)

    def test_live_default_runtime_is_secure_temporary_outside_repository(self) -> None:
        layout = create_run_layout(
            self.repository,
            "suite",
            "conceptual-physics",
            raw_root=self.raw_root,
            user_home=Path.home(),
        )
        try:
            self.assertTrue(layout.owns_runtime_root)
            self.assertTrue(layout.runtime_root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.assertFalse(layout.cwd.is_relative_to(self.repository))
        finally:
            remove_runtime_root(layout, self.repository)

    def test_runtime_mkdir_race_never_deletes_foreign_directory(self) -> None:
        foreign_root = self.runtime_base / "suite" / "conceptual-physics"
        foreign_root.parent.mkdir()
        sentinel = foreign_root / "foreign-sentinel.txt"
        real_mkdir = Path.mkdir

        def race(
            path: Path,
            mode: int = 0o777,
            parents: bool = False,
            exist_ok: bool = False,
        ) -> None:
            if path == foreign_root:
                os.mkdir(path)
                sentinel.write_text("foreign", encoding="utf-8")
                raise FileExistsError("foreign creator won")
            real_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

        with mock.patch("evaluation.isolation.Path.mkdir", autospec=True, side_effect=race):
            with self.assertRaises(FileExistsError):
                self.layout("conceptual-physics")

        self.assertEqual("foreign", sentinel.read_text(encoding="utf-8"))

    def test_runtime_inside_repository_is_rejected_before_creation(self) -> None:
        with self.assertRaises(ValueError):
            self.layout("conceptual-physics", runtime_base=self.repository / "runtime")
        with self.assertRaises(ValueError):
            self.layout("practical-programming", runtime_base=self.raw_root / "runtime")

        self.assertFalse((self.raw_root / "suite").exists())

    def test_raw_root_outside_repository_and_invalid_identifiers_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.layout("conceptual-physics", raw_root=self.outer / "raw")
        for identifier in ("../escape", "Uppercase", "two/slashes", ""):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    create_run_layout(
                        self.repository,
                        identifier,
                        "scenario",
                        raw_root=self.raw_root,
                        runtime_base=self.runtime_base,
                        user_home=self.user_home,
                    )

    def test_explicit_raw_root_rebases_like_macos_var_alias(self) -> None:
        lexical_repository = self.outer / "var-alias" / "project" / "repo"
        lexical_raw = lexical_repository / ".semantic-runs"

        import evaluation.isolation as isolation

        real_require = isolation._require_directory

        def resolve_linked_boundary(path: Path, label: str) -> Path:
            if label == "repository":
                self.assertEqual(lexical_repository, Path(path))
                return self.repository
            return real_require(path, label)

        with mock.patch(
            "evaluation.isolation._require_directory",
            side_effect=resolve_linked_boundary,
        ):
            layout = create_run_layout(
                lexical_repository,
                "suite",
                "macos-var-style",
                raw_root=lexical_raw,
                runtime_base=self.runtime_base,
                user_home=self.user_home,
            )

        self.assertEqual(
            self.repository / ".semantic-runs" / "suite" / "macos-var-style",
            layout.run_dir,
        )
        remove_runtime_root(layout, self.repository)

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_explicit_raw_root_rebases_through_real_junction_ancestor(self) -> None:
        physical_parent = self.outer / "physical-parent"
        physical_repository = physical_parent / "repo"
        physical_repository.mkdir(parents=True)
        alias_parent = self.outer / "junction-parent"
        self.make_directory_link(physical_parent, alias_parent)
        lexical_repository = alias_parent / "repo"

        layout = create_run_layout(
            lexical_repository,
            "suite",
            "junction-repository",
            raw_root=lexical_repository / ".semantic-runs",
            runtime_base=self.runtime_base,
            user_home=self.user_home,
        )

        self.assertEqual(
            physical_repository
            / ".semantic-runs"
            / "suite"
            / "junction-repository",
            layout.run_dir,
        )
        remove_runtime_root(layout, physical_repository)

    def test_explicit_raw_root_rejects_dotdot_escape_from_linked_repository(self) -> None:
        lexical_repository = self.outer / "alias" / "repo"
        escaping_raw = lexical_repository / ".semantic-runs" / ".." / ".." / "escape"

        import evaluation.isolation as isolation

        real_require = isolation._require_directory

        def resolve_linked_boundary(path: Path, label: str) -> Path:
            if label == "repository":
                return self.repository
            return real_require(path, label)

        with mock.patch(
            "evaluation.isolation._require_directory",
            side_effect=resolve_linked_boundary,
        ):
            with self.assertRaisesRegex(ValueError, "raw_root"):
                create_run_layout(
                    lexical_repository,
                    "suite",
                    "dotdot-escape",
                    raw_root=escaping_raw,
                    runtime_base=self.runtime_base,
                    user_home=self.user_home,
                )

        self.assertFalse((self.runtime_base / "suite" / "dotdot-escape").exists())

    @unittest.skipUnless(os.name == "nt", "Windows drive containment")
    def test_explicit_raw_root_rejects_another_drive(self) -> None:
        drive = "Z:" if self.repository.drive.upper() != "Z:" else "Y:"

        with self.assertRaisesRegex(ValueError, "raw_root"):
            self.layout("other-drive", raw_root=Path(f"{drive}/outside"))

        self.assertFalse((self.runtime_base / "suite" / "other-drive").exists())

    def test_explicit_raw_root_rejects_mocked_internal_reparse_escape(self) -> None:
        linked_component = self.repository / "linked"
        raw_root = linked_component / "raw"

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path == linked_component or real_check(path),
        ):
            with self.assertRaisesRegex(ValueError, "link|reparse"):
                self.layout("mocked-link-escape", raw_root=raw_root)

        self.assertFalse(
            (self.runtime_base / "suite" / "mocked-link-escape").exists()
        )

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_explicit_raw_root_rejects_real_internal_junction_escape(self) -> None:
        outside = self.outer / "outside-raw"
        outside.mkdir()
        linked_component = self.repository / "linked"
        self.make_directory_link(outside, linked_component)

        with self.assertRaisesRegex(ValueError, "link|reparse"):
            self.layout(
                "junction-link-escape",
                raw_root=linked_component / "raw",
            )

        self.assertFalse((outside / "raw").exists())

    def test_existing_run_and_runtime_roots_are_rejected(self) -> None:
        first = self.layout("conceptual-physics")
        with self.assertRaises(ValueError):
            self.layout("conceptual-physics")
        self.assertTrue(first.run_dir.is_dir())
        self.assertTrue(first.runtime_root.is_dir())

    def test_linked_ancestors_above_trusted_boundaries_are_allowed(self) -> None:
        runtime_base = self.user_home / "container" / "runtime"
        runtime_base.mkdir(parents=True)
        linked_ancestors = {self.repository.parent, runtime_base.parent}

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path in linked_ancestors or real_check(path),
        ):
            layout = self.layout("conceptual-physics", runtime_base=runtime_base)

        self.assertTrue(layout.runtime_root.is_dir())

    def test_local_rule_markers_below_user_home_are_rejected(self) -> None:
        for marker in RULE_MARKERS:
            with self.subTest(marker=marker):
                parent = self.user_home / f"ancestor-{marker.strip('.')}"
                cwd = parent / "child" / "learning"
                cwd.mkdir(parents=True)
                if marker.endswith(".md"):
                    (parent / marker).write_text("not read", encoding="utf-8")
                else:
                    (parent / marker).mkdir()
                with self.assertRaisesRegex(LocalRuleContamination, marker):
                    assert_no_local_rule_ancestors(cwd, self.user_home)

    def test_marker_in_cwd_itself_is_rejected_without_absolute_path(self) -> None:
        cwd = self.user_home / "work" / "learning"
        cwd.mkdir(parents=True)
        (cwd / "AGENTS.md").write_text("not read", encoding="utf-8")

        with self.assertRaises(LocalRuleContamination) as captured:
            assert_no_local_rule_ancestors(cwd, self.user_home)

        self.assertIn("AGENTS.md", str(captured.exception))
        self.assertIn("0 levels above cwd", str(captured.exception))
        self.assertNotIn(str(cwd), str(captured.exception))

    def test_cwd_outside_user_home_uses_filesystem_root_boundary(self) -> None:
        cwd = self.outer / "elsewhere" / "learning"
        cwd.mkdir(parents=True)
        real_lexists = os.path.lexists

        def scoped(path: object) -> bool:
            candidate = Path(path)
            return candidate.is_relative_to(self.outer) and real_lexists(path)

        with mock.patch("evaluation.isolation.os.path.lexists", side_effect=scoped):
            self.assertEqual(
                "filesystem_root",
                assert_no_local_rule_ancestors(cwd, self.user_home),
            )
            (self.outer / "elsewhere" / "CLAUDE.md").write_text(
                "not read", encoding="utf-8"
            )
            with self.assertRaises(LocalRuleContamination):
                assert_no_local_rule_ancestors(cwd, self.user_home)

    def test_user_level_rules_are_allowed_and_disclosed_by_name_only(self) -> None:
        (self.user_home / "AGENTS.md").write_text("private rule text", encoding="utf-8")
        (self.user_home / ".agents").mkdir()
        (self.user_home / ".gemini").mkdir()
        (self.user_home / ".gemini" / "GEMINI.md").write_text(
            "private", encoding="utf-8"
        )
        (self.outer / "GEMINI.md").write_text(
            "private above-home rule", encoding="utf-8"
        )
        cwd = self.user_home / "work" / "learning"
        cwd.mkdir(parents=True)

        with mock.patch("builtins.open", side_effect=AssertionError("must not read")):
            boundary = assert_no_local_rule_ancestors(cwd, self.user_home)
            disclosure = disclose_rule_markers(self.user_home, boundary)

        self.assertEqual(
            ("AGENTS.md", ".agents", ".gemini/GEMINI.md"),
            disclosure.user_home_rule_paths,
        )
        self.assertIn(AboveHomeMarker(1, "GEMINI.md"), disclosure.above_home_markers)
        encoded = json.dumps(
            [
                {"levels_above_home": item.levels_above_home, "marker": item.marker}
                for item in disclosure.above_home_markers
            ]
        )
        self.assertNotIn(str(self.outer), encoded)

    def test_rule_disclosure_uses_lexists_for_dangling_entries(self) -> None:
        expected = str(self.user_home / ".gemini" / "GEMINI.md")

        def fake_lexists(path: object) -> bool:
            return os.fspath(path) == expected

        with mock.patch(
            "evaluation.isolation.os.path.lexists", side_effect=fake_lexists
        ) as lexists:
            disclosure = disclose_rule_markers(self.user_home, "user_home")

        self.assertEqual((".gemini/GEMINI.md",), disclosure.user_home_rule_paths)
        self.assertGreater(lexists.call_count, 1)

    def test_filesystem_root_home_has_no_above_home_ancestor(self) -> None:
        filesystem_root = Path(self.outer.anchor)

        with mock.patch(
            "evaluation.isolation.os.path.lexists",
            side_effect=lambda path: Path(path) == filesystem_root / "AGENTS.md",
        ):
            disclosure = disclose_rule_markers(filesystem_root, "user_home")

        self.assertEqual(("AGENTS.md",), disclosure.user_home_rule_paths)
        self.assertEqual((), disclosure.above_home_markers)

    def test_layout_rejects_contaminated_external_runtime_and_cleans_it(self) -> None:
        (self.runtime_base / "GEMINI.md").write_text("not read", encoding="utf-8")

        with self.assertRaises(LocalRuleContamination):
            self.layout("conceptual-physics")

        self.assertFalse((self.runtime_base / "suite" / "conceptual-physics").exists())
        self.assertFalse((self.raw_root / "suite").exists())

    def test_snapshot_copies_regular_files_and_skips_linked_files(self) -> None:
        layout = self.layout("conceptual-physics")
        (layout.records / "progress.md").write_text(
            "learner record", encoding="utf-8"
        )
        outside = self.outer / "outside.txt"
        outside.write_text("must not be copied", encoding="utf-8")
        try:
            os.symlink(outside, layout.records / "linked.txt")
        except OSError:
            linked = False
        else:
            linked = True

        snapshot = snapshot_learner_records(layout)

        self.assertEqual(
            "learner record", (snapshot / "progress.md").read_text("utf-8")
        )
        self.assertFalse((snapshot / "linked.txt").exists())
        skipped = json.loads(
            (snapshot.parent / "skipped-links.json").read_text("utf-8")
        )
        self.assertEqual(["linked.txt"] if linked else [], skipped)
        self.assertFalse(any(Path(item).is_absolute() for item in skipped))

    def test_snapshot_prunes_mocked_reparse_directory_before_descent(self) -> None:
        layout = self.layout("conceptual-physics")
        junction = layout.records / "junction"
        junction.mkdir()
        (junction / "outside-record.md").write_text("must not copy", encoding="utf-8")

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse

        def classify(path: Path) -> bool:
            return path == junction or real_check(path)

        with mock.patch(
            "evaluation.isolation._is_link_or_reparse", side_effect=classify
        ):
            snapshot = snapshot_learner_records(layout)

        self.assertFalse((snapshot / "junction").exists())
        skipped = json.loads(
            (snapshot.parent / "skipped-links.json").read_text("utf-8")
        )
        self.assertIn("junction", skipped)
        self.assertNotIn("junction/outside-record.md", skipped)

    def test_snapshot_rejects_mocked_reparse_in_records_ancestry(self) -> None:
        layout = self.layout("conceptual-physics")

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path == layout.cwd or real_check(path),
        ):
            with self.assertRaisesRegex(ValueError, "link|reparse"):
                snapshot_learner_records(layout)

        self.assertFalse((layout.run_dir / "learner-records").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_snapshot_rejects_real_junction_in_records_ancestry(self) -> None:
        layout = self.layout("conceptual-physics")
        moved_workspace = self.outer / "moved-learning"
        layout.cwd.rename(moved_workspace)
        self.make_directory_link(moved_workspace, layout.cwd)

        with self.assertRaisesRegex(ValueError, "link|reparse"):
            snapshot_learner_records(layout)

        self.assertFalse((layout.run_dir / "learner-records").exists())

    def test_snapshot_refuses_linked_records_root(self) -> None:
        layout = self.layout("conceptual-physics")
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path == layout.records,
        ):
            with self.assertRaises(ValueError):
                snapshot_learner_records(layout)
        self.assertFalse((layout.run_dir / "learner-records").exists())

    def test_snapshot_raises_when_walk_cannot_read_directory(self) -> None:
        layout = self.layout("conceptual-physics")

        def unreadable_walk(
            *args: object,
            onerror: object = None,
            **kwargs: object,
        ):
            if callable(onerror):
                onerror(PermissionError("unreadable learner records"))
            return iter(())

        with mock.patch("evaluation.isolation.os.walk", side_effect=unreadable_walk):
            with self.assertRaises(PermissionError):
                snapshot_learner_records(layout)

        self.assertFalse((layout.run_dir / "learner-records").exists())

    def test_remove_runtime_root_deletes_only_per_run_runtime(self) -> None:
        layout = self.layout("conceptual-physics")
        layout.raw.mkdir(parents=True, exist_ok=True)

        remove_runtime_root(layout, self.repository)

        self.assertFalse(layout.runtime_root.exists())
        self.assertTrue(self.runtime_base.is_dir())
        self.assertTrue(layout.run_dir.is_dir())

    def test_cleanup_refuses_protected_ancestors_and_out_of_contract_root(self) -> None:
        layout = self.layout("conceptual-physics")
        unsafe_roots = (
            self.repository,
            self.raw_root,
            self.user_home,
            self.user_home.parent,
            self.repository.parent,
        )
        for unsafe_root in unsafe_roots:
            with self.subTest(unsafe_root=unsafe_root):
                with self.assertRaises(ValueError):
                    remove_runtime_root(
                        replace(layout, runtime_root=unsafe_root),
                        self.repository,
                    )
                self.assertTrue(unsafe_root.exists())
        unrelated = self.outer / "unrelated"
        unrelated.mkdir()
        with self.assertRaises(ValueError):
            remove_runtime_root(
                replace(layout, runtime_root=unrelated),
                self.repository,
            )
        self.assertTrue(unrelated.is_dir())

    def test_cleanup_removes_mocked_internal_reparse_entry(self) -> None:
        layout = self.layout("conceptual-physics")
        reparse = layout.runtime_root / "home" / "mocked-junction"
        reparse.mkdir()
        (reparse / "private.txt").write_text("private", encoding="utf-8")

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path == reparse or real_check(path),
        ):
            remove_runtime_root(layout, self.repository)

        self.assertFalse(layout.runtime_root.exists())

    def test_cleanup_removes_internal_link_without_following_target(self) -> None:
        layout = self.layout("conceptual-physics")
        target = self.outer / "junction-target"
        target.mkdir()
        sentinel = target / "outside.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        self.make_directory_link(target, layout.runtime_root / "internal-link")

        remove_runtime_root(layout, self.repository)

        self.assertFalse(layout.runtime_root.exists())
        self.assertEqual("preserve", sentinel.read_text(encoding="utf-8"))

    def test_cleanup_refuses_mocked_reparse_in_runtime_ancestry(self) -> None:
        layout = self.layout("conceptual-physics")
        unsafe_ancestor = layout.runtime_root.parent

        import evaluation.isolation as isolation

        real_check = isolation._is_link_or_reparse
        with mock.patch(
            "evaluation.isolation._is_link_or_reparse",
            side_effect=lambda path: path == unsafe_ancestor or real_check(path),
        ):
            with self.assertRaisesRegex(ValueError, "link|reparse"):
                remove_runtime_root(layout, self.repository)

        self.assertTrue(layout.runtime_root.is_dir())

    def test_rollback_removes_internal_link_and_preserves_target(self) -> None:
        runtime_root = self.runtime_base / "suite" / "conceptual-physics"
        target = self.outer / "rollback-target"
        target.mkdir()
        sentinel = target / "outside.txt"
        sentinel.write_text("preserve", encoding="utf-8")

        class WorkspaceFailure(RuntimeError):
            pass

        def fail_workspace(home: Path) -> None:
            self.make_directory_link(target, home.parent / "internal-link")
            raise WorkspaceFailure("original workspace failure")

        with mock.patch(
            "evaluation.isolation.prepare_personal_workspace",
            side_effect=fail_workspace,
        ):
            with self.assertRaisesRegex(WorkspaceFailure, "original workspace failure"):
                self.layout("conceptual-physics")

        self.assertFalse(runtime_root.exists())
        self.assertEqual("preserve", sentinel.read_text(encoding="utf-8"))

    def test_rollback_preserves_original_exception_when_cleanup_fails(self) -> None:
        class WorkspaceFailure(RuntimeError):
            pass

        with (
            mock.patch(
                "evaluation.isolation.prepare_personal_workspace",
                side_effect=WorkspaceFailure("original workspace failure"),
            ),
            mock.patch(
                "evaluation.isolation._remove_created_runtime",
                side_effect=OSError("cleanup failure"),
            ),
        ):
            with self.assertRaisesRegex(
                WorkspaceFailure,
                "original workspace failure",
            ):
                self.layout("conceptual-physics")

    def test_environment_inherits_auth_home_and_userprofile_without_mutation(self) -> None:
        parent = {
            "PATH": "C:/bin",
            "ANTIGRAVITY_AUTH_STATE": "opaque-parent-value",
            "HOME": "C:/Users/tester",
            "USERPROFILE": "C:/Users/tester-profile",
        }
        layout = type("Layout", (), {"home": Path("C:/private/home")})()

        child = isolated_environment(layout, parent)

        self.assertEqual("opaque-parent-value", child["ANTIGRAVITY_AUTH_STATE"])
        self.assertEqual("C:/Users/tester", child["HOME"])
        self.assertEqual("C:/Users/tester-profile", child["USERPROFILE"])
        self.assertEqual(str(Path("C:/private/home")), child["SOCRATIC_LEARN_HOME"])
        self.assertEqual("1", child["PYTHONDONTWRITEBYTECODE"])
        self.assertNotIn("SOCRATIC_LEARN_HOME", parent)


class ProtocolIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = Path(__file__).resolve().parents[1]

    def test_protocol_identity_uses_commit_version_and_built_bundle_hash(self) -> None:
        identity = capture_protocol_identity(self.repository)
        bundle = (
            self.repository / "dist" / "socratic-learn.prompt.md"
        ).read_bytes()

        self.assertRegex(identity.repository_commit, r"^[0-9a-f]{40,64}$")
        self.assertEqual(PROTOCOL_VERSION, identity.protocol_version)
        self.assertEqual(hashlib.sha256(bundle).hexdigest(), identity.bundle_sha256)

    def test_checked_in_protocol_matches_in_memory_distribution(self) -> None:
        self.assertEqual(
            (self.repository / "dist/socratic-learn.prompt.md").read_bytes(),
            build_distribution(self.repository).bundle,
        )

    def test_external_layout_bootstrap_and_protocol_match_public_launcher(self) -> None:
        root = self.repository
        with (
            tempfile.TemporaryDirectory() as repository_base,
            tempfile.TemporaryDirectory() as runtime_base,
        ):
            repository = Path(repository_base) / "repo"
            repository.mkdir()
            (repository / ".gitignore").write_text(
                "/.semantic-runs/\n",
                encoding="utf-8",
            )
            layout = create_run_layout(
                repository,
                "suite",
                "conceptual-physics",
                raw_root=repository / ".semantic-runs",
                runtime_base=Path(runtime_base),
                user_home=Path(runtime_base),
            )
            try:
                self.assertFalse(layout.cwd.resolve().is_relative_to(root))
                self.assertFalse(layout.cwd.resolve().is_relative_to(repository))
                self.assertEqual(
                    build_distribution(root).bundle,
                    layout.protocol.read_bytes(),
                )
                goal = "learn cafés"
                public = command_for(
                    ADAPTERS["antigravity"],
                    "agy",
                    layout.protocol,
                    goal,
                )
                self.assertEqual(
                    public[2],
                    initial_bootstrap(layout.protocol, goal),
                )
            finally:
                remove_runtime_root(layout, repository)

    def test_protocol_identity_detects_each_mismatch(self) -> None:
        identity = capture_protocol_identity(self.repository)
        mismatches = (
            replace(identity, repository_commit="0" * len(identity.repository_commit)),
            replace(identity, protocol_version="different"),
            replace(identity, bundle_sha256="0" * 64),
        )

        for expected in mismatches:
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError):
                    assert_protocol_unchanged(expected, self.repository)

    def test_protocol_identity_detects_checked_in_distribution_drift(self) -> None:
        from socratic_learn.build import BuildResult, build_distribution

        built = build_distribution(self.repository)
        drifted = BuildResult(bundle=built.bundle + b"drift", manifest=built.manifest)
        with mock.patch(
            "evaluation.isolation.build_distribution", return_value=drifted
        ):
            with self.assertRaises(ValueError):
                capture_protocol_identity(self.repository)

    def test_protocol_identity_normalizes_missing_git_executable(self) -> None:
        with mock.patch(
            "evaluation.isolation.subprocess.run",
            side_effect=FileNotFoundError("private executable path"),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "^repository commit could not be captured$",
            ) as captured:
                capture_protocol_identity(self.repository)

        self.assertNotIn("private", str(captured.exception))
        self.assertNotIn("git", str(captured.exception))

    def test_protocol_identity_normalizes_git_command_failure(self) -> None:
        failure = subprocess.CalledProcessError(
            128,
            ("git", "rev-parse", "HEAD"),
            stderr="private repository path",
        )
        with mock.patch("evaluation.isolation.subprocess.run", side_effect=failure):
            with self.assertRaisesRegex(
                ValueError,
                "^repository commit could not be captured$",
            ) as captured:
                capture_protocol_identity(self.repository)

        self.assertNotIn("private", str(captured.exception))
        self.assertNotIn("rev-parse", str(captured.exception))
