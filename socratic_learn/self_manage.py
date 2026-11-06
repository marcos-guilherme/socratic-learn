"""Installation-channel-aware update and uninstall operations."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
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


def load_install_channel(home: Path) -> InstallChannel | None:
    """Load strict native-channel metadata; absence denotes a pipx install."""

    metadata_path = home / "channel.json"
    if not metadata_path.exists() and not metadata_path.is_symlink():
        return None
    if home.is_symlink() or metadata_path.is_symlink():
        raise _channel_error("must not use symbolic links", metadata_path)
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
    if not executable.is_absolute() or executable.is_symlink():
        raise _channel_error(
            "executable must be an absolute non-symbolic path",
            metadata_path,
        )
    manifest_url = document["manifest_url"]
    if type(manifest_url) is not str or not manifest_url:
        raise _channel_error("manifest_url must be a non-empty string", metadata_path)
    return InstallChannel(1, "native", executable, manifest_url)


def _fetch_manifest(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


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


def _spawn_helper(helper: Path) -> None:
    subprocess.Popen(
        [
            "powershell.exe",
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
    return (
        "$ErrorActionPreference = 'Stop'\n"
        "function Decode-Path([string]$Value) {\n"
        "  [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Value))\n"
        "}\n"
        f"$staged = Decode-Path '{_encode_path(staged)}'\n"
        f"$destination = Decode-Path '{_encode_path(destination)}'\n"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        "try {\n"
        "  [System.IO.File]::Move($staged, $destination, $true)\n"
        "} finally {\n"
        "  Remove-Item -LiteralPath $staged -Force "
        "-ErrorAction SilentlyContinue\n"
        "  Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force "
        "-ErrorAction SilentlyContinue\n"
        "}\n"
    )


def _replace_native(staged: Path, executable: Path) -> None:
    if not _is_windows():
        staged.chmod(0o755)
        os.replace(staged, executable)
        return

    helper: Path | None = None
    try:
        helper = _write_helper(_replacement_script(staged, executable))
        _spawn_helper(helper)
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
    if executable.is_symlink() or not _same_path(executable, channel.executable):
        raise _channel_error(
            "executable does not match the running program",
            home / "channel.json",
        )

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
        if not _same_path(published, staged):
            raise IntegrityError(
                "verified artifact was published to an unexpected path",
                path=published,
            )
        _replace_native(staged, channel.executable)
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
            helper = _write_helper(
                _uninstall_script(
                    executable,
                    metadata,
                    home if delete_data else None,
                )
            )
            _spawn_helper(helper)
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
