from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.errors import IntegrityError, UsageError
from socratic_learn.release import ReleaseArtifact
from socratic_learn.self_manage import (
    InstallChannel,
    load_install_channel,
    uninstall,
    update_installation,
)


MANIFEST_URL = (
    "https://github.com/marcos-guilherme/socratic-learn/"
    "releases/latest/download/release-manifest.json"
)


def write_native_channel(
    home: Path,
    executable_path: Path,
    **overrides: object,
) -> None:
    document: dict[str, object] = {
        "schema_version": 1,
        "channel": "native",
        "executable": str(executable_path.absolute()),
        "manifest_url": MANIFEST_URL,
    }
    document.update(overrides)
    home.mkdir(parents=True, exist_ok=True)
    (home / "channel.json").write_text(json.dumps(document), encoding="utf-8")


def fake_manifest(url: str) -> bytes:
    payload = b"new"
    return json.dumps(
        {
            "schema_version": 1,
            "version": "0.1.0",
            "artifacts": [
                {
                    "platform": "windows",
                    "architecture": "x86_64",
                    "filename": "socratic-windows-x86_64.exe",
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ],
        }
    ).encode("utf-8")


def fake_artifact(artifact: ReleaseArtifact, destination: Path) -> Path:
    destination.write_bytes(b"new")
    return destination


class InstallChannelTests(unittest.TestCase):
    def test_absent_channel_means_python_install(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(load_install_channel(Path(temporary)))

    def test_loads_exact_native_channel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)

            self.assertEqual(
                InstallChannel(1, "native", executable.absolute(), MANIFEST_URL),
                load_install_channel(home),
            )

    def test_rejects_unknown_missing_and_invalid_channel_fields(self) -> None:
        cases = (
            {"extra": True},
            {"schema_version": 2},
            {"channel": "pipx"},
            {"executable": "relative/socratic"},
            {"manifest_url": ""},
        )
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "socratic"
            executable.write_bytes(b"old")
            for overrides in cases:
                with self.subTest(overrides=overrides):
                    write_native_channel(home, executable, **overrides)
                    with self.assertRaises(IntegrityError):
                        load_install_channel(home)

            document = {
                "schema_version": 1,
                "channel": "native",
                "executable": str(executable.absolute()),
            }
            (home / "channel.json").write_text(
                json.dumps(document), encoding="utf-8"
            )
            with self.assertRaises(IntegrityError):
                load_install_channel(home)

    def test_rejects_symlinked_metadata_and_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "socratic"
            executable.write_bytes(b"old")
            home = root / "home"
            write_native_channel(home, executable)
            channel = home / "channel.json"
            real_channel = root / "real-channel.json"
            channel.replace(real_channel)
            try:
                channel.symlink_to(real_channel)
            except OSError:
                self.skipTest("symbolic links are unavailable")
            with self.assertRaises(IntegrityError):
                load_install_channel(home)

            channel.unlink()
            real_channel.replace(channel)
            linked = root / "linked-socratic"
            linked.symlink_to(executable)
            write_native_channel(home, linked)
            with self.assertRaises(IntegrityError):
                load_install_channel(home)


class UpdateTests(unittest.TestCase):
    def test_python_install_reports_pipx_command_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            marker = home / "marker"
            marker.write_text("unchanged", encoding="utf-8")
            messages: list[str] = []

            self.assertEqual(
                0,
                update_installation(home, Path("python"), output=messages.append),
            )

            self.assertEqual(["Run: pipx upgrade socratic-learn"], messages)
            self.assertEqual("unchanged", marker.read_text(encoding="utf-8"))

    def test_native_executable_must_match_channel_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "socratic"
            executable.write_bytes(b"old")
            write_native_channel(home, executable)

            with self.assertRaises(IntegrityError):
                update_installation(home, home / "other")

    def test_posix_update_replaces_verified_artifact_and_sets_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)

            with (
                mock.patch(
                    "socratic_learn.self_manage._is_windows",
                    return_value=False,
                ),
                mock.patch.object(Path, "chmod", autospec=True) as chmod,
                mock.patch(
                    "socratic_learn.self_manage.current_platform",
                    return_value=("windows", "x86_64"),
                ),
            ):
                self.assertEqual(
                    0,
                    update_installation(
                        home,
                        executable,
                        fetch_manifest=fake_manifest,
                        fetch_artifact=fake_artifact,
                    ),
                )

            self.assertEqual(b"new", executable.read_bytes())
            self.assertEqual(0o755, chmod.call_args.args[1])
            self.assertEqual(
                {"socratic"}, {path.name for path in executable.parent.iterdir()}
            )

    def test_failed_native_replacement_preserves_old_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)
            with (
                mock.patch(
                    "socratic_learn.self_manage.current_platform",
                    return_value=("windows", "x86_64"),
                ),
                mock.patch(
                    "socratic_learn.self_manage._replace_native",
                    side_effect=OSError("blocked"),
                ),
                self.assertRaises(OSError),
            ):
                update_installation(
                    home,
                    executable,
                    fetch_manifest=fake_manifest,
                    fetch_artifact=fake_artifact,
                )

            self.assertEqual(b"old", executable.read_bytes())
            self.assertEqual(
                {"socratic"}, {path.name for path in executable.parent.iterdir()}
            )

    def test_windows_helper_embeds_base64_paths_and_not_raw_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="space's root ") as temporary:
            home = Path(temporary) / "learner home"
            executable = Path(temporary) / "bin's folder/socratic.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)
            scripts: list[str] = []

            def capture_popen(command: list[str], **kwargs: object) -> mock.Mock:
                scripts.append(Path(command[-1]).read_text(encoding="utf-8"))
                return mock.Mock()

            with (
                mock.patch(
                    "socratic_learn.self_manage._is_windows",
                    return_value=True,
                ),
                mock.patch(
                    "socratic_learn.self_manage.current_platform",
                    return_value=("windows", "x86_64"),
                ),
                mock.patch(
                    "socratic_learn.self_manage.subprocess.Popen",
                    side_effect=capture_popen,
                ),
            ):
                update_installation(
                    home,
                    executable,
                    fetch_manifest=fake_manifest,
                    fetch_artifact=fake_artifact,
                )

            script = scripts[0]
            self.assertNotIn(str(executable), script)
            encoded_values = [
                token
                for token in script.replace("'", " ").split()
                if len(token) > 8
                and all(character.isalnum() or character in "+/=" for character in token)
            ]
            decoded = []
            for value in encoded_values:
                try:
                    decoded.append(base64.b64decode(value).decode("utf-16le"))
                except (ValueError, UnicodeError):
                    pass
            self.assertIn(str(executable), decoded)
            self.assertTrue(
                any(
                    Path(value).parent == executable.parent
                    and Path(value) != executable
                    for value in decoded
                )
            )
            self.assertIn("[System.IO.File]::Move($staged, $destination, $true)", script)
            self.assertIn("Wait-Process", script)
            self.assertIn(
                "Remove-Item -LiteralPath $staged -Force "
                "-ErrorAction SilentlyContinue",
                script,
            )


class UninstallTests(unittest.TestCase):
    def test_python_install_reports_pipx_command_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            marker = home / "marker"
            marker.write_text("unchanged", encoding="utf-8")
            messages: list[str] = []

            self.assertEqual(
                0,
                uninstall(
                    home,
                    delete_data=False,
                    confirm=lambda prompt: True,
                    output=messages.append,
                ),
            )

            self.assertEqual(["Run: pipx uninstall socratic-learn"], messages)
            self.assertTrue(marker.exists())

    def test_uninstall_preserves_records_without_delete_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            record = home / "learning/.socratic-learn/workspace/progress.md"
            record.parent.mkdir(parents=True)
            record.write_text("private\n", encoding="utf-8")
            write_native_channel(home, executable)

            with mock.patch(
                "socratic_learn.self_manage._is_windows",
                return_value=False,
            ):
                uninstall(home, delete_data=False, confirm=lambda prompt: True)

            self.assertFalse(executable.exists())
            self.assertFalse((home / "channel.json").exists())
            self.assertEqual("private\n", record.read_text(encoding="utf-8"))

    def test_delete_data_requires_confirmation(self) -> None:
        prompt = (
            "Delete all Socratic Learn learner profiles, progress, and sessions? [y/N]"
        )
        for answer in ("", "n", "sure"):
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary)
                executable = home / "socratic"
                executable.write_bytes(b"old")
                write_native_channel(home, executable)
                prompts: list[str] = []

                with mock.patch(
                    "socratic_learn.self_manage._is_windows",
                    return_value=False,
                ):
                    result = uninstall(
                        home,
                        delete_data=True,
                        confirm=lambda value: prompts.append(value) or answer,
                    )

                self.assertEqual(0, result)
                self.assertEqual([prompt], prompts)
                self.assertTrue(executable.exists())
                self.assertTrue((home / "channel.json").exists())

    def test_confirmed_delete_data_removes_managed_home(self) -> None:
        for answer in ("y", "YES"):
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / "home"
                executable = Path(temporary) / "bin/socratic"
                executable.parent.mkdir()
                executable.write_bytes(b"old")
                record = home / "workspace/progress.md"
                record.parent.mkdir(parents=True)
                record.write_text("private", encoding="utf-8")
                write_native_channel(home, executable)

                with mock.patch(
                    "socratic_learn.self_manage._is_windows",
                    return_value=False,
                ):
                    uninstall(
                        home,
                        delete_data=True,
                        confirm=lambda prompt: answer,
                    )

                self.assertFalse(executable.exists())
                self.assertFalse(home.exists())

    def test_yes_without_delete_data_is_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(UsageError):
                uninstall(
                    Path(temporary),
                    delete_data=False,
                    confirm=lambda prompt: True,
                    yes=True,
                )


if __name__ == "__main__":
    unittest.main()
