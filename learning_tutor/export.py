"""Validated export of the generated universal prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .build import _atomic_write
from .errors import FilesystemError, IntegrityError
from .manifest import sha256_bytes, validate_manifest


def _read_artifact(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as error:
        raise IntegrityError(
            f"{label} is missing",
            path=path,
            remediation="run 'learning-tutor build'",
        ) from error
    except OSError as error:
        raise FilesystemError(f"{label} could not be read", path=path) from error


def export_prompt(output: Path | None = None, *, root: Path | None = None) -> None:
    """Validate checked-in build artifacts and export exact prompt bytes."""

    repository = Path.cwd() if root is None else root
    manifest_path = repository / "dist/manifest.json"
    manifest_bytes = _read_artifact(manifest_path, "distribution manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(
            "distribution manifest is not valid UTF-8 JSON",
            path=manifest_path,
            remediation="run 'learning-tutor build'",
        ) from error
    if not isinstance(manifest, dict):
        raise IntegrityError("distribution manifest must contain a JSON object")
    validate_manifest(manifest)

    bundle = manifest["bundle"]
    assert isinstance(bundle, dict)
    bundle_path = repository / "dist" / bundle["path"]
    bundle_bytes = _read_artifact(bundle_path, "distribution prompt")
    if sha256_bytes(bundle_bytes) != bundle["sha256"]:
        raise IntegrityError(
            "distribution prompt hash does not match the manifest",
            path=bundle_path,
            remediation="run 'learning-tutor build'",
        )

    if output is None:
        sys.stdout.buffer.write(bundle_bytes)
        sys.stdout.buffer.flush()
        return
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise FilesystemError("export directory could not be created", path=output.parent) from error
    _atomic_write(output, bundle_bytes)
