"""Validated export of the generated universal prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .build import (
    _atomic_write,
    _dist_path,
    _ensure_contained,
    _resolve_repository_root,
)
from .errors import CollisionError, FilesystemError, IntegrityError
from .manifest import sha256_bytes, validate_manifest
from .safe_fs import ParentIdentity, capture_parent_chain, identity_bound_mkdir


def _read_artifact(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as error:
        raise IntegrityError(
            f"{label} is missing",
            path=path,
            remediation="run 'python -m socratic_learn build'",
        ) from error
    except OSError as error:
        raise FilesystemError(
            f"{label} could not be read",
            path=path,
            remediation=(
                "check artifact permissions and run "
                "'python -m socratic_learn build'"
            ),
        ) from error


def _ensure_output_parent(
    repository: Path,
    parent: Path,
) -> tuple[ParentIdentity, ...]:
    try:
        relative = parent.relative_to(repository)
    except ValueError as error:
        raise IntegrityError(
            "export parent escapes the repository",
            path=parent,
            remediation="choose an output inside the repository",
        ) from error
    current = repository
    for part in relative.parts:
        current /= part
        if current.exists() or current.is_symlink():
            try:
                capture_parent_chain(repository, current / ".export-parent-probe")
            except OSError as error:
                raise IntegrityError(
                    "export parent is not a plain identity-bound directory",
                    path=current,
                    remediation="choose a different output path",
                ) from error
            continue
        try:
            identity_bound_mkdir(current, root=repository)
        except FileExistsError as error:
            raise CollisionError(
                "export parent appeared during creation",
                path=current,
                remediation="preserve the raced path and choose another output",
            ) from error
        except OSError as error:
            raise FilesystemError(
                "export directory could not be created safely",
                path=current,
                remediation="choose a writable directory inside the repository",
            ) from error
    return capture_parent_chain(repository, parent / ".export-parent-probe")


def export_prompt(output: Path | None = None, *, root: Path | None = None) -> None:
    """Validate checked-in build artifacts and export exact prompt bytes."""

    repository = _resolve_repository_root(Path.cwd() if root is None else root)
    dist = _dist_path(repository)
    manifest_path = _ensure_contained(
        repository,
        dist / "manifest.json",
        display_path="dist/manifest.json",
    )
    manifest_bytes = _read_artifact(manifest_path, "distribution manifest")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise IntegrityError(
            "distribution manifest is not valid UTF-8 JSON",
            path=manifest_path,
            remediation="run 'python -m socratic_learn build'",
        ) from error
    if not isinstance(manifest, dict):
        raise IntegrityError(
            "distribution manifest must contain a JSON object",
            path="dist/manifest.json",
            remediation="run 'python -m socratic_learn build'",
        )
    validate_manifest(manifest)

    bundle = manifest["bundle"]
    assert isinstance(bundle, dict)
    bundle_path = _ensure_contained(
        repository,
        dist / bundle["path"],
        display_path=f"dist/{bundle['path']}",
    )
    bundle_bytes = _read_artifact(bundle_path, "distribution prompt")
    if sha256_bytes(bundle_bytes) != bundle["sha256"]:
        raise IntegrityError(
            "distribution prompt hash does not match the manifest",
            path=bundle_path,
            remediation="run 'python -m socratic_learn build'",
        )

    if output is None:
        try:
            sys.stdout.buffer.write(bundle_bytes)
            sys.stdout.buffer.flush()
        except OSError as error:
            raise FilesystemError(
                "distribution prompt could not be written to standard output",
                path="<stdout>",
                remediation="use --output with a writable path inside the repository",
            ) from error
        return
    requested_output = output if output.is_absolute() else repository / output
    safe_output = _ensure_contained(
        repository,
        requested_output,
        display_path=output,
    )
    if safe_output.exists() or safe_output.is_symlink():
        raise CollisionError(
            "export output already exists",
            path=safe_output,
            remediation="choose a new output path; export has no --force mode",
        )
    destination_chain = _ensure_output_parent(repository, safe_output.parent)
    try:
        _atomic_write(
            safe_output,
            bundle_bytes,
            root=repository,
            temporary_directory=repository,
            expected_destination_chain=destination_chain,
        )
    except FilesystemError as error:
        if isinstance(error.__cause__, FileExistsError):
            raise CollisionError(
                "export output appeared during atomic publication",
                path=safe_output,
                remediation=(
                    "preserve the raced output and choose a new path; inspect "
                    "the temporary recovery path reported by the original error"
                ),
            ) from error
        raise
