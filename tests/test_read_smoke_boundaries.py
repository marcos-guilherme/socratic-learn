from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.read_smoke import (
    PrivateBoundaryContext,
    assert_no_repository_mutation,
    assert_private_bundle_boundary,
    repository_state,
)


class PrivateBoundaryTests(unittest.TestCase):
    def test_rejects_touched_sibling_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            (home / "learning").mkdir(parents=True)
            (home / "learning" / ".socratic-learn" / "workspace" / "sources" / "x").mkdir(
                parents=True
            )
            sibling = root / "sibling" / "sentinel.bin"
            sibling.parent.mkdir(parents=True)
            sibling.write_bytes(b"before")
            sibling.write_bytes(b"after")
            context = PrivateBoundaryContext(
                isolated_home=home,
                repository=root,
                sibling_sentinel=sibling,
                sentinel_before=b"before",
            )
            with self.assertRaisesRegex(AssertionError, "sibling tree"):
                assert_private_bundle_boundary(context)

    def test_rejects_missing_home_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            sibling = root / "sibling" / "sentinel.bin"
            sibling.parent.mkdir(parents=True)
            sentinel = b"\x01"
            sibling.write_bytes(sentinel)
            context = PrivateBoundaryContext(
                isolated_home=home,
                repository=root,
                sibling_sentinel=sibling,
                sentinel_before=sentinel,
            )
            with self.assertRaisesRegex(AssertionError, "expected a private source bundle"):
                assert_private_bundle_boundary(context)

    def test_rejects_repository_workspace_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            bundle = (
                home
                / "learning"
                / ".socratic-learn"
                / "workspace"
                / "sources"
                / "abc"
            )
            bundle.mkdir(parents=True)
            repo_bundle = root / ".socratic-learn" / "workspace" / "sources" / "leaked"
            repo_bundle.mkdir(parents=True)
            sibling = root / "sibling" / "sentinel.bin"
            sibling.parent.mkdir(parents=True)
            sentinel = b"\x01"
            sibling.write_bytes(sentinel)
            context = PrivateBoundaryContext(
                isolated_home=home,
                repository=root,
                sibling_sentinel=sibling,
                sentinel_before=sentinel,
            )
            with self.assertRaisesRegex(AssertionError, "repository must not gain"):
                assert_private_bundle_boundary(context)

    def test_rejects_learner_bundle_inside_wheel_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            (
                home
                / "learning"
                / ".socratic-learn"
                / "workspace"
                / "sources"
                / "ok"
            ).mkdir(parents=True)
            wheel = root / "artifact.whl"
            bundle_id = "a" * 64
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(f"sources/{bundle_id}/index.md", "leak")
            sibling = root / "sibling" / "sentinel.bin"
            sibling.parent.mkdir(parents=True)
            sentinel = b"\x01"
            sibling.write_bytes(sentinel)
            context = PrivateBoundaryContext(
                isolated_home=home,
                repository=root,
                sibling_sentinel=sibling,
                sentinel_before=sentinel,
                package_artifacts=(wheel,),
            )
            with self.assertRaisesRegex(AssertionError, "package artifact must not"):
                assert_private_bundle_boundary(context)

    def test_accepts_layout_without_wheel_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            (
                home
                / "learning"
                / ".socratic-learn"
                / "workspace"
                / "sources"
                / "ok"
            ).mkdir(parents=True)
            sibling = root / "sibling" / "sentinel.bin"
            sibling.parent.mkdir(parents=True)
            sentinel = b"\x01"
            sibling.write_bytes(sentinel)
            frozen = root / "socratic-frozen.exe"
            frozen.write_bytes(b"MZ")
            context = PrivateBoundaryContext(
                isolated_home=home,
                repository=root,
                sibling_sentinel=sibling,
                sentinel_before=sentinel,
                package_artifacts=(frozen,),
            )
            assert_private_bundle_boundary(context)

    def test_repository_mutation_helper_detects_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess_git_init = __import__("subprocess").run
            subprocess_git_init(["git", "init", "-q"], cwd=root, check=True)
            subprocess_git_init(
                ["git", "config", "user.email", "smoke@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess_git_init(
                ["git", "config", "user.name", "read smoke"],
                cwd=root,
                check=True,
            )
            subprocess_git_init(
                ["git", "commit", "--allow-empty", "-m", "seed", "-q"],
                cwd=root,
                check=True,
            )
            marker = root / "new.txt"
            before = repository_state(root)
            marker.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "must not mutate"):
                assert_no_repository_mutation(root, before)


if __name__ == "__main__":
    unittest.main()
