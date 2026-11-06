from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.config import LauncherConfig, load_config, save_config
from socratic_learn.errors import IntegrityError


class LauncherConfigTests(unittest.TestCase):
    def test_missing_config_has_no_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                LauncherConfig(default_agent=None),
                load_config(Path(temporary) / "config.json"),
            )

    def test_round_trip_uses_schema_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            save_config(path, LauncherConfig(default_agent="pi"))
            self.assertEqual(LauncherConfig(default_agent="pi"), load_config(path))
            self.assertIn('"schema_version": 1', path.read_text("utf-8"))

    def test_corrupt_config_is_preserved_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(IntegrityError):
                load_config(path)
            self.assertEqual("{broken", path.read_text("utf-8"))

    def test_invalid_schema_shapes_are_rejected_with_remediation(self) -> None:
        invalid_documents = (
            [],
            {"schema_version": True, "default_agent": None},
            {"schema_version": 2, "default_agent": None},
            {"schema_version": 1, "default_agent": "unknown"},
            {"schema_version": 1, "default_agent": False},
            {"schema_version": 1, "default_agent": None, "extra": "value"},
            {"schema_version": 1},
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            for document in invalid_documents:
                with self.subTest(document=document):
                    path.write_text(json.dumps(document), encoding="utf-8")
                    with self.assertRaises(IntegrityError) as raised:
                        load_config(path)
                    self.assertEqual(path, raised.exception.path)
                    self.assertEqual(
                        "move the file aside and rerun socratic",
                        raised.exception.remediation,
                    )

    def test_save_creates_private_parent_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences" / "config.json"
            save_config(path, LauncherConfig(default_agent="claude"))
            if os.name == "posix":
                self.assertEqual(0o700, path.parent.stat().st_mode & 0o777)
                self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_save_rejects_symlinked_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("preserved", encoding="utf-8")
            path = root / "config.json"
            try:
                path.symlink_to(target)
            except OSError as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaises(IntegrityError):
                save_config(path, LauncherConfig(default_agent=None))
            self.assertEqual("preserved", target.read_text("utf-8"))

    def test_prepublication_failure_removes_only_created_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "config.json"
            unrelated = root / ".config.json.unrelated.tmp"
            unrelated.write_text("preserved", encoding="utf-8")
            with (
                mock.patch(
                    "socratic_learn.config.os.replace",
                    side_effect=OSError("publish failed"),
                ),
                self.assertRaises(OSError),
            ):
                save_config(path, LauncherConfig(default_agent="antigravity"))
            self.assertEqual("preserved", unrelated.read_text("utf-8"))
            self.assertEqual([unrelated], list(root.iterdir()))
