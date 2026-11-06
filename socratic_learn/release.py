"""Strict release metadata parsing and verified artifact publication."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Callable
from urllib.parse import urljoin
from urllib.request import urlopen

from .errors import IntegrityError, UsageError


_TOP_LEVEL_KEYS = {"schema_version", "version", "artifacts"}
_ARTIFACT_KEYS = {
    "platform",
    "architecture",
    "filename",
    "size",
    "sha256",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_PLATFORMS = {"win32": "windows", "linux": "linux", "darwin": "macos"}
_ARCHITECTURES = {"amd64": "x86_64", "x86_64": "x86_64", "x64": "x86_64"}
_FORBIDDEN_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
_RESERVED_WINDOWS_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_INSTALL_REMEDIATION = "pipx install socratic-learn"
_MANIFEST_REMEDIATION = "download a valid release manifest"


@dataclass(frozen=True, slots=True)
class ReleaseArtifact:
    """One downloadable artifact described by a trusted release manifest."""

    version: str
    platform: str
    architecture: str
    filename: str
    size: int
    sha256: str
    url: str


def _invalid(field: str, message: str) -> IntegrityError:
    return IntegrityError(
        f"release manifest {field} {message}",
        path=f"release_manifest.{field}",
        remediation=_MANIFEST_REMEDIATION,
    )


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    if unknown:
        name = f"{field}.{unknown[0]}" if field else unknown[0]
        raise _invalid(name, "is an unknown property")
    missing = sorted(expected - actual)
    if missing:
        name = f"{field}.{missing[0]}" if field else missing[0]
        raise _invalid(name, "is required")


def _has_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def _require_string(value: object, field: str) -> str:
    if type(value) is not str or not value or _has_control_character(value):
        raise _invalid(field, "must be a non-empty control-free string")
    return value


def _require_leaf_filename(value: object, field: str) -> str:
    filename = _require_string(value, field)
    basename = filename.split(".", 1)[0].upper()
    if (
        filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or any(
            character in _FORBIDDEN_FILENAME_CHARACTERS
            for character in filename
        )
        or filename.endswith((" ", "."))
        or basename in _RESERVED_WINDOWS_BASENAMES
        or PurePosixPath(filename).name != filename
        or PureWindowsPath(filename).name != filename
    ):
        raise _invalid(field, "must be a portable leaf name")
    return filename


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _invalid(key, "is duplicated")
        value[key] = item
    return value


def parse_release_manifest(
    data: bytes,
    base_url: str,
) -> tuple[ReleaseArtifact, ...]:
    """Parse a release manifest without accepting schema or type drift."""

    if type(data) is not bytes:
        raise _invalid("$", "must be UTF-8 encoded bytes")
    if type(base_url) is not str:
        raise _invalid("base_url", "must be a string")
    try:
        document = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except IntegrityError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid("$", "must be valid UTF-8 JSON") from error
    if not isinstance(document, Mapping):
        raise _invalid("$", "must be a JSON object")
    _require_exact_keys(document, _TOP_LEVEL_KEYS, "")

    schema_version = document["schema_version"]
    if type(schema_version) is not int or schema_version != 1:
        raise _invalid("schema_version", "must be integer 1")
    version = document["version"]
    if type(version) is not str or _SEMVER_RE.fullmatch(version) is None:
        raise _invalid("version", "must be a strict semantic version")
    artifacts = document["artifacts"]
    if type(artifacts) is not list or not artifacts:
        raise _invalid("artifacts", "must be a non-empty array")

    parsed: list[ReleaseArtifact] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(artifacts):
        field = f"artifacts[{index}]"
        if not isinstance(item, Mapping):
            raise _invalid(field, "must be a JSON object")
        _require_exact_keys(item, _ARTIFACT_KEYS, field)
        artifact_platform = _require_string(item["platform"], f"{field}.platform")
        architecture = _require_string(
            item["architecture"],
            f"{field}.architecture",
        )
        filename = _require_leaf_filename(item["filename"], f"{field}.filename")
        size = item["size"]
        if type(size) is not int or size <= 0:
            raise _invalid(f"{field}.size", "must be a positive integer")
        digest = item["sha256"]
        if type(digest) is not str or _SHA256_RE.fullmatch(digest) is None:
            raise _invalid(
                f"{field}.sha256",
                "must be a lowercase SHA-256 hash",
            )
        pair = (artifact_platform, architecture)
        if pair in seen_pairs:
            raise _invalid(
                field,
                "has a duplicate platform/architecture pair",
            )
        seen_pairs.add(pair)
        parsed.append(
            ReleaseArtifact(
                version=version,
                platform=artifact_platform,
                architecture=architecture,
                filename=filename,
                size=size,
                sha256=digest,
                url=urljoin(base_url, filename),
            )
        )
    return tuple(parsed)


def current_platform() -> tuple[str, str]:
    """Return normalized platform and architecture identifiers."""

    system = _PLATFORMS.get(sys.platform)
    if system is None:
        raise UsageError(
            f"unsupported platform: {sys.platform}",
            remediation=_INSTALL_REMEDIATION,
        )
    machine = platform.machine()
    architecture = _ARCHITECTURES.get(machine.lower())
    if architecture is None:
        raise UsageError(
            f"unsupported architecture: {machine}",
            remediation=_INSTALL_REMEDIATION,
        )
    return system, architecture


def select_artifact(
    artifacts: Iterable[ReleaseArtifact],
    platform: str,
    architecture: str,
) -> ReleaseArtifact:
    """Select the artifact matching an exact normalized platform pair."""

    for artifact in artifacts:
        if artifact.platform == platform and artifact.architecture == architecture:
            return artifact
    raise UsageError(
        f"no release artifact for {platform}/{architecture}",
        remediation=_INSTALL_REMEDIATION,
    )


def download_verified(
    artifact: ReleaseArtifact,
    destination: str | os.PathLike[str],
    opener: Callable[[str], BinaryIO] = urlopen,
) -> Path:
    """Stream, verify, and atomically publish one release artifact."""

    destination_path = Path(destination)
    temporary_path: Path | None = None
    file_descriptor: int | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination_path.name}.",
            suffix=".tmp",
            dir=destination_path.parent,
        )
        temporary_path = Path(temporary_name)
        digest = hashlib.sha256()
        byte_count = 0
        output = os.fdopen(file_descriptor, "wb")
        file_descriptor = None
        with output:
            with opener(artifact.url) as response:
                while chunk := response.read(64 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
                    byte_count += len(chunk)
                output.flush()
                os.fsync(output.fileno())

        if byte_count != artifact.size:
            raise IntegrityError(
                f"release artifact size mismatch: expected {artifact.size}, "
                f"received {byte_count}",
                path=destination_path,
                remediation="download the release artifact again",
            )
        actual_digest = digest.hexdigest()
        if actual_digest != artifact.sha256:
            raise IntegrityError(
                "release artifact SHA-256 mismatch",
                path=destination_path,
                remediation="download the release artifact again",
            )
        os.replace(temporary_path, destination_path)
        temporary_path = None
        return destination_path
    finally:
        try:
            if file_descriptor is not None:
                os.close(file_descriptor)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
