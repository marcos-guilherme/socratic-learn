from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


class UniversalSmokeTests(unittest.TestCase):
    TARGETS = ("generic", "cursor", "claude-code", "pi")

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
    def _isolated_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        return environment

    def _run_cli(
        self,
        source: Path,
        *arguments: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "learning_tutor", *arguments],
            cwd=source,
            env=self._isolated_environment(),
            check=check,
            capture_output=True,
            text=True,
        )

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

            self._run_cli(source, "build")
            first = {
                path.name: path.read_bytes()
                for path in (source / "dist").iterdir()
                if path.is_file()
            }
            self._run_cli(source, "build")
            second = {
                path.name: path.read_bytes()
                for path in (source / "dist").iterdir()
                if path.is_file()
            }
            self.assertEqual(first, second)

            projects: dict[str, Path] = {}
            for target in self.TARGETS:
                with self.subTest(target=target):
                    project = root / f"project-{target}"
                    project.mkdir()
                    subprocess.run(["git", "init", "-q"], cwd=project, check=True)

                    self._run_cli(source, "install", target, str(project))
                    doctor = self._run_cli(source, "doctor", str(project))
                    self.assertEqual("Installation healthy.\n", doctor.stdout)

                    private = project / ".learning-tutor/workspace/private.md"
                    private.write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")
                    ignored = subprocess.run(
                        ["git", "check-ignore", "--quiet", str(private)],
                        cwd=project,
                        check=False,
                    )
                    self.assertEqual(0, ignored.returncode)

                    self._run_cli(
                        source,
                        "install",
                        target,
                        str(project),
                        "--update",
                    )
                    doctor = self._run_cli(source, "doctor", str(project))
                    self.assertEqual("Installation healthy.\n", doctor.stdout)
                    projects[target] = project

            tampered = projects["generic"] / ".learning-tutor/loader.md"
            tampered.write_text("user change\n", encoding="utf-8")
            before = self._snapshot(projects["generic"])
            refused = self._run_cli(
                source,
                "install",
                "generic",
                str(projects["generic"]),
                "--update",
                check=False,
            )
            self.assertEqual(4, refused.returncode)
            self.assertIn("owned installation file was modified", refused.stderr)
            self.assertEqual(before, self._snapshot(projects["generic"]))

    def test_copied_runtime_removal_fails_without_live_checkout_fallback(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            project = root / "project"
            source.mkdir()
            project.mkdir()
            self._tracked_copy(source)
            (source / "learning_tutor/install.py").unlink()

            result = self._run_cli(
                source,
                "install",
                "generic",
                str(project),
                check=False,
            )

            self.assertEqual(4, result.returncode)
            self.assertIn("install implementation is unavailable", result.stderr)
            self.assertFalse((project / ".learning-tutor").exists())


if __name__ == "__main__":
    unittest.main()
