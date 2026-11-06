from __future__ import annotations

import contextlib
import hashlib
import http.server
import json
import os
import platform
import shlex
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
def fixture_server(
    directory: Path,
    *,
    redirects: dict[str, str] | None = None,
    requests: list[str] | None = None,
):
    redirect_map = redirects or {}
    request_log = requests if requests is not None else []

    class FixtureHandler(QuietHandler):
        def do_GET(self) -> None:
            request_log.append(self.path)
            destination = redirect_map.get(self.path)
            if destination is not None:
                self.send_response(302)
                self.send_header("Location", destination)
                self.end_headers()
                return
            super().do_GET()

    handler = lambda *args, **kwargs: FixtureHandler(  # noqa: E731
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

    def test_channel_is_published_before_executable(self) -> None:
        powershell = POWERSHELL_INSTALLER.read_text(encoding="utf-8")
        shell = POSIX_INSTALLER.read_text(encoding="utf-8")

        self.assertLess(
            powershell.index("File]::Move($channelStaged"),
            powershell.index("File]::Move($staged"),
        )
        self.assertLess(
            shell.index('mv "$channel_staged" "$channel_target"'),
            shell.index('mv "$staged" "$target"'),
        )

    def test_posix_channel_backup_is_random_private_and_exclusive(self) -> None:
        shell = POSIX_INSTALLER.read_text(encoding="utf-8")

        self.assertIn('mktemp -d "$channel_home/.channel-backup.XXXXXX"', shell)
        self.assertIn('chmod 700 "$channel_backup_dir"', shell)
        self.assertNotIn('channel.json.previous', shell)

    def test_installers_are_user_local_and_do_not_elevate(self) -> None:
        combined = (
            POWERSHELL_INSTALLER.read_text(encoding="utf-8")
            + POSIX_INSTALLER.read_text(encoding="utf-8")
        ).lower()

        for forbidden in (
            "sudo",
            "runas",
            "/usr/local",
            "program files",
            "python",
            "jq ",
            "node ",
        ):
            self.assertNotIn(forbidden, combined)
        self.assertIn("--proto-redir '=https'", combined)
        self.assertIn("--proto-redir '=http'", combined)

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

    def _isolated_posix_path(
        self,
        root: Path,
        overrides: dict[str, str] | None = None,
    ) -> Path:
        isolated_path = root / "path"
        isolated_path.mkdir()
        replacements = overrides or {}
        for command in (
            "uname",
            "curl",
            "mkdir",
            "rm",
            "awk",
            "cat",
            "chmod",
            "mv",
            "mktemp",
            "sha256sum",
            "shasum",
            "touch",
        ):
            destination = isolated_path / command
            if command in replacements:
                destination.write_text(replacements[command], encoding="utf-8")
                destination.chmod(0o755)
                continue
            source = shutil.which(command)
            if source is not None:
                destination.symlink_to(source)
        return isolated_path

    def _run_powershell(
        self,
        root: Path,
        manifest_url: str,
        install_dir: Path,
        home: Path,
        *,
        consent: bool = True,
        input_text: str | None = None,
        extra_environment: dict[str, str] | None = None,
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
        environment.update(extra_environment or {})
        arguments = [
            executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(POWERSHELL_INSTALLER),
            "-ManifestUrl",
            manifest_url,
            "-InstallDirectory",
            str(install_dir),
        ]
        if consent:
            arguments.append("-Yes")
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            input=input_text,
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
                reinstall = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    install_dir,
                    home,
                )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertEqual(
                0,
                reinstall.returncode,
                reinstall.stderr + reinstall.stdout,
            )
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
                    "manifest_url": MANIFEST_URL,
                },
                channel,
            )
            self.assertFalse((install_dir / "socratic.previous.exe").exists())
            self.assertFalse((install_dir / "socratic.failed.exe").exists())

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_artifact_url_uses_original_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            install_dir = root / "install"
            self._write_windows_release(
                root,
                hashlib.sha256(self.payload).hexdigest(),
            )
            redirected = root / "redirected"
            redirected.mkdir()
            shutil.copy2(
                root / "release-manifest.json",
                redirected / "manifest-asset",
            )
            requests: list[str] = []
            redirects = {
                "/release-manifest.json": "/redirected/manifest-asset",
            }
            with fixture_server(
                root,
                redirects=redirects,
                requests=requests,
            ) as base_url:
                result = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    install_dir,
                    home,
                )

            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
            self.assertEqual(self.payload, (install_dir / "socratic.exe").read_bytes())
            self.assertEqual(
                [
                    "/release-manifest.json",
                    "/redirected/manifest-asset",
                    "/socratic-windows-x86_64.exe",
                ],
                requests,
            )

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_requires_consent_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            requests: list[str] = []
            with fixture_server(root, requests=requests) as base_url:
                result = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    root / "install",
                    home,
                    consent=False,
                    input_text="n\n",
                )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual([], requests)
            self.assertIn("SmartScreen", result.stderr + result.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_rejects_hostile_manifest_urls_before_network(self) -> None:
        hostile_urls = (
            "http://localhost:123@evil.example/release-manifest.json",
            "http://localhost.evil/release-manifest.json",
            "http://LOCALHOST/release-manifest.json",
            "http://2130706433/release-manifest.json",
            "http://127.1/release-manifest.json",
            "http://localhost:99999/release-manifest.json",
            "http://localhost:80:90/release-manifest.json",
            "http://[0:0:0:0:0:0:0:1]/release-manifest.json",
            "http://[::1/release-manifest.json",
            "http://example.com/release-manifest.json",
            "file:///C:/release-manifest.json",
            "https://example.com/release-manifest.json",
            "http://localhost/release-manifest.json#fragment",
            MANIFEST_URL + "#fragment",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            for manifest_url in hostile_urls:
                with self.subTest(manifest_url=manifest_url):
                    result = self._run_powershell(
                        root,
                        manifest_url,
                        root / "install",
                        home,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn(
                        "trusted",
                        (result.stderr + result.stdout).lower(),
                    )

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_rejects_redirect_away_from_loopback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            evil_requests: list[str] = []
            with fixture_server(root, requests=evil_requests) as evil_base:
                hostile_redirect = evil_base.replace("http://", "http://localhost@")
                redirects = {"/release-manifest.json": f"{hostile_redirect}/stolen"}
                with fixture_server(root, redirects=redirects) as trusted_base:
                    result = self._run_powershell(
                        root,
                        f"{trusted_base}/release-manifest.json",
                        root / "install",
                        home,
                    )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual([], evil_requests)

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_channel_failure_preserves_existing_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            channel_target = home / ".socratic-learn" / "channel.json"
            channel_target.mkdir(parents=True)
            install_dir = root / "install"
            install_dir.mkdir()
            target = install_dir / "socratic.exe"
            target.write_bytes(b"existing")
            self._write_windows_release(
                root,
                hashlib.sha256(self.payload).hexdigest(),
            )
            with fixture_server(root) as base_url:
                result = self._run_powershell(
                    root,
                    f"{base_url}/release-manifest.json",
                    install_dir,
                    home,
                )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(b"existing", target.read_bytes())

    @unittest.skipUnless(os.name == "nt", "Windows installer executes only on Windows")
    def test_windows_executable_failure_rolls_back_channel_and_executable(self) -> None:
        for reinstall in (False, True):
            with self.subTest(reinstall=reinstall), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                home.mkdir()
                install_dir = root / "install"
                install_dir.mkdir()
                target = install_dir / "socratic.exe"
                channel = home / ".socratic-learn" / "channel.json"
                previous_channel = b'\xef\xbb\xbf{"previous":"exact bytes"}\r\n'
                if reinstall:
                    target.write_bytes(b"existing")
                    channel.parent.mkdir()
                    channel.write_bytes(previous_channel)
                self._write_windows_release(
                    root,
                    hashlib.sha256(self.payload).hexdigest(),
                )

                with fixture_server(root) as base_url:
                    result = self._run_powershell(
                        root,
                        f"{base_url}/release-manifest.json",
                        install_dir,
                        home,
                        extra_environment={
                            "SOCRATIC_TEST_FAIL_EXECUTABLE_PUBLICATION": "1",
                        },
                    )

                self.assertNotEqual(0, result.returncode)
                self.assertIn(
                    "Injected executable publication failure",
                    result.stderr + result.stdout,
                )
                if reinstall:
                    self.assertEqual(b"existing", target.read_bytes())
                    self.assertEqual(previous_channel, channel.read_bytes())
                else:
                    self.assertFalse(target.exists())
                    self.assertFalse(channel.exists())
                self.assertFalse((install_dir / "socratic.new.exe").exists())
                self.assertFalse(
                    (home / ".socratic-learn" / "channel.json.new").exists()
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
            install_dir = root / (
                "bin spaces ' \" `touch BACKTICKED` $HOME "
                "$(touch PWNED) \\ end"
            )
            system = {"Linux": "linux", "Darwin": "macos"}.get(platform.system())
            if system is None or platform.machine().lower() not in ("x86_64", "amd64"):
                self.skipTest("POSIX execution test requires an x86-64 Linux or macOS host")
            asset = f"socratic-{system}-x86_64"
            (root / asset).write_bytes(self.payload)
            digest = hashlib.sha256(self.payload).hexdigest()
            (root / "SHA256SUMS").write_text(
                f"{digest}  {asset}\n", encoding="ascii"
            )
            isolated_path = self._isolated_posix_path(root)
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
            profile_line = next(
                line
                for line in result.stdout.splitlines()
                if line.startswith("export PATH=")
            )
            round_trip = subprocess.run(
                [
                    shell,
                    "-c",
                    profile_line + '\nprintf "%s" "$PATH"',
                ],
                cwd=root,
                capture_output=True,
                text=True,
                env={"PATH": str(isolated_path)},
                check=False,
            )
            self.assertEqual(0, round_trip.returncode, round_trip.stderr)
            self.assertEqual(
                f"{install_dir.resolve()}:{isolated_path}",
                round_trip.stdout,
            )
            self.assertFalse((root / "PWNED").exists())
            self.assertFalse((root / "BACKTICKED").exists())

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_requires_consent_before_network(self) -> None:
        if shutil.which("sh") is None:
            self.skipTest("sh is required for the POSIX installer test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            requests: list[str] = []
            with fixture_server(root, requests=requests) as base_url:
                environment = os.environ.copy()
                environment.update(
                    {
                        "HOME": str(home),
                        "SOCRATIC_RELEASE_BASE_URL": base_url,
                        "SOCRATIC_INSTALL_DIR": str(root / "install"),
                    }
                )
                result = subprocess.run(
                    [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                    input="n\n",
                    capture_output=True,
                    text=True,
                    env=environment,
                    check=False,
                )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual([], requests)
            self.assertIn("Gatekeeper", result.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_rejects_hostile_release_urls_before_network(self) -> None:
        if shutil.which("sh") is None:
            self.skipTest("sh is required for the POSIX installer test")
        hostile_urls = (
            "http://localhost:123@evil.example/releases",
            "http://localhost.evil/releases",
            "http://LOCALHOST/releases",
            "http://2130706433/releases",
            "http://127.1/releases",
            "http://localhost:99999/releases",
            "http://localhost:80:90/releases",
            "http://[0:0:0:0:0:0:0:1]/releases",
            "http://[::1/releases",
            "http://example.com/releases",
            "file:///tmp/releases",
            "https://example.com/releases",
            "http://localhost/releases#fragment",
            RELEASE_BASE_URL + "#fragment",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            for release_url in hostile_urls:
                with self.subTest(release_url=release_url):
                    environment = os.environ.copy()
                    environment.update(
                        {
                            "HOME": str(home),
                            "SOCRATIC_INSTALL_YES": "1",
                            "SOCRATIC_RELEASE_BASE_URL": release_url,
                            "SOCRATIC_INSTALL_DIR": str(root / "install"),
                        }
                    )
                    result = subprocess.run(
                        [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                        capture_output=True,
                        text=True,
                        env=environment,
                        check=False,
                    )
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("trusted", result.stderr.lower())

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_rejects_redirect_away_from_loopback(self) -> None:
        if shutil.which("sh") is None or shutil.which("curl") is None:
            self.skipTest("sh and curl are required for the POSIX installer test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            evil_requests: list[str] = []
            with fixture_server(root, requests=evil_requests) as evil_base:
                hostile_redirect = evil_base.replace("http://", "http://localhost@")
                redirects = {"/SHA256SUMS": f"{hostile_redirect}/stolen"}
                with fixture_server(root, redirects=redirects) as trusted_base:
                    environment = os.environ.copy()
                    environment.update(
                        {
                            "HOME": str(home),
                            "SOCRATIC_INSTALL_YES": "1",
                            "SOCRATIC_RELEASE_BASE_URL": trusted_base,
                            "SOCRATIC_INSTALL_DIR": str(root / "install"),
                        }
                    )
                    result = subprocess.run(
                        [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                        capture_output=True,
                        text=True,
                        env=environment,
                        check=False,
                    )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual([], evil_requests)

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_rejects_https_redirect_downgrade_before_second_request(self) -> None:
        if shutil.which("sh") is None:
            self.skipTest("sh is required for the POSIX installer test")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            calls = root / "curl-calls"
            fake_curl = f"""#!/bin/sh
headers=
body=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --dump-header) headers=$2; shift 2 ;;
        --output) body=$2; shift 2 ;;
        *) shift ;;
    esac
done
printf 'call\\n' >> {shlex.quote(str(calls))}
printf 'HTTP/1.1 302 Found\\r\\nLocation: http://127.0.0.1/evil\\r\\n\\r\\n' > "$headers"
: > "$body"
printf '302'
"""
            isolated_path = self._isolated_posix_path(
                root,
                overrides={"curl": fake_curl},
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "HOME": str(home),
                    "PATH": str(isolated_path),
                    "SOCRATIC_INSTALL_YES": "1",
                    "SOCRATIC_INSTALL_DIR": str(root / "install"),
                }
            )
            result = subprocess.run(
                [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(["call"], calls.read_text(encoding="utf-8").splitlines())
            self.assertIn("trusted HTTPS", result.stderr)

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

    @unittest.skipIf(os.name == "nt", "POSIX installer executes only on POSIX")
    def test_posix_executable_failure_rolls_back_channel_and_executable(self) -> None:
        required = ("sh", "curl", "uname", "awk", "sha256sum", "mv")
        if any(shutil.which(command) is None for command in required):
            self.skipTest("POSIX installer test dependencies are unavailable")
        for reinstall in (False, True):
            with self.subTest(reinstall=reinstall), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                home.mkdir()
                install_dir = root / "install"
                install_dir.mkdir()
                target = install_dir / "socratic"
                channel = home / ".socratic-learn" / "channel.json"
                previous_channel = b'{"previous":"exact bytes"}\n'
                channel.parent.mkdir()
                sentinel = root / "external-sentinel"
                sentinel_bytes = b"must remain unchanged\n"
                sentinel.write_bytes(sentinel_bytes)
                predictable_backup = channel.parent / "channel.json.previous"
                predictable_backup.symlink_to(sentinel)
                if reinstall:
                    target.write_bytes(b"existing")
                    channel.write_bytes(previous_channel)
                system = {"Linux": "linux", "Darwin": "macos"}.get(platform.system())
                if system is None or platform.machine().lower() not in (
                    "x86_64",
                    "amd64",
                ):
                    self.skipTest(
                        "POSIX execution test requires an x86-64 Linux or macOS host"
                    )
                asset = f"socratic-{system}-x86_64"
                (root / asset).write_bytes(self.payload)
                digest = hashlib.sha256(self.payload).hexdigest()
                (root / "SHA256SUMS").write_text(
                    f"{digest}  {asset}\n", encoding="ascii"
                )
                real_mv = shutil.which("mv")
                assert real_mv is not None
                fake_mv = (
                    "#!/bin/sh\n"
                    'case "$2" in */socratic) exit 73 ;; esac\n'
                    f"exec {shlex.quote(real_mv)} \"$@\"\n"
                )
                isolated_path = self._isolated_posix_path(
                    root,
                    overrides={"mv": fake_mv},
                )
                environment = os.environ.copy()
                environment.update(
                    {
                        "HOME": str(home),
                        "PATH": str(isolated_path),
                        "SOCRATIC_INSTALL_YES": "1",
                        "SOCRATIC_INSTALL_DIR": str(install_dir),
                    }
                )

                with fixture_server(root) as base_url:
                    environment["SOCRATIC_RELEASE_BASE_URL"] = base_url
                    result = subprocess.run(
                        [shutil.which("sh") or "sh", str(POSIX_INSTALLER)],
                        capture_output=True,
                        text=True,
                        env=environment,
                        check=False,
                    )

                self.assertEqual(73, result.returncode, result.stderr + result.stdout)
                if reinstall:
                    self.assertEqual(b"existing", target.read_bytes())
                    self.assertEqual(previous_channel, channel.read_bytes())
                else:
                    self.assertFalse(target.exists())
                    self.assertFalse(channel.exists())
                self.assertEqual(sentinel_bytes, sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
