from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from socratic_learn.errors import IntegrityError
from socratic_learn.install import apply_install, load_receipt, plan_install
from socratic_learn.resources import resource_bytes
from socratic_learn.resources import packaged_distribution_root
from socratic_learn.workspace import (
    launcher_home,
    prepare_here_workspace,
    prepare_personal_workspace,
)


class WorkspaceTests(unittest.TestCase):
    def test_packaged_learner_profile_matches_repository_template(self) -> None:
        repository_template = (
            Path(__file__).resolve().parents[1] / "templates/learner-profile.md"
        )
        self.assertEqual(
            repository_template.read_bytes(),
            resource_bytes("templates/learner-profile.md"),
        )

    def test_home_override_is_test_only_boundary(self) -> None:
        self.assertEqual(
            Path("C:/isolated"),
            launcher_home({"SOCRATIC_LEARN_HOME": "C:/isolated"}),
        )

    def test_personal_workspace_is_idempotent_and_preserves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            first = prepare_personal_workspace(home)
            profile = first.records / "learner-profile.md"
            profile.write_text("private learner evidence\n", encoding="utf-8")
            second = prepare_personal_workspace(home)
            self.assertEqual(first, second)
            self.assertEqual("private learner evidence\n", profile.read_text("utf-8"))
            self.assertEqual(home / "learning", second.root)
            self.assertTrue((second.records / "learning-goal.md").is_file())
            self.assertTrue((second.records / "progress.md").is_file())
            self.assertTrue((second.records / "sessions").is_dir())

    def test_here_mode_reuses_existing_target_without_retargeting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            first = prepare_here_workspace(project)
            second = prepare_here_workspace(project)
            self.assertEqual(first.protocol, second.protocol)
            self.assertEqual(
                project / ".socratic-learn/socratic-learn.prompt.md",
                second.protocol,
            )

    def test_here_mode_retains_existing_native_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            with packaged_distribution_root() as source:
                apply_install(plan_install(source, project, "cursor", False))

            prepare_here_workspace(project)

            self.assertEqual("cursor", load_receipt(project)["target"])
            self.assertTrue(
                (project / ".cursor/skills/socratic-learn/SKILL.md").is_file()
            )

    def test_workspace_preparation_does_not_print_installer_loader(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            output = StringIO()

            with redirect_stdout(output):
                prepare_here_workspace(project)

            self.assertEqual("", output.getvalue())

    def test_personal_workspace_rejects_non_directory_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.write_text("not a directory", encoding="utf-8")

            with self.assertRaises(IntegrityError):
                prepare_personal_workspace(home)
