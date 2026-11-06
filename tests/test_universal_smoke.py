from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.legacy_install_fixture import create_valid_legacy_install


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
            [sys.executable, "-m", "socratic_learn", *arguments],
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

    @staticmethod
    def _repository_state(root: Path) -> tuple[bytes, bytes, bytes]:
        return tuple(
            subprocess.run(
                command,
                cwd=root,
                check=True,
                capture_output=True,
            ).stdout
            for command in (
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                ["git", "diff", "--binary"],
                ["git", "diff", "--cached", "--binary"],
            )
        )

    def test_installed_wheel_launches_fake_pi_end_to_end(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        before_repository = self._repository_state(repository)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            wheelhouse = root / "wheelhouse"
            wheelhouse.mkdir()
            build = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--outdir",
                    str(wheelhouse),
                ],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, build.returncode, build.stdout + build.stderr)
            wheels = tuple(wheelhouse.glob("socratic_learn-*.whl"))
            self.assertEqual(1, len(wheels), wheels)

            environment = root / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(environment)],
                check=True,
            )
            scripts = environment / ("Scripts" if os.name == "nt" else "bin")
            python = scripts / ("python.exe" if os.name == "nt" else "python")
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    "--no-deps",
                    str(wheels[0]),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            site_packages = Path(
                subprocess.run(
                    [
                        str(python),
                        "-c",
                        "import site; print(site.getsitepackages()[0])",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            record = root / "fake-pi-record.json"
            (site_packages / "fake_pi.py").write_text(
                "import json, os, sys\n"
                "def main():\n"
                "    record = {'argv': sys.argv[1:], 'cwd': os.getcwd()}\n"
                "    with open(os.environ['FAKE_PI_RECORD'], 'w', "
                "encoding='utf-8') as output:\n"
                "        json.dump(record, output)\n"
                "    return 17\n",
                encoding="utf-8",
            )
            make_fake = subprocess.run(
                [
                    str(python),
                    "-c",
                    (
                        "import sys; "
                        "from pip._vendor.distlib.scripts import ScriptMaker; "
                        f"maker=ScriptMaker(None, {str(scripts)!r}); "
                        "maker.executable=sys.executable; "
                        "maker.variants={''}; "
                        "maker.make('pi=fake_pi:main')"
                    ),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                0,
                make_fake.returncode,
                make_fake.stdout + make_fake.stderr,
            )

            home = root / "home"
            home.mkdir()
            run_environment = os.environ.copy()
            run_environment.update(
                {
                    "FAKE_PI_RECORD": str(record),
                    "HOME": str(home),
                    "PATH": str(scripts),
                    "SOCRATIC_LEARN_HOME": str(home),
                    "USERPROFILE": str(home),
                }
            )
            run_environment.pop("PYTHONPATH", None)
            console = scripts / ("socratic.exe" if os.name == "nt" else "socratic")
            first_run = subprocess.run(
                [str(console), "choose pi"],
                cwd=root,
                env=run_environment,
                input="1\n",
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                17,
                first_run.returncode,
                first_run.stdout + first_run.stderr,
            )
            self.assertEqual(
                {"schema_version": 1, "default_agent": "pi"},
                json.loads((home / "config.json").read_text(encoding="utf-8")),
            )

            result = subprocess.run(
                [
                    str(console),
                    "--agent",
                    "pi",
                    "learn graph theory",
                ],
                cwd=root,
                env=run_environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(17, result.returncode, result.stdout + result.stderr)
            invocation = json.loads(record.read_text(encoding="utf-8"))
            protocol = (
                home
                / "learning"
                / ".socratic-learn"
                / "socratic-learn.prompt.md"
            ).resolve()
            self.assertEqual(
                ["--append-system-prompt", str(protocol), "learn graph theory"],
                invocation["argv"],
            )
            self.assertEqual(str((home / "learning").resolve()), invocation["cwd"])
            private = home / "learning" / ".socratic-learn" / "workspace"
            self.assertTrue((private / "learner-profile.md").is_file())
            self.assertTrue((private / "learning-goal.md").is_file())
            self.assertTrue((private / "progress.md").is_file())
            self.assertTrue((private / "sessions").is_dir())

        self.assertEqual(
            before_repository,
            self._repository_state(repository),
            "installed-wheel acceptance must not mutate the source repository",
        )

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

                    private = project / ".socratic-learn/workspace/private.md"
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

            tampered = projects["generic"] / ".socratic-learn/loader.md"
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

            legacy = root / "project-legacy"
            legacy.mkdir()
            create_valid_legacy_install(legacy, target="generic")
            private = legacy / ".learning-tutor/workspace/private.md"
            private.write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")

            before_migration = self._run_cli(
                source,
                "doctor",
                str(legacy),
                check=False,
            )
            self.assertEqual(4, before_migration.returncode)
            self.assertIn("legacy-installation", before_migration.stdout)

            self._run_cli(
                source,
                "install",
                "generic",
                str(legacy),
                "--update",
            )
            self.assertFalse((legacy / ".learning-tutor").exists())
            self.assertEqual(
                "PRIVATE_LEARNER_DATA\n",
                (
                    legacy / ".socratic-learn/workspace/private.md"
                ).read_text(encoding="utf-8"),
            )
            migrated_doctor = self._run_cli(
                source,
                "doctor",
                str(legacy),
            )
            self.assertEqual("Installation healthy.\n", migrated_doctor.stdout)

    def test_copied_runtime_removal_fails_without_live_checkout_fallback(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            project = root / "project"
            source.mkdir()
            project.mkdir()
            self._tracked_copy(source)
            (source / "socratic_learn/install.py").unlink()

            result = self._run_cli(
                source,
                "install",
                "generic",
                str(project),
                check=False,
            )

            self.assertEqual(4, result.returncode)
            self.assertIn("install implementation is unavailable", result.stderr)
            self.assertFalse((project / ".socratic-learn").exists())


if __name__ == "__main__":
    unittest.main()
