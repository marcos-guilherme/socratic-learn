from __future__ import annotations

import contextlib
import hashlib
import http.server
import json
import os
import platform
import shutil
import socketserver
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_INSTALLER = ROOT / "scripts" / "install.ps1"
POSIX_INSTALLER = ROOT / "scripts" / "install.sh"
MANIFEST_URL = (
    "https://github.com/marcos-guilherme/socratic-learn/"
    "releases/latest/download/release-manifest.json"
)
RELEASE_BASE_URL = (
    "https://github.com/marcos-guilherme/socratic-learn/releases/latest/download"
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextlib.contextmanager
def fixture_server(directory: Path):
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(directory), **kwargs
    )
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            thread.join()


class BootstrapInstallerTests(unittest.TestCase):
    payload = b"fixture executable bytes\n"

    def test_installers_pin_canonical_release_locations(self) -> None:
        powershell = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        shell = POSIX_INSTALLER.read_text(encoding="utf-8")

        self.assertIn(MANIFEST_URL, powershell)
        self.assertIn(RELEASE_BASE_URL, shell)
        self.assertIn("SHA256SUMS", shell)

    def test_installers_verify_hash_before_atomic_publication(self) -> None:
        powershell = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        shell = POSIX_INSTALLER.read_text(encoding="utf-8")

        self.assertLess(powershell.index("Get-FileHash"), powershell.index("File]::Move"))
        self.assertLess(shell.index("sha256sum"), shell.index('mv "$staged" "$target"'))
        self.assertIn("Get-Item", powershell)
        self.assertIn("chmod 755", shell)

    def test_installers_are_user_local_and_do_not_elevate(self) -> None:
        combined = (
            POWERSHELL_INSTALLER.read_text(encoding="utf-8")
            + POSIX_INSTALLER.read_text(encoding="utf-8")
        ).lower()

        for forbidden in ("sudo", "runas", "/usr/local", "program files"):
            self.assertNotIn(forbidden, combined)

    def test_posix_checksum_selection_is_an_exact_unique_filename_match(self) -> None:
        shell = POSIX_INSTALLER.read_text(encoding="utf-8")

        self.assertIn(
            """awk -v name="$asset" '$2 == name {print $1}'""",
            shell,
        )
        self.assertIn("match_count", shell)

    def _write_windows_release(self, root: Path, digest: str) -> None:
        filename = "socratic-windows-x86_64.exe"
        (root / filename).write_bytes(self.payload)
        manifest = {
            "schema_version": 1,
            "version": "0.1.0",
            "artifacts": [
                {
                    "platform": "windows",
                    "architecture": "x86_64",
                    "filename": filename,
                    "size": len(self.payload),
                    "sha256": digest,
                }
            ],
        }
        (root / "release-manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    def _run_powershell(
        self, root: Path, manifest_url: str, install_dir: Path, home: Path
    ) -> subprocess.CompletedProcess[str]:
        executable = shutil.which("powershell.exe") or shutil.which("pwsh")
        if executable is None:
            self.skipTest("PowerShell is unavailable")
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(root / "local-app-data"),
            "PATH": str(root / "isolated-path"),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "PROCESSOR_ARCHITECTURE": os.environ.get(
                "PROCESSOR_ARCHITECTURE", "AMD64"
            ),
        }
        return subprocess.run(
            [
                executable,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(POWERSHELL_INSTALLER),
                "-ManifestUrl",
                manifest_url,
                "-InstallDirectory",
                str(install_dir),
                "-Yes",
            ],
            capture_output=True,
            text=True,
            env=environment,
            timeout=30,
            check=False,
        )

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_installer_isolated_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            install_dir = root / "install"
            digest = hashlib.sha256(self.payload).hexdigest()
            self._write_windows_release(root, digest)

            with fixture_server(root) as base_url:
                result = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    install_dir,
                    home,
                )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            executable = install_dir / "socratic.exe"
            self.assertEqual(self.payload, executable.read_bytes())
            channel = json.loads(
                (home / ".socratic-learn" / "channel.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                {
                    "schema_version": 1,
                    "channel": "native",
                    "executable": str(executable.resolve()),
                    "manifest_url": f"{base_url}/release-manifest.json",
                },
                channel,
            )

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_installer_preserves_existing_file_on_bad_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            install_dir = root / "install"
            install_dir.mkdir()
            target = install_dir / "socratic.exe"
            target.write_bytes(b"existing")
            self._write_windows_release(root, "0" * 64)

            with fixture_server(root) as base_url:
                result = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    install_dir,
                    home,
                )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"existing", target.read_bytes())
            self.assertFalse((install_dir / "socratic.new.exe").exists())
            self.assertFalse((home / ".socratic-learn" / "channel.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_installer_rejects_duplicate_and_unknown_manifest_keys(self) -> None:
        filename = "socratic-windows-x86_64.exe"
        digest = hashlib.sha256(self.payload).hexdigest()
        artifact = (
            '{"platform":"windows","architecture":"x86_64",'
            f'"filename":"{filename}","size":{len(self.payload)},'
            f'"sha256":"{digest}"'
        )
        cases = (
            (
                '{"schema_version":1,"schema_version":1,"version":"0.1.0",'
                f'"artifacts":[{artifact}}}]}}',
                "duplicate",
            ),
            (
                '{"schema_version":1,"version":"0.1.0","unknown":true,'
                f'"artifacts":[{artifact}}}]}}',
                "unknown",
            ),
            (
                '{"schema_version":1,"version":"0.1.0",'
                f'"artifacts":[{artifact},"unknown":true}}]}}',
                "unknown",
            ),
            (
                '{"schema_version":1,"version":"0.1.0","artifacts":'
                + artifact
                + "}}",
                "array",
            ),
        )
        for index, (manifest, expected_error) in enumerate(cases):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                home.mkdir()
                install_dir = root / "install"
                (root / filename).write_bytes(self.payload)
                (root / "release-manifest.json").write_text(
                    manifest, encoding="utf-8"
                )
                with fixture_server(root) as base_url:
                    result = self._run_powershell(
                        root,
                        f"{base_url}/release-manifest.json",
                        install_dir,
                        home,
                    )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    expected_error,
                    (result.stderr + result.stdout).lower(),
                )
                self.assertFalse((install_dir / "socratic.exe").exists())

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_installer_isolated_success(self) -> None:
        if shutil.which("sh") is None or shutil.which("curl") is None:
            self.skipTest("sh and curl are required for the POSIX installer test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            install_dir = root / 'install "quoted" \\ path'
            system = {"Linux": "linux", "Darwin": "macos"}.get(platform.system())
            if system is None or platform.machine().lower() not in ("x86_64", "amd64"):
                self.skipTest("POSIX execution test requires an x86-64 Linux or macOS host")
            asset = f"socratic-{system}-x86_64"
            (root / asset).write_bytes(self.payload)
            digest = hashlib.sha256(self.payload).hexdigest()
            (root / "SHA256SUMS").write_text(
                f"{digest}  {asset}\n", encoding="ascii"
            )
            isolated_path = root / "path"
            isolated_path.mkdir()
            for command in (
                "uname",
                "curl",
                "mkdir",
                "rm",
                "awk",
                "cat",
                "chmod",
                "mv",
                "sha256sum",
                "shasum",
            ):
                source = shutil.which(command)
                if source is not None:
                    (isolated_path / command).symlink_to(source)
            shell = shutil.which("sh")
            assert shell is not None

            with fixture_server(root) as base_url:
                environment = os.environ.copy()
                environment.update(
                    {
                        "HOME": str(home),
                        "PATH": str(isolated_path),
                        "SOCRATIC_INSTALL_YES": "1",
                        "SOCRATIC_RELEASE_BASE_URL": base_url,
                        "SOCRATIC_INSTALL_DIR": str(install_dir),
                    }
                )
                result = subprocess.run(
                    [shell, str(POSIX_INSTALLER)],
                    capture_output=True,
                    text=True,
                    env=environment,
                    timeout=30,
                    check=False,
                )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            executable = install_dir / "socratic"
            self.assertEqual(self.payload, executable.read_bytes())
            channel = json.loads(
                (home / ".socratic-learn" / "channel.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("native", channel["channel"])
            self.assertEqual(str(executable.resolve()), channel["executable"])
            self.assertEqual(MANIFEST_URL, channel["manifest_url"])

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_installer_preserves_existing_file_on_bad_hash(self) -> None:
        required = ("sh", "curl", "uname", "awk", "sha256sum")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("POSIX installer test dependencies are unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            install_dir = root / "install"
            install_dir.mkdir()
            target = install_dir / "socratic"
            target.write_bytes(b"existing")
            system = {"Linux": "linux", "Darwin": "macos"}.get(platform.system())
            if system is None or platform.machine().lower() not in ("x86_64", "amd64"):
                self.skipTest("POSIX execution test requires an x86-64 Linux or macOS host")
            asset = f"socratic-{system}-x86_64"
            (root / asset).write_bytes(self.payload)
            (root / "SHA256SUMS").write_text(
                f"{'0' * 64}  {asset}\n", encoding="ascii"
            )

            with fixture_server(root) as base_url:
                environment = os.environ.copy()
                environment.update(
                    {
                        "HOME": str(home),
                        "SOCRATIC_INSTALL_YES": "1",
                        "SOCRATIC_RELEASE_BASE_URL": base_url,
                        "SOCRATIC_INSTALL_DIR": str(install_dir),
                    }
                )
                result = subprocess.run(
                    [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                    capture_output=True,
                    text=True,
                    env=environment,
                    timeout=30,
                    check=False,
                )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"existing", target.read_bytes())
            self.assertFalse((install_dir / "socratic.new").exists())
            self.assertFalse((home / ".socratic-learn" / "channel.json").exists())


if __name__ == "__main__":
    unittest.main()
