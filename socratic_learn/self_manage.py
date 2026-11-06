"""Installation-channel-aware update and uninstall operations."""

from __future__ import annotations

import base64
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin
from urllib.request import urlopen

from .errors import IntegrityError, UsageError
from .release import (
    ReleaseArtifact,
    current_platform,
    download_verified,
    parse_release_manifest,
    select_artifact,
)
from .windows_security import trusted_windows_powershell


_CHANNEL_KEYS = {
    "schema_version",
    "channel",
    "executable",
    "manifest_url",
}
_DELETE_PROMPT = (
    "Delete all Socratic Learn learner profiles, progress, and sessions? [y/N]"
)


@dataclass(frozen=True, slots=True)
class InstallChannel:
    schema_version: int
    channel: str
    executable: Path
    manifest_url: str


def _channel_error(message: str, path: Path) -> IntegrityError:
    return IntegrityError(
        f"installation channel metadata {message}",
        path=path,
        remediation="reinstall Socratic Learn from a trusted release",
    )


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _strict_unlinked_path(
    path: Path,
    *,
    metadata_path: Path,
    label: str,
) -> Path:
    absolute = Path(os.path.abspath(path))
    for component in (*reversed(absolute.parents), absolute):
        try:
            status = os.lstat(component)
        except OSError as error:
            raise _channel_error(
                f"{label} path must exist and be inspectable",
                metadata_path,
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_flag:
            raise _channel_error(
                f"{label} path must not traverse a symbolic link or reparse point",
                metadata_path,
            )
    try:
        return absolute.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise _channel_error(
            f"{label} path could not be resolved safely",
            metadata_path,
        ) from error


def load_install_channel(home: Path) -> InstallChannel | None:
    """Load strict native-channel metadata; absence denotes a pipx install."""

    metadata_path = home / "channel.json"
    if not os.path.lexists(metadata_path):
        return None
    resolved_home = _strict_unlinked_path(
        home,
        metadata_path=metadata_path,
        label="launcher home",
    )
    resolved_metadata = _strict_unlinked_path(
        metadata_path,
        metadata_path=metadata_path,
        label="metadata",
    )
    try:
        metadata_is_in_home = os.path.samefile(
            resolved_metadata.parent,
            resolved_home,
        )
    except OSError as error:
        raise _channel_error(
            "location could not be verified safely",
            metadata_path,
        ) from error
    if not metadata_is_in_home:
        raise _channel_error("must remain inside launcher home", metadata_path)
    try:
        document = json.loads(
            metadata_path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise _channel_error("must be valid UTF-8 JSON", metadata_path) from error
    if not isinstance(document, Mapping):
        raise _channel_error("must be a JSON object", metadata_path)
    if set(document) != _CHANNEL_KEYS:
        raise _channel_error("must contain exactly the supported keys", metadata_path)
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise _channel_error("schema_version must be integer 1", metadata_path)
    if document["channel"] != "native":
        raise _channel_error("channel must be 'native'", metadata_path)
    executable_value = document["executable"]
    if type(executable_value) is not str or not executable_value:
        raise _channel_error("executable must be a non-empty string", metadata_path)
    executable = Path(executable_value)
    if not executable.is_absolute():
        raise _channel_error(
            "executable must be an absolute non-symbolic path",
            metadata_path,
        )
    _strict_unlinked_path(
        executable,
        metadata_path=metadata_path,
        label="executable",
    )
    manifest_url = document["manifest_url"]
    if type(manifest_url) is not str or not manifest_url:
        raise _channel_error("manifest_url must be a non-empty string", metadata_path)
    return InstallChannel(1, "native", executable, manifest_url)


def _fetch_manifest(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()


def _bind_executable(
    running: Path,
    installed: Path,
    metadata_path: Path,
) -> None:
    resolved_running = _strict_unlinked_path(
        running,
        metadata_path=metadata_path,
        label="running executable",
    )
    resolved_installed = _strict_unlinked_path(
        installed,
        metadata_path=metadata_path,
        label="installed executable",
    )
    try:
        matches = os.path.samefile(resolved_running, resolved_installed)
    except OSError as error:
        raise _channel_error(
            "executable identity could not be verified safely",
            metadata_path,
        ) from error
    if not matches:
        raise _channel_error(
            "executable does not match the running program",
            metadata_path,
        )


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(
            left.resolve(strict=True),
            right.resolve(strict=True),
        )
    except (OSError, RuntimeError):
        return False


def _encode_path(path: Path) -> str:
    return base64.b64encode(str(path).encode("utf-16le")).decode("ascii")


def _is_windows() -> bool:
    return os.name == "nt"


def _write_helper(script: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="socratic-", suffix=".ps1")
    helper = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(script)
    except BaseException:
        helper.unlink(missing_ok=True)
        raise
    return helper


def _spawn_helper(helper: Path, *, powershell: Path | None = None) -> None:
    if powershell is None:
        powershell = trusted_windows_powershell()
    subprocess.Popen(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(helper),
        ],
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        ),
        close_fds=True,
    )


def _replacement_script(staged: Path, destination: Path) -> str:
    backup = staged.with_name(f"{staged.name}.backup")
    failed = staged.with_name(f"{staged.name}.failed")
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "function Decode-Path([string]$Value) {\n"
        "  [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Value))\n"
        "}\n"
        f"$staged = Decode-Path '{_encode_path(staged)}'\n"
        f"$destination = Decode-Path '{_encode_path(destination)}'\n"
        f"$backup = Decode-Path '{_encode_path(backup)}'\n"
        f"$failed = Decode-Path '{_encode_path(failed)}'\n"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        "$replacementSucceeded = $false\n"
        "$restorationSucceeded = $false\n"
        "try {\n"
        "  if ([System.IO.File]::Exists($destination)) {\n"
        "    [System.IO.File]::Replace($staged, $destination, $backup)\n"
        "  } else {\n"
        "    [System.IO.File]::Move($staged, $destination)\n"
        "  }\n"
        "  $replacementSucceeded = $true\n"
        "} catch {\n"
        "  $replacementError = $_\n"
        "  if ([System.IO.File]::Exists($backup)) {\n"
        "    try {\n"
        "      if ([System.IO.File]::Exists($destination)) {\n"
        "        [System.IO.File]::Replace($backup, $destination, $failed)\n"
        "      } else {\n"
        "        [System.IO.File]::Move($backup, $destination)\n"
        "      }\n"
        "      $restorationSucceeded = $true\n"
        "    } catch {\n"
        "      throw \"native update failed and the old executable could not be "
        "restored; recovery copy: $backup\"\n"
        "    }\n"
        "  }\n"
        "  throw $replacementError\n"
        "} finally {\n"
        "  if ($replacementSucceeded -or $restorationSucceeded) {\n"
        "    Remove-Item -LiteralPath $staged -Force "
        "-ErrorAction SilentlyContinue\n"
        "    Remove-Item -LiteralPath $backup -Force "
        "-ErrorAction SilentlyContinue\n"
        "    Remove-Item -LiteralPath $failed -Force "
        "-ErrorAction SilentlyContinue\n"
        "  }\n"
        "  Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force "
        "-ErrorAction SilentlyContinue\n"
        "}\n"
    )


def _replace_native(
    staged: Path,
    executable: Path,
    *,
    powershell: Path | None = None,
) -> None:
    if not _is_windows():
        staged.chmod(0o755)
        os.replace(staged, executable)
        return

    helper: Path | None = None
    try:
        if powershell is None:
            powershell = trusted_windows_powershell()
        helper = _write_helper(_replacement_script(staged, executable))
        _spawn_helper(helper, powershell=powershell)
    except BaseException:
        staged.unlink(missing_ok=True)
        if helper is not None:
            helper.unlink(missing_ok=True)
        raise


def update_installation(
    home: Path,
    executable: Path,
    *,
    fetch_manifest: Callable[[str], bytes] = _fetch_manifest,
    fetch_artifact: Callable[[ReleaseArtifact, Path], Path] = download_verified,
    output: Callable[[str], object] = print,
) -> int:
    """Update a native install, or report the pipx command without mutation."""

    channel = load_install_channel(home)
    if channel is None:
        output("Run: pipx upgrade socratic-learn")
        return 0
    _bind_executable(executable, channel.executable, home / "channel.json")
    powershell = trusted_windows_powershell() if _is_windows() else None

    manifest = fetch_manifest(channel.manifest_url)
    artifacts = parse_release_manifest(
        manifest,
        urljoin(channel.manifest_url, "."),
    )
    artifact = select_artifact(artifacts, *current_platform())
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{channel.executable.name}.",
        suffix=".update",
        dir=channel.executable.parent,
    )
    os.close(descriptor)
    staged = Path(staged_name)
    staged.unlink()
    try:
        published = fetch_artifact(artifact, staged)
        if not _same_existing_file(published, staged):
            raise IntegrityError(
                "verified artifact was published to an unexpected path",
                path=published,
            )
        _replace_native(
            staged,
            channel.executable,
            powershell=powershell,
        )
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    return 0


def _uninstall_script(
    executable: Path,
    metadata: Path,
    home: Path | None,
) -> str:
    lines = [
        "$ErrorActionPreference = 'Stop'",
        "function Decode-Path([string]$Value) {",
        "  [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Value))",
        "}",
        f"$executable = Decode-Path '{_encode_path(executable)}'",
        f"$metadata = Decode-Path '{_encode_path(metadata)}'",
    ]
    if home is not None:
        lines.append(f"$home = Decode-Path '{_encode_path(home)}'")
    lines.extend(
        [
            f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue",
            "try {",
            "  Remove-Item -LiteralPath $executable -Force",
            "  Remove-Item -LiteralPath $metadata -Force",
        ]
    )
    if home is not None:
        lines.append("  Remove-Item -LiteralPath $home -Recurse -Force")
    lines.extend(
        [
            "} finally {",
            "  Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force "
            "-ErrorAction SilentlyContinue",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def _remove_native(
    home: Path,
    executable: Path,
    *,
    delete_data: bool,
) -> None:
    metadata = home / "channel.json"
    if _is_windows():
        helper: Path | None = None
        try:
            powershell = trusted_windows_powershell()
            helper = _write_helper(
                _uninstall_script(
                    executable,
                    metadata,
                    home if delete_data else None,
                )
            )
            _spawn_helper(helper, powershell=powershell)
        except BaseException:
            if helper is not None:
                helper.unlink(missing_ok=True)
            raise
        return

    executable.unlink()
    metadata.unlink()
    if delete_data:
        shutil.rmtree(home)


def uninstall(
    home: Path,
    *,
    executable: Path | None = None,
    delete_data: bool,
    confirm: Callable[[str], object],
    yes: bool = False,
    output: Callable[[str], object] = print,
) -> int:
    """Remove the managed native install while preserving data by default."""

    if yes and not delete_data:
        raise UsageError("--yes requires --delete-data")
    channel = load_install_channel(home)
    if channel is None:
        output("Run: pipx uninstall socratic-learn")
        return 0
    running_executable = Path(sys.executable) if executable is None else executable
    _bind_executable(
        running_executable,
        channel.executable,
        home / "channel.json",
    )
    if delete_data and not yes:
        answer = confirm(_DELETE_PROMPT)
        if type(answer) is not str or answer.strip().lower() not in {"y", "yes"}:
            return 0
    _remove_native(
        home,
        channel.executable,
        delete_data=delete_data,
    )
    return 0
