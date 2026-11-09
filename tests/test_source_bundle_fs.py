from __future__ import annotations

import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from socratic_learn.safe_fs import (
    IdentityMismatchError,
    PostMutationIdentityError,
    identity_bound_mkdir,
    publish_tracked_directory,
    track_directory,
)


def _make_directory_link(target: Path, link: Path) -> None:
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    link.symlink_to(target, target_is_directory=True)


class SourceBundleFilesystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_publish_rejects_linked_destination_ancestor(self) -> None:
        external = self.root / "external"
        external.mkdir()
        sources = self.root / "sources"
        try:
            _make_directory_link(external, sources)
        except OSError as error:
            self.skipTest(f"directory links unavailable: {error}")

        staging = identity_bound_mkdir(
            self.root / "staging",
            root=self.root,
        )
        (staging.path / "bundle.txt").write_bytes(b"staged")

        destination = sources / "bundle-id"
        marker = external / "must-not-appear"
        with self.assertRaises(IdentityMismatchError):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertFalse(marker.exists())
        self.assertFalse(destination.exists())
        self.assertTrue(staging.path.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_publish_rejects_real_junction_destination_ancestor(self) -> None:
        external = self.root / "junction-target"
        external.mkdir()
        sources = self.root / "sources"
        junction = subprocess.run(
            [
                os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                "/d",
                "/c",
                "mklink",
                "/J",
                str(sources),
                str(external),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if junction.returncode != 0:
            self.skipTest("directory junctions are unavailable")

        staging = identity_bound_mkdir(
            self.root / "staging",
            root=self.root,
        )
        (staging.path / "bundle.txt").write_bytes(b"staged")

        destination = sources / "bundle-id"
        with self.assertRaises(IdentityMismatchError):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertFalse((external / "bundle-id").exists())
        self.assertTrue(staging.path.is_dir())

    def test_publish_reuses_valid_existing_bundle(self) -> None:
        destination = self.root / "sources" / "bundle-id"
        destination.parent.mkdir(parents=True)
        destination.mkdir()
        (destination / "index.md").write_bytes(b"existing bundle")

        staging_path = self.root / "staging"
        staging_path.mkdir()
        (staging_path / "index.md").write_bytes(b"staged bundle")
        staging = track_directory(staging_path)

        result = publish_tracked_directory(
            staging,
            destination,
            root=self.root,
            validate_existing=lambda path: path == destination,
        )

        self.assertEqual(destination, result)
        self.assertEqual(b"existing bundle", (destination / "index.md").read_bytes())
        self.assertFalse(staging_path.exists())

    def test_publish_rejects_invalid_existing_bundle(self) -> None:
        destination = self.root / "sources" / "bundle-id"
        destination.parent.mkdir(parents=True)
        destination.mkdir()
        (destination / "index.md").write_bytes(b"existing bundle")

        staging_path = self.root / "staging"
        staging_path.mkdir()
        (staging_path / "index.md").write_bytes(b"staged bundle")
        staging = track_directory(staging_path)

        with self.assertRaises(IdentityMismatchError):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertEqual(b"existing bundle", (destination / "index.md").read_bytes())
        self.assertEqual(b"staged bundle", (staging_path / "index.md").read_bytes())
        self.assertTrue(staging_path.is_dir())

    def test_publish_removes_owned_staging_after_pre_publish_failure(self) -> None:
        staging_path = self.root / "staging"
        staging_path.mkdir()
        (staging_path / "index.md").write_bytes(b"staged bundle")
        staging = track_directory(staging_path)
        destination = self.root / "sources" / "bundle-id"
        destination.parent.mkdir(parents=True)

        def fail_before_rename(_source: Path, _destination: Path) -> None:
            raise OSError("injected pre-publish failure")

        with (
            mock.patch(
                "socratic_learn.safe_fs._before_bound_replace",
                side_effect=fail_before_rename,
            ),
            self.assertRaises(OSError),
        ):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertFalse(staging_path.exists())

    def test_publish_preserves_ambiguous_tree_after_identity_change(self) -> None:
        staging_path = self.root / "staging"
        staging_path.mkdir()
        owned = staging_path / "owned.txt"
        owned.write_bytes(b"owned")
        staging = track_directory(staging_path)
        destination = self.root / "sources" / "bundle-id"
        destination.parent.mkdir(parents=True)
        detached = self.root / "detached.txt"

        def replace_owned(_directory: object) -> None:
            owned.rename(detached)
            owned.write_bytes(b"external replacement")

        with (
            mock.patch(
                "socratic_learn.safe_fs.identity_bound_replace",
                side_effect=IdentityMismatchError("injected publish failure"),
            ),
            mock.patch(
                "socratic_learn.safe_fs._before_identity_cleanup",
                side_effect=replace_owned,
            ),
            self.assertRaises(IdentityMismatchError),
        ):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertTrue(staging_path.is_dir())
        self.assertEqual(b"external replacement", owned.read_bytes())
        self.assertEqual(b"owned", detached.read_bytes())
        self.assertFalse(destination.exists())

    def test_publish_preserves_tree_on_post_mutation_identity_error(self) -> None:
        staging_path = self.root / "staging"
        staging_path.mkdir()
        (staging_path / "index.md").write_bytes(b"staged bundle")
        staging = track_directory(staging_path)
        destination = self.root / "sources" / "bundle-id"
        destination.parent.mkdir(parents=True)

        with (
            mock.patch(
                "socratic_learn.safe_fs.identity_bound_replace",
                side_effect=PostMutationIdentityError("ambiguous recovery"),
            ),
            self.assertRaises(PostMutationIdentityError),
        ):
            publish_tracked_directory(
                staging,
                destination,
                root=self.root,
                validate_existing=lambda _path: False,
            )

        self.assertTrue(staging_path.is_dir())
        self.assertEqual(b"staged bundle", (staging_path / "index.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
