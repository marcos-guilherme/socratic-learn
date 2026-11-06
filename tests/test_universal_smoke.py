from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from learning_tutor import TARGETS
from learning_tutor.build import build_distribution
from learning_tutor.doctor import diagnose
from learning_tutor.errors import IntegrityError
from learning_tutor.install import apply_install, plan_install


class UniversalSmokeTests(unittest.TestCase):
    def _tracked_copy(self, destination: Path) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        for raw_relative in result.stdout.split(b"\0"):
            if not raw_relative:
                continue
            relative = raw_relative.decode("utf-8")
            source = root / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    @staticmethod
    def _snapshot(project: Path) -> dict[str, bytes]:
        return {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(project).parts
        }

    def test_tracked_copy_end_to_end_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            self._tracked_copy(source)

            first = build_distribution(source)
            second = build_distribution(source)
            self.assertEqual(first.bundle, second.bundle)
            self.assertEqual(first.manifest, second.manifest)
            self.assertEqual(
                first.bundle,
                (source / "dist/learning-tutor.prompt.md").read_bytes(),
            )
            self.assertEqual(
                first.manifest,
                (source / "dist/manifest.json").read_bytes(),
            )

            projects: dict[str, Path] = {}
            for target in TARGETS:
                with self.subTest(target=target):
                    project = root / f"project-{target}"
                    project.mkdir()
                    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

                    apply_install(plan_install(source, project, target, False))
                    self.assertEqual([], diagnose(project))

                    private = project / ".learning-tutor/workspace/private.md"
                    private.write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")
                    ignored = subprocess.run(
                        ["git", "check-ignore", "--quiet", str(private)],
                        cwd=project,
                        check=False,
                    )
                    self.assertEqual(0, ignored.returncode)

                    apply_install(plan_install(source, project, target, True))
                    self.assertEqual([], diagnose(project))
                    projects[target] = project

            tampered = projects["generic"] / ".learning-tutor/loader.md"
            tampered.write_text("user change\n", encoding="utf-8")
            before = self._snapshot(projects["generic"])
            with self.assertRaises(IntegrityError):
                plan_install(source, projects["generic"], "generic", True)
            self.assertEqual(before, self._snapshot(projects["generic"]))


if __name__ == "__main__":
    unittest.main()
