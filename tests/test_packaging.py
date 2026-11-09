from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_runtime_declares_supported_pypdf_major(self) -> None:
        root = Path(__file__).resolve().parents[1]
        project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
        self.assertIn("pypdf>=7.0,<8", project["project"]["dependencies"])

    def test_native_spec_collects_pypdf(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "socratic-learn.spec").read_text("utf-8")
        self.assertIn('collect_submodules("pypdf")', text)

    def test_minimal_text_pdf_fixture_is_readable(self) -> None:
        from pypdf import PdfReader

        root = Path(__file__).resolve().parents[1]
        fixture = root / "tests/fixtures/sources/minimal-text.pdf"
        self.assertTrue(fixture.is_file(), "minimal-text.pdf must be committed")
        reader = PdfReader(fixture)
        self.assertIn("Evidence", reader.pages[0].extract_text() or "")

    def test_build_text_pdf_is_deterministic(self) -> None:
        from pypdf import PdfReader

        from tests.pdf_fixture import build_text_pdf

        pages = ("Evidence paragraph.", "Second page.")
        first = build_text_pdf(pages)
        second = build_text_pdf(pages)
        self.assertEqual(first, second)
        reader = PdfReader(io.BytesIO(first))
        self.assertEqual(2, len(reader.pages))

    def test_published_archives_exclude_private_evaluation_system(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(
                [sys.executable, "-m", "build", "--outdir", temporary],
                cwd=root,
                check=True,
            )
            wheel = next(Path(temporary).glob("*.whl"))
            sdist = next(Path(temporary).glob("*.tar.gz"))
            with zipfile.ZipFile(wheel) as archive:
                self.assertFalse(
                    any(
                        name.startswith("evaluation/")
                        or ".semantic-runs/" in name
                        for name in archive.namelist()
                    )
                )
            with tarfile.open(sdist, "r:gz") as archive:
                self.assertFalse(
                    any(
                        "/evaluation/" in name
                        or "/.semantic-runs/" in name
                        for name in archive.getnames()
                    )
                )

    def test_wheel_contains_console_entry_and_protocol(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", temporary],
                cwd=root,
                check=True,
            )
            wheel = next(Path(temporary).glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                self.assertIn(
                    "socratic_learn/data/socratic-learn.prompt.md",
                    names,
                )
                self.assertEqual(
                    (root / "templates/learner-profile.md").read_bytes(),
                    archive.read(
                        "socratic_learn/data/templates/learner-profile.md"
                    ),
                )
                entry_points = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                self.assertIn(
                    "socratic = socratic_learn.cli:entry_point",
                    archive.read(entry_points).decode("utf-8"),
                )

    def test_installed_console_version_preserves_module_cli(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            wheel_directory = temporary_path / "wheel"
            environment = temporary_path / "venv"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--outdir",
                    str(wheel_directory),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, "-m", "venv", str(environment)],
                check=True,
                capture_output=True,
                text=True,
            )
            scripts = environment / (
                "Scripts" if sys.platform == "win32" else "bin"
            )
            python = scripts / (
                "python.exe" if sys.platform == "win32" else "python"
            )
            console = scripts / (
                "socratic.exe" if sys.platform == "win32" else "socratic"
            )
            wheel = next(wheel_directory.glob("*.whl"))
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "--disable-pip-version-check",
                    "install",
                    str(wheel),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            dependency = subprocess.run(
                [str(python), "-c", "import pypdf; print(pypdf.__version__)"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, dependency.returncode, dependency.stderr)

            version = subprocess.run(
                [str(console), "--version"],
                cwd=temporary_path,
                capture_output=True,
                text=True,
                check=False,
            )
            module = subprocess.run(
                [str(python), "-m", "socratic_learn"],
                cwd=temporary_path,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, version.returncode, version.stderr)
            self.assertTrue(
                version.stdout.startswith("socratic-learn 0.1.0"),
                version.stdout,
            )
            self.assertEqual(2, module.returncode, module.stderr)
