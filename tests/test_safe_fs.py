from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from learning_tutor.safe_fs import (
    IdentityMismatchError,
    identity_bound_replace,
    path_identity,
    remove_tracked_tree,
    track_directory,
)


class SafeFilesystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    @unittest.skipUnless(os.name == "nt", "requires Windows handle rename")
    def test_destination_appearance_at_rename_boundary_is_not_overwritten(self) -> None:
        source = self.root / "source"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")

        def create_destination(_source: Path, _destination: Path) -> None:
            destination.write_bytes(b"external destination")

        with (
            mock.patch(
                "learning_tutor.safe_fs._before_bound_replace",
                side_effect=create_destination,
            ),
            self.assertRaises(FileExistsError),
        ):
            identity_bound_replace(source, destination, root=self.root)

        self.assertEqual(b"authorized source", source.read_bytes())
        self.assertEqual(b"external destination", destination.read_bytes())

    @unittest.skipUnless(os.name == "nt", "requires Windows source handle binding")
    def test_source_replacement_at_rename_boundary_is_preserved(self) -> None:
        source = self.root / "source"
        detached = self.root / "detached-source"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")
        identity = path_identity(source)

        def replace_source(_source: Path, _destination: Path) -> None:
            source.rename(detached)
            source.write_bytes(b"external replacement")

        with (
            mock.patch(
                "learning_tutor.safe_fs._before_bound_replace",
                side_effect=replace_source,
            ),
            self.assertRaises(IdentityMismatchError),
        ):
            identity_bound_replace(
                source,
                destination,
                root=self.root,
                expected_source=identity,
            )

        self.assertEqual(b"authorized source", detached.read_bytes())
        self.assertEqual(b"external replacement", source.read_bytes())
        self.assertFalse(destination.exists())

    @unittest.skipUnless(os.name == "nt", "requires Windows delete handles")
    def test_cleanup_root_cannot_be_replaced_at_delete_boundary(self) -> None:
        directory = self.root / "tracked"
        detached = self.root / "detached"
        directory.mkdir()
        (directory / "owned.txt").write_bytes(b"owned")
        tracked = track_directory(directory)
        attempted = False

        def replace_root(path: Path) -> None:
            nonlocal attempted
            if path != directory or attempted:
                return
            attempted = True
            directory.rename(detached)

        with (
            mock.patch(
                "learning_tutor.safe_fs._before_windows_handle_delete",
                side_effect=replace_root,
            ),
            self.assertRaises(OSError),
        ):
            remove_tracked_tree(tracked)

        self.assertTrue(attempted)
        self.assertEqual(b"owned", (directory / "owned.txt").read_bytes())
        self.assertFalse(detached.exists())

    def test_posix_replace_refuses_when_source_binding_is_unavailable(self) -> None:
        source = self.root / "source"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")

        with (
            mock.patch("learning_tutor.safe_fs.os.name", "posix"),
            self.assertRaisesRegex(IdentityMismatchError, "cannot prove"),
        ):
            identity_bound_replace(source, destination, root=self.root)

        self.assertEqual(b"authorized source", source.read_bytes())
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
