from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagingTests(unittest.TestCase):
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
