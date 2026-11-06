from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.errors import IntegrityError, UsageError
from socratic_learn.release import ReleaseArtifact
from socratic_learn.self_manage import (
    InstallChannel,
    _replacement_script,
    _spawn_helper,
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

    def test_rejects_symlinked_executable_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_bin = root / "real-bin"
            real_bin.mkdir()
            executable = real_bin / "socratic"
            executable.write_bytes(b"old")
            linked_bin = root / "linked-bin"
            try:
                linked_bin.symlink_to(real_bin, target_is_directory=True)
            except OSError:
                self.skipTest("symbolic links are unavailable")
            home = root / "home"
            write_native_channel(home, linked_bin / "socratic")

            with self.assertRaisesRegex(IntegrityError, "symbolic|reparse"):
                load_install_channel(home)

    def test_rejects_launcher_home_through_symlinked_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "socratic"
            executable.write_bytes(b"old")
            real_parent = root / "real-parent"
            home = real_parent / "home"
            write_native_channel(home, executable)
            linked_parent = root / "linked-parent"
            try:
                linked_parent.symlink_to(real_parent, target_is_directory=True)
            except OSError:
                self.skipTest("symbolic links are unavailable")

            with self.assertRaisesRegex(IntegrityError, "symbolic|reparse"):
                load_install_channel(linked_parent / "home")


class UpdateTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows helper policy runs on Windows")
    def test_windows_helper_ignores_hostile_cwd_and_path_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hostile = root / "powershell.exe"
            hostile.write_bytes(b"hostile executable")
            helper = root / "helper.ps1"
            helper.write_text("exit 0\n", encoding="utf-8")
            marker = root / "hostile-ran"
            commands: list[list[str]] = []

            def capture(command: list[str], **kwargs: object) -> mock.Mock:
                commands.append(command)
                if Path(command[0]) == hostile:
                    marker.write_text("executed", encoding="utf-8")
                return mock.Mock()

            with (
                mock.patch(
                    "socratic_learn.self_manage.subprocess.Popen",
                    side_effect=capture,
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "PATH": str(root),
                        "SYSTEMROOT": os.environ["SYSTEMROOT"],
                    },
                ),
            ):
                _spawn_helper(helper)

            expected = (
                Path(os.environ["SYSTEMROOT"])
                / "System32"
                / "WindowsPowerShell"
                / "v1.0"
                / "powershell.exe"
            )
            self.assertEqual(expected, Path(commands[0][0]))
            self.assertNotEqual(hostile, Path(commands[0][0]))
            self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "nt", "Windows helper policy runs on Windows")
    def test_windows_helper_rejects_missing_trusted_powershell_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = root / "helper.ps1"
            helper.write_text("must remain", encoding="utf-8")
            popen = mock.Mock()

            with (
                mock.patch(
                    "socratic_learn.self_manage.subprocess.Popen",
                    popen,
                ),
                mock.patch.dict(
                    os.environ,
                    {
                        "PATH": str(root),
                        "SYSTEMROOT": str(root / "missing-windows"),
                    },
                ),
                self.assertRaisesRegex(UsageError, "trusted Windows PowerShell"),
            ):
                _spawn_helper(helper)

            popen.assert_not_called()
            self.assertEqual("must remain", helper.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "nt", "Windows helper policy runs on Windows")
    def test_windows_helper_rejects_reparse_point_in_trusted_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_root = root / "real-windows"
            powershell = (
                real_root
                / "System32"
                / "WindowsPowerShell"
                / "v1.0"
                / "powershell.exe"
            )
            powershell.parent.mkdir(parents=True)
            powershell.write_bytes(b"not executed")
            linked_root = root / "linked-windows"
            junction = subprocess.run(
                [
                    os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(linked_root),
                    str(real_root),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if junction.returncode != 0:
                self.skipTest("directory junctions are unavailable")
            helper = root / "helper.ps1"
            helper.write_text("must remain", encoding="utf-8")
            popen = mock.Mock()

            with (
                mock.patch(
                    "socratic_learn.self_manage.subprocess.Popen",
                    popen,
                ),
                mock.patch.dict(
                    os.environ,
                    {"SYSTEMROOT": str(linked_root)},
                ),
                self.assertRaisesRegex(UsageError, "without links"),
            ):
                _spawn_helper(helper)

            popen.assert_not_called()
            self.assertEqual("must remain", helper.read_text(encoding="utf-8"))

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

    @unittest.skipUnless(os.name == "nt", "Windows helper policy runs on Windows")
    def test_windows_update_rejects_missing_trusted_powershell_before_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)
            fetch_manifest = mock.Mock(return_value=fake_manifest(MANIFEST_URL))

            with (
                mock.patch.dict(
                    os.environ,
                    {"SYSTEMROOT": str(home / "missing-windows")},
                ),
                self.assertRaisesRegex(UsageError, "trusted Windows PowerShell"),
            ):
                update_installation(
                    home,
                    executable,
                    fetch_manifest=fetch_manifest,
                    fetch_artifact=fake_artifact,
                )

            fetch_manifest.assert_not_called()
            self.assertEqual(b"old", executable.read_bytes())
            self.assertEqual(
                {"socratic.exe"},
                {path.name for path in executable.parent.iterdir()},
            )

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
            self.assertIn("[System.IO.File]::Replace(", script)
            self.assertNotIn(
                "[System.IO.File]::Move($staged, $destination, $true)",
                script,
            )
            self.assertIn("Wait-Process", script)
            self.assertIn("$backup", script)
            self.assertIn("$replacementSucceeded", script)
            self.assertIn("$restorationSucceeded", script)

    @unittest.skipUnless(os.name == "nt", "Windows helper executes on Windows")
    def test_windows_helper_executes_under_windows_powershell_51(self) -> None:
        powershell = shutil.which("powershell.exe")
        if powershell is None:
            self.skipTest("Windows PowerShell is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "socratic.exe"
            staged = root / "socratic.new.exe"
            helper = root / "replace.ps1"
            destination.write_bytes(b"old")
            staged.write_bytes(b"new")
            script = _replacement_script(staged, destination)
            script = "\n".join(
                "# wait omitted by focused helper test"
                if line.startswith("Wait-Process -Id ")
                else line
                for line in script.splitlines()
            )
            helper.write_text(script, encoding="utf-8")

            reflection = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "$replace = [IO.File].GetMethods() | "
                    "? { $_.Name -eq 'Replace' -and $_.GetParameters().Count -eq 3 }; "
                    "$move = [IO.File].GetMethods() | "
                    "? { $_.Name -eq 'Move' -and $_.GetParameters().Count -eq 3 }; "
                    "if (-not $replace -or $move) { exit 91 }",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                0,
                reflection.returncode,
                reflection.stderr + reflection.stdout,
            )
            result = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertEqual(b"new", destination.read_bytes())
            self.assertFalse(staged.exists())
            self.assertEqual(
                {"socratic.exe"},
                {path.name for path in root.iterdir()},
            )

            destination.write_bytes(b"old-again")
            staged.write_bytes(b"new-again")
            helper.write_text(
                "\n".join(
                    "# wait omitted by focused helper test"
                    if line.startswith("Wait-Process -Id ")
                    else (
                        line + "\n    throw 'injected post-replacement failure'"
                        if line
                        == "    [System.IO.File]::Replace($staged, $destination, $backup)"
                        else line
                    )
                    for line in _replacement_script(staged, destination).splitlines()
                ),
                encoding="utf-8",
            )
            failed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(helper),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(0, failed.returncode)
            self.assertEqual(b"old-again", destination.read_bytes())
            self.assertEqual(
                {"socratic.exe"},
                {path.name for path in root.iterdir()},
            )


class UninstallTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows helper policy runs on Windows")
    def test_windows_uninstall_rejects_missing_trusted_powershell_without_mutation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            executable = Path(temporary) / "bin/socratic.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            write_native_channel(home, executable)
            popen = mock.Mock()

            with (
                mock.patch(
                    "socratic_learn.self_manage.subprocess.Popen",
                    popen,
                ),
                mock.patch.dict(
                    os.environ,
                    {"SYSTEMROOT": str(Path(temporary) / "missing-windows")},
                ),
                self.assertRaisesRegex(UsageError, "trusted Windows PowerShell"),
            ):
                uninstall(
                    home,
                    executable=executable,
                    delete_data=False,
                    confirm=lambda prompt: self.fail("must not prompt"),
                )

            popen.assert_not_called()
            self.assertEqual(b"old", executable.read_bytes())
            self.assertTrue((home / "channel.json").exists())

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
                uninstall(
                    home,
                    executable=executable,
                    delete_data=False,
                    confirm=lambda prompt: True,
                )

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
                        executable=executable,
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
                        executable=executable,
                        delete_data=True,
                        confirm=lambda prompt: answer,
                    )

                self.assertFalse(executable.exists())
                self.assertFalse(home.exists())

    def test_uninstall_rejects_unrelated_metadata_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            running = root / "running-socratic.exe"
            running.write_bytes(b"running")
            unrelated = root / "unrelated.exe"
            unrelated.write_bytes(b"unrelated")
            record = home / "workspace/progress.md"
            record.parent.mkdir()
            record.write_text("private", encoding="utf-8")
            write_native_channel(home, unrelated)
            confirm = mock.Mock(return_value="yes")

            with (
                mock.patch("socratic_learn.self_manage._remove_native") as remove,
                self.assertRaisesRegex(IntegrityError, "running program"),
            ):
                uninstall(
                    home,
                    executable=running,
                    delete_data=True,
                    confirm=confirm,
                )

            remove.assert_not_called()
            confirm.assert_not_called()
            self.assertEqual(b"running", running.read_bytes())
            self.assertEqual(b"unrelated", unrelated.read_bytes())
            self.assertEqual("private", record.read_text(encoding="utf-8"))
            self.assertTrue((home / "channel.json").exists())

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
