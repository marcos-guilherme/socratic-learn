from __future__ import annotations

import json
import unittest
from pathlib import Path

from socratic_learn.resources import packaged_distribution_root, resource_bytes


class PackagedResourceTests(unittest.TestCase):
    def test_packaged_distribution_matches_checked_in_dist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (root / "dist/manifest.json").read_bytes(),
            resource_bytes("manifest.json"),
        )
        self.assertEqual(
            (root / "dist/socratic-learn.prompt.md").read_bytes(),
            resource_bytes("socratic-learn.prompt.md"),
        )

    def test_materialized_root_has_installer_layout(self) -> None:
        with packaged_distribution_root() as root:
            manifest = json.loads((root / "dist/manifest.json").read_text("utf-8"))
            self.assertEqual("socratic-learn", manifest["product"])
            self.assertTrue((root / "dist/socratic-learn.prompt.md").is_file())

    def test_unknown_resource_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resource_bytes("../LICENSE")
