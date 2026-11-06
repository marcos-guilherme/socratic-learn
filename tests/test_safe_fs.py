from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import learning_tutor.safe_fs as safe_fs
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

    def test_linux_backend_uses_renameat2_noreplace(self) -> None:
        native = mock.Mock(return_value=0)

        with (
            mock.patch.object(safe_fs.sys, "platform", "linux"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=native,
            ),
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

        native.assert_called_once_with(3, b"source", 4, b"destination", 1)

    def test_macos_backend_uses_renameatx_np_excl(self) -> None:
        native = mock.Mock(return_value=0)

        with (
            mock.patch.object(safe_fs.sys, "platform", "darwin"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=native,
            ),
        ):
            safe_fs._native_posix_rename_no_replace(5, "source", 6, "destination")

        native.assert_called_once_with(5, b"source", 6, b"destination", 4)

    def test_posix_backend_maps_destination_collision(self) -> None:
        def destination_exists(*_arguments: object) -> int:
            ctypes.set_errno(errno.EEXIST)
            return -1

        with (
            mock.patch.object(safe_fs.sys, "platform", "linux"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=destination_exists,
            ),
            self.assertRaises(FileExistsError),
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

    def test_posix_backend_preserves_other_errno(self) -> None:
        def permission_denied(*_arguments: object) -> int:
            ctypes.set_errno(errno.EACCES)
            return -1

        with (
            mock.patch.object(safe_fs.sys, "platform", "linux"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=permission_denied,
            ),
            self.assertRaises(OSError) as raised,
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

        self.assertEqual(errno.EACCES, raised.exception.errno)

    def test_linux_backend_refuses_unsupported_filesystem(self) -> None:
        def unsupported(*_arguments: object) -> int:
            ctypes.set_errno(errno.EINVAL)
            return -1

        with (
            mock.patch.object(safe_fs.sys, "platform", "linux"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=unsupported,
            ),
            self.assertRaisesRegex(IdentityMismatchError, "RENAME_NOREPLACE"),
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

    def test_macos_backend_refuses_unsupported_filesystem(self) -> None:
        def unsupported(*_arguments: object) -> int:
            ctypes.set_errno(errno.ENOTSUP)
            return -1

        with (
            mock.patch.object(safe_fs.sys, "platform", "darwin"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=unsupported,
            ),
            self.assertRaisesRegex(IdentityMismatchError, "RENAME_EXCL"),
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

    def test_posix_backend_refuses_missing_native_api(self) -> None:
        with (
            mock.patch.object(safe_fs.sys, "platform", "linux"),
            mock.patch.object(
                safe_fs,
                "_load_posix_symbol",
                return_value=None,
            ),
            self.assertRaisesRegex(IdentityMismatchError, "renameat2"),
        ):
            safe_fs._native_posix_rename_no_replace(3, "source", 4, "destination")

    def test_posix_source_replacement_is_rejected_before_native_rename(self) -> None:
        source = self.root / "source"
        detached = self.root / "detached"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")
        identity = path_identity(source)

        def replace_source(_source: Path, _destination: Path) -> None:
            source.rename(detached)
            source.write_bytes(b"external replacement")

        native = mock.Mock()
        with (
            mock.patch("learning_tutor.safe_fs.os.name", "posix"),
            mock.patch(
                "learning_tutor.safe_fs._open_verified_parent",
                side_effect=[10, 11],
            ),
            mock.patch("learning_tutor.safe_fs.os.close"),
            mock.patch(
                "learning_tutor.safe_fs._before_bound_replace",
                side_effect=replace_source,
            ),
            mock.patch(
                "learning_tutor.safe_fs._native_posix_rename_no_replace",
                native,
            ),
            self.assertRaises(IdentityMismatchError),
        ):
            identity_bound_replace(
                source,
                destination,
                root=self.root,
                expected_source=identity,
            )

        native.assert_not_called()
        self.assertEqual(b"authorized source", detached.read_bytes())
        self.assertEqual(b"external replacement", source.read_bytes())
        self.assertFalse(destination.exists())

    def test_posix_parent_replacement_is_rejected_before_native_rename(self) -> None:
        parent = self.root / "parent"
        detached = self.root / "detached"
        parent.mkdir()
        source = parent / "source"
        destination = parent / "destination"
        source.write_bytes(b"authorized source")

        def replace_parent(_source: Path, _destination: Path) -> None:
            parent.rename(detached)
            parent.mkdir()
            (parent / "source").write_bytes(b"external replacement")

        native = mock.Mock()
        with (
            mock.patch("learning_tutor.safe_fs.os.name", "posix"),
            mock.patch(
                "learning_tutor.safe_fs._open_verified_parent",
                side_effect=[10, 11],
            ),
            mock.patch("learning_tutor.safe_fs.os.close"),
            mock.patch(
                "learning_tutor.safe_fs._before_bound_replace",
                side_effect=replace_parent,
            ),
            mock.patch(
                "learning_tutor.safe_fs._native_posix_rename_no_replace",
                native,
            ),
            self.assertRaises(IdentityMismatchError),
        ):
            identity_bound_replace(source, destination, root=self.root)

        native.assert_not_called()
        self.assertEqual(b"authorized source", (detached / "source").read_bytes())
        self.assertEqual(b"external replacement", (parent / "source").read_bytes())

    def test_posix_success_is_verified_against_source_identity(self) -> None:
        source = self.root / "source"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")

        def rename(
            _source: Path,
            _destination: Path,
            _source_parent: int,
            _destination_parent: int,
            _identity: object,
        ) -> None:
            source.rename(destination)

        with (
            mock.patch("learning_tutor.safe_fs.os.name", "posix"),
            mock.patch(
                "learning_tutor.safe_fs._open_verified_parent",
                side_effect=[10, 11],
            ),
            mock.patch("learning_tutor.safe_fs.os.close"),
            mock.patch(
                "learning_tutor.safe_fs._posix_identity_bound_replace",
                side_effect=rename,
            ),
        ):
            moved = identity_bound_replace(source, destination, root=self.root)

        self.assertEqual(path_identity(destination), moved)
        self.assertEqual(b"authorized source", destination.read_bytes())
        self.assertFalse(source.exists())

    def test_posix_destination_race_is_not_overwritten(self) -> None:
        source = self.root / "source"
        destination = self.root / "destination"
        source.write_bytes(b"authorized source")

        def lose_race(
            _source: Path,
            _destination: Path,
            _source_parent: int,
            _destination_parent: int,
            _identity: object,
        ) -> None:
            destination.write_bytes(b"external destination")
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST))

        with (
            mock.patch("learning_tutor.safe_fs.os.name", "posix"),
            mock.patch(
                "learning_tutor.safe_fs._open_verified_parent",
                side_effect=[10, 11],
            ),
            mock.patch("learning_tutor.safe_fs.os.close"),
            mock.patch(
                "learning_tutor.safe_fs._posix_identity_bound_replace",
                side_effect=lose_race,
            ),
            self.assertRaises(FileExistsError),
        ):
            identity_bound_replace(source, destination, root=self.root)

        self.assertEqual(b"authorized source", source.read_bytes())
        self.assertEqual(b"external destination", destination.read_bytes())

    def test_posix_final_source_race_is_reversed_without_overwrite(self) -> None:
        source = self.root / "source"
        destination = self.root / "destination"
        expected = safe_fs.PathIdentity(1, 10)
        replacement = safe_fs.PathIdentity(1, 11)
        native = mock.Mock()

        with (
            mock.patch(
                "learning_tutor.safe_fs._posix_entry_identity",
                side_effect=[expected, expected, replacement],
            ),
            mock.patch(
                "learning_tutor.safe_fs._open_posix_source",
                return_value=12,
            ),
            mock.patch(
                "learning_tutor.safe_fs._native_posix_rename_no_replace",
                native,
            ),
            mock.patch("learning_tutor.safe_fs.os.close"),
            self.assertRaisesRegex(IdentityMismatchError, "was restored"),
        ):
            safe_fs._posix_identity_bound_replace(
                source,
                destination,
                3,
                4,
                expected,
            )

        self.assertEqual(
            [
                mock.call(3, "source", 4, "destination"),
                mock.call(4, "destination", 3, "source"),
            ],
            native.call_args_list,
        )

    @unittest.skipUnless(os.name == "posix", "requires a native POSIX kernel")
    def test_native_posix_move_in_subprocess(self) -> None:
        script = """
from pathlib import Path
import sys
from learning_tutor.safe_fs import identity_bound_replace
root = Path(sys.argv[1])
source = root / "source"
destination = root / "destination"
source.write_bytes(b"source")
identity_bound_replace(source, destination, root=root)
assert not source.exists()
assert destination.read_bytes() == b"source"
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.root)],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual("", completed.stderr)
        self.assertEqual(0, completed.returncode)


if __name__ == "__main__":
    unittest.main()
