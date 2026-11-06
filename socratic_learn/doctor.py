"""Read-only installation and integrity diagnostics."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import PROTOCOL_VERSION
from .conformance import Diagnostic
from .errors import FilesystemError, IntegrityError, LearningTutorError
from .install import (
    INSTALL_ROOT,
    LEGACY_INSTALL_ROOT,
    LEGACY_RECEIPT_PATH,
    RECEIPT_PATH,
    InstallReceipt,
    _claude_snippet,
    _is_reparse_or_symlink,
    _parse_receipt,
    _portable_relative_path,
    _resolve_directory,
    _template_bytes,
    _verify_legacy_tree_is_migratable,
)
from .manifest import sha256_bytes, validate_manifest


_MANIFEST_PATH = f"{INSTALL_ROOT}/manifest.json"
_BUNDLE_PATH = f"{INSTALL_ROOT}/socratic-learn.prompt.md"
_GENERIC_LOADER_PATH = f"{INSTALL_ROOT}/loader.md"
_IGNORE_PATH = f"{INSTALL_ROOT}/.gitignore"
_WORKSPACE_KEEP = f"{INSTALL_ROOT}/workspace/.gitkeep"
_NATIVE_PATHS = {
    "cursor": ".cursor/skills/socratic-learn/SKILL.md",
    "claude-code": "CLAUDE.md",
    "pi": ".pi/skills/socratic-learn/SKILL.md",
}
_LOADER_REFERENCES = {
    "generic": ".socratic-learn/socratic-learn.prompt.md",
    "cursor": "../../../.socratic-learn/socratic-learn.prompt.md",
    "claude-code": ".socratic-learn/socratic-learn.prompt.md",
    "pi": "../../../.socratic-learn/socratic-learn.prompt.md",
}
_PARTIAL_MARKERS = (
    _MANIFEST_PATH,
    _BUNDLE_PATH,
    _GENERIC_LOADER_PATH,
    *_NATIVE_PATHS.values(),
)


@dataclass(frozen=True)
class _ChainEntry:
    path: Path
    device: int
    inode: int
    mode: int


def _diagnostic(
    code: str,
    path: str,
    message: str,
    remediation: str,
) -> Diagnostic:
    return Diagnostic(code, path, message, remediation)


def _ordered_diagnostics(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]:
    unique = dict.fromkeys(diagnostics)
    return sorted(unique, key=lambda item: (item.code, item.path))


def _relative_error_path(project: Path, value: object, fallback: str) -> str:
    try:
        path = Path(value)  # type: ignore[arg-type]
        if path.is_absolute():
            return path.relative_to(project).as_posix()
        return path.as_posix()
    except (TypeError, ValueError):
        return fallback


def _safe_managed_path(project: Path, relative: str) -> Path:
    if not _portable_relative_path(relative):
        raise IntegrityError(
            "managed path is not a control-free relative POSIX path",
            path=relative,
            remediation="repair the receipt before inspecting managed files",
        )
    candidate = project.joinpath(*PurePosixPath(relative).parts)
    current = project
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        current /= part
        try:
            status = current.stat(follow_symlinks=False)
        except FileNotFoundError:
            break
        except OSError as error:
            raise FilesystemError(
                f"managed path metadata could not be read: {error}",
                path=relative,
                remediation="check path permissions and rerun doctor",
            ) from error
        if _is_reparse_or_symlink(status):
            raise IntegrityError(
                "managed path contains a symlink or reparse point",
                path=relative,
                remediation="replace the unsafe path with a project-local regular path",
            )
        if index < len(parts) - 1 and not stat.S_ISDIR(status.st_mode):
            raise IntegrityError(
                "managed path has a non-directory parent",
                path=relative,
                remediation="replace the blocking parent with a project-local directory",
            )
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise IntegrityError(
            "managed path cannot be resolved safely",
            path=relative,
            remediation="replace the unsafe path with a project-local regular path",
        ) from error
    if not resolved.is_relative_to(project):
        raise IntegrityError(
            "managed path resolves outside the project",
            path=relative,
            remediation="replace the escaping path with a project-local regular path",
        )
    return candidate


def _capture_managed_chain(
    project: Path,
    relative: str,
) -> tuple[Path, tuple[_ChainEntry, ...]] | None:
    if not _portable_relative_path(relative):
        raise IntegrityError(
            "managed path is not a control-free relative POSIX path",
            path=relative,
            remediation="repair the receipt before inspecting managed files",
        )
    candidate = project.joinpath(*PurePosixPath(relative).parts)
    entries: list[_ChainEntry] = []
    current = project
    components = (".", *PurePosixPath(relative).parts)
    for index, part in enumerate(components):
        if part != ".":
            current /= part
        try:
            status = current.stat(follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise FilesystemError(
                f"managed path metadata could not be read: {error}",
                path=relative,
                remediation="check path permissions and rerun doctor",
            ) from error
        if _is_reparse_or_symlink(status):
            raise IntegrityError(
                "managed path contains a symlink or reparse point",
                path=relative,
                remediation="replace the unsafe path with a project-local regular path",
            )
        if index < len(components) - 1 and not stat.S_ISDIR(status.st_mode):
            raise IntegrityError(
                "managed path has a non-directory parent",
                path=relative,
                remediation="replace the blocking parent with a project-local directory",
            )
        entries.append(
            _ChainEntry(
                current,
                status.st_dev,
                status.st_ino,
                status.st_mode,
            )
        )
    if not stat.S_ISREG(entries[-1].mode):
        raise IntegrityError(
            "managed file is not a regular file",
            path=relative,
            remediation="replace the unsafe path with a project-local regular file",
        )
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise IntegrityError(
            "managed path cannot be resolved safely",
            path=relative,
            remediation="replace the unsafe path with a project-local regular path",
        ) from error
    if not resolved.is_relative_to(project):
        raise IntegrityError(
            "managed path resolves outside the project",
            path=relative,
            remediation="replace the escaping path with a project-local regular path",
        )
    return candidate, tuple(entries)


def _before_managed_open(project: Path, relative: str, path: Path) -> None:
    """Narrow validation/open boundary hook for race testing."""


def _read_descriptor(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _entry_matches_status(entry: _ChainEntry, status: os.stat_result) -> bool:
    return (
        entry.device == status.st_dev
        and entry.inode == status.st_ino
        and stat.S_IFMT(entry.mode) == stat.S_IFMT(status.st_mode)
    )


def _supports_bound_reads() -> bool:
    return (
        os.open in os.supports_dir_fd
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    )


def _changed_path_error(relative: str) -> IntegrityError:
    return IntegrityError(
        "managed path identity changed before it could be read",
        path=relative,
        remediation="preserve the changed path and rerun doctor after inspection",
    )


def _raise_open_error(
    project: Path,
    relative: str,
    expected: tuple[_ChainEntry, ...],
    error: OSError,
) -> None:
    try:
        current = _capture_managed_chain(project, relative)
    except IntegrityError as changed:
        raise changed from error
    if current is None or current[1] != expected:
        raise _changed_path_error(relative) from error
    raise FilesystemError(
        f"managed path could not be opened without following links: {error}",
        path=relative,
        remediation="check path permissions and rerun doctor",
    ) from error


def _verify_open_chain(
    project: Path,
    relative: str,
    expected: tuple[_ChainEntry, ...],
) -> None:
    current = _capture_managed_chain(project, relative)
    if current is None or current[1] != expected:
        raise _changed_path_error(relative)


def _read_with_dir_descriptors(
    project: Path,
    relative: str,
    expected: tuple[_ChainEntry, ...],
) -> bytes:
    descriptors: list[int] = []
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        try:
            parent_descriptor = os.open(project, flags)
        except OSError as error:
            _raise_open_error(project, relative, expected, error)
            raise AssertionError("unreachable")
        descriptors.append(parent_descriptor)
        if not _entry_matches_status(expected[0], os.fstat(parent_descriptor)):
            raise _changed_path_error(relative)
        for entry in expected[1:-1]:
            try:
                parent_descriptor = os.open(
                    entry.path.name,
                    flags,
                    dir_fd=parent_descriptor,
                )
            except OSError as error:
                _raise_open_error(project, relative, expected, error)
                raise AssertionError("unreachable")
            descriptors.append(parent_descriptor)
            if not _entry_matches_status(entry, os.fstat(parent_descriptor)):
                raise _changed_path_error(relative)
        try:
            file_descriptor = os.open(
                expected[-1].path.name,
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
        except OSError as error:
            _raise_open_error(project, relative, expected, error)
            raise AssertionError("unreachable")
        descriptors.append(file_descriptor)
        if not _entry_matches_status(expected[-1], os.fstat(file_descriptor)):
            raise _changed_path_error(relative)
        _verify_open_chain(project, relative, expected)
        return _read_descriptor(file_descriptor)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _read_with_path_descriptor(
    project: Path,
    relative: str,
    path: Path,
    expected: tuple[_ChainEntry, ...],
) -> bytes:
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    try:
        try:
            descriptor = os.open(path, flags)
        except OSError as error:
            _raise_open_error(project, relative, expected, error)
            raise AssertionError("unreachable")
        if not _entry_matches_status(expected[-1], os.fstat(descriptor)):
            raise _changed_path_error(relative)
        _verify_open_chain(project, relative, expected)
        return _read_descriptor(descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _path_diagnostic(error: LearningTutorError, relative: str) -> Diagnostic:
    code = (
        "unsafe-managed-path"
        if isinstance(error, IntegrityError)
        else "managed-path-unreadable"
    )
    return _diagnostic(
        code,
        relative,
        error.message,
        error.remediation or "inspect the managed path and rerun doctor",
    )


def _read_managed_bytes(
    project: Path,
    relative: str,
) -> tuple[bytes | None, Diagnostic | None]:
    try:
        captured = _capture_managed_chain(project, relative)
    except LearningTutorError as error:
        return None, _path_diagnostic(error, relative)
    if captured is None:
        return None, None
    path, expected = captured
    try:
        _before_managed_open(project, relative, path)
        if _supports_bound_reads():
            return _read_with_dir_descriptors(project, relative, expected), None
        return _read_with_path_descriptor(project, relative, path, expected), None
    except LearningTutorError as error:
        return None, _path_diagnostic(error, relative)
    except OSError as error:
        return None, _diagnostic(
            "managed-path-unreadable",
            relative,
            f"managed path could not be read: {error}",
            "check path permissions and rerun doctor",
        )


def _has_partial_install(project: Path) -> tuple[bool, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    found = False
    for relative in (INSTALL_ROOT, *_PARTIAL_MARKERS):
        try:
            path = _safe_managed_path(project, relative)
            path.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue
        except LearningTutorError as error:
            diagnostics.append(_path_diagnostic(error, relative))
            found = True
            continue
        except OSError as error:
            diagnostics.append(
                _diagnostic(
                    "managed-path-unreadable",
                    relative,
                    f"managed path metadata could not be read: {error}",
                    "check path permissions and rerun doctor",
                )
            )
            found = True
            continue
        found = True
    return found, diagnostics


def _receipt_diagnostics(
    project: Path,
) -> tuple[InstallReceipt | None, list[Diagnostic]]:
    receipt_bytes, path_diagnostic = _read_managed_bytes(project, RECEIPT_PATH)
    if path_diagnostic is not None:
        return None, [path_diagnostic]
    if receipt_bytes is None:
        partial, partial_diagnostics = _has_partial_install(project)
        if partial:
            return None, [
                _diagnostic(
                    "missing-receipt",
                    RECEIPT_PATH,
                    "installation files exist but the ownership receipt is missing",
                    (
                        "preserve the partial installation and recovery artifacts, "
                        "then reinstall only after manual review"
                    ),
                ),
                *partial_diagnostics,
            ]
        return None, [
            _diagnostic(
                "installation-not-found",
                INSTALL_ROOT,
                "no Socratic Learn installation or ownership receipt was found",
                "install Socratic Learn into this project",
            )
        ]
    try:
        value = json.loads(receipt_bytes.decode("utf-8"))
        receipt = _parse_receipt(value, project / RECEIPT_PATH)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [
            _diagnostic(
                "invalid-receipt",
                RECEIPT_PATH,
                f"installation receipt is not valid UTF-8 JSON: {error}",
                "remove the invalid installation and reinstall",
            )
        ]
    except LearningTutorError as error:
        remediation = error.remediation or (
            "preserve the installation and reinstall after manual review"
        )
        if "compatible" in remediation.lower() and "version" in remediation.lower():
            remediation = "reinstall with a compatible Socratic Learn version"
        return None, [
            _diagnostic(
                "invalid-receipt",
                _relative_error_path(project, error.path, RECEIPT_PATH),
                error.message,
                remediation,
            )
        ]
    return receipt, []


def _path_exists_no_follow(path: Path) -> bool:
    try:
        path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _legacy_installation_diagnostics(project: Path) -> list[Diagnostic]:
    receipt_bytes, path_diagnostic = _read_managed_bytes(
        project,
        LEGACY_RECEIPT_PATH,
    )
    if path_diagnostic is not None:
        return [path_diagnostic]
    if receipt_bytes is None:
        return [
            _diagnostic(
                "missing-receipt",
                LEGACY_RECEIPT_PATH,
                "legacy installation files exist but their receipt is missing",
                "preserve the legacy installation and migrate manually",
            )
        ]
    try:
        value = json.loads(receipt_bytes.decode("utf-8"))
        receipt = _parse_receipt(
            value,
            project / LEGACY_RECEIPT_PATH,
            legacy=True,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, LearningTutorError) as error:
        message = (
            error.message
            if isinstance(error, LearningTutorError)
            else f"legacy receipt is not valid UTF-8 JSON: {error}"
        )
        return [
            _diagnostic(
                "invalid-receipt",
                LEGACY_RECEIPT_PATH,
                message,
                "preserve the legacy installation and migrate manually",
            )
        ]
    diagnostics: list[Diagnostic] = []
    for relative, expected in receipt.hashes:
        content, read_diagnostic = _read_managed_bytes(project, relative)
        if read_diagnostic is not None:
            diagnostics.append(read_diagnostic)
        elif content is None:
            diagnostics.append(
                _diagnostic(
                    "owned-file-missing",
                    relative,
                    "a legacy installation-owned file is missing",
                    "restore the legacy file before migration",
                )
            )
        elif sha256_bytes(content) != expected:
            diagnostics.append(
                _diagnostic(
                    "owned-file-changed",
                    relative,
                    "a legacy installation-owned file was modified",
                    "restore the legacy file or migrate manually",
                )
            )
    if diagnostics:
        return _ordered_diagnostics(diagnostics)
    try:
        _verify_legacy_tree_is_migratable(project, receipt)
    except LearningTutorError as error:
        return [
            _diagnostic(
                "legacy-installation-unsafe",
                _relative_error_path(
                    project,
                    error.path,
                    LEGACY_INSTALL_ROOT,
                ),
                error.message,
                error.remediation
                or "preserve the legacy installation and migrate manually",
            )
        ]
    except OSError as error:
        return [
            _diagnostic(
                "legacy-installation-unsafe",
                LEGACY_INSTALL_ROOT,
                f"legacy installation tree could not be validated: {error}",
                "preserve the legacy installation and migrate manually",
            )
        ]
    return [
        _diagnostic(
            "legacy-installation",
            LEGACY_RECEIPT_PATH,
            "a managed Learning Tutor installation can be migrated",
            (
                "run 'python -m socratic_learn install "
                f"{receipt.target} PROJECT --update'"
            ),
        )
    ]


def _owned_file_diagnostics(
    project: Path,
    receipt: InstallReceipt,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    hashes = dict(receipt.hashes)
    for relative in receipt.owned_paths:
        if relative == RECEIPT_PATH:
            continue
        content, path_diagnostic = _read_managed_bytes(project, relative)
        if path_diagnostic is not None:
            diagnostics.append(path_diagnostic)
            continue
        if content is None:
            diagnostics.append(
                _diagnostic(
                    "owned-file-missing",
                    relative,
                    "an installation-owned file is missing",
                    "restore the owned file from a trusted installation or reinstall",
                )
            )
            continue
        expected = hashes.get(relative)
        if expected is not None and sha256_bytes(content) != expected:
            diagnostics.append(
                _diagnostic(
                    "owned-file-changed",
                    relative,
                    "an installation-owned file differs from its receipt hash",
                    "restore the owned file from a trusted installation or reinstall",
                )
            )
    return diagnostics


def _manifest_diagnostics(project: Path) -> list[Diagnostic]:
    manifest_bytes, path_diagnostic = _read_managed_bytes(project, _MANIFEST_PATH)
    if path_diagnostic is not None:
        return [path_diagnostic]
    if manifest_bytes is None:
        return []
    try:
        value = json.loads(manifest_bytes.decode("utf-8"))
        validate_manifest(value)
    except (UnicodeDecodeError, json.JSONDecodeError, LearningTutorError) as error:
        message = error.message if isinstance(error, LearningTutorError) else str(error)
        return [
            _diagnostic(
                "invalid-manifest",
                _MANIFEST_PATH,
                f"the installed manifest is invalid: {message}",
                "restore the manifest and bundle from a trusted installation",
            )
        ]
    bundle = value["bundle"]
    assert isinstance(bundle, dict)
    bundle_relative = f"{INSTALL_ROOT}/{bundle['path']}"
    bundle_bytes, path_diagnostic = _read_managed_bytes(project, bundle_relative)
    if path_diagnostic is not None:
        return [path_diagnostic]
    if bundle_bytes is None:
        return []
    if sha256_bytes(bundle_bytes) == bundle["sha256"]:
        return []
    return [
        _diagnostic(
            "bundle-hash-mismatch",
            bundle_relative,
            "the installed bundle hash does not match the installed manifest",
            "restore the manifest and bundle together from a trusted installation",
        )
    ]


def _discovery_diagnostics(
    project: Path,
    receipt: InstallReceipt,
) -> list[Diagnostic]:
    target = receipt.target
    if target == "claude-code" and "CLAUDE.md" not in receipt.owned_paths:
        content, path_diagnostic = _read_managed_bytes(project, "CLAUDE.md")
        if path_diagnostic is not None:
            return [path_diagnostic]
        if content is not None:
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                return [
                    _diagnostic(
                        "managed-path-unreadable",
                        "CLAUDE.md",
                        f"manual Claude integration could not be verified as UTF-8: {error}",
                        "save CLAUDE.md as UTF-8 and rerun doctor",
                    )
                ]
            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            snippet = _claude_snippet().replace("\r\n", "\n").replace("\r", "\n")
            if snippet.rstrip("\n") in normalized:
                return []
        return [
            _diagnostic(
                "manual-integration-required",
                "CLAUDE.md",
                "the user-owned Claude file does not contain the exact required loader snippet",
                (
                    "append the exact emitted loader snippet to CLAUDE.md "
                    "without replacing existing content"
                ),
            )
        ]

    if target == "generic":
        expected = _GENERIC_LOADER_PATH
    else:
        expected = _NATIVE_PATHS[target]
    if target == "generic":
        expected_bytes = _template_bytes("generic-loader.md")
    elif target in ("cursor", "pi"):
        expected_bytes = _template_bytes(f"{target}-skill.md", "../../../")
    else:
        expected_bytes = _template_bytes("claude-loader.md")

    content, path_diagnostic = _read_managed_bytes(project, expected)
    if path_diagnostic is not None:
        return [path_diagnostic]
    if content is None:
        candidate_diagnostics: list[Diagnostic] = []
        wrong = None
        candidates = (
            _GENERIC_LOADER_PATH,
            *_NATIVE_PATHS.values(),
        )
        for relative in candidates:
            if relative == expected:
                continue
            candidate, candidate_diagnostic = _read_managed_bytes(project, relative)
            if candidate_diagnostic is not None:
                candidate_diagnostics.append(candidate_diagnostic)
                continue
            if candidate == expected_bytes:
                wrong = relative
                break
        if wrong is not None:
            candidate_diagnostics.append(
                _diagnostic(
                    "wrong-native-discovery-path",
                    expected,
                    f"the {target} loader is published at the wrong discovery path: {wrong}",
                    f"restore the owned loader at {expected}",
                )
            )
        else:
            candidate_diagnostics.append(
                _diagnostic(
                    "discovery-path-missing",
                    expected,
                    f"the {target} loader is missing from its discovery path",
                    f"restore the owned loader at {expected}",
                )
            )
        return candidate_diagnostics
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        return [
            _diagnostic(
                "managed-path-unreadable",
                expected,
                f"target loader is not valid UTF-8: {error}",
                "restore the target loader from a trusted installation",
            )
        ]
    reference = _LOADER_REFERENCES[target]
    if reference in text:
        return []
    return [
        _diagnostic(
            "broken-loader-link",
            expected,
            "the target loader does not reference the installed prompt bundle",
            f"restore the loader reference to {reference}",
        )
    ]


def _ignore_diagnostics(project: Path) -> list[Diagnostic]:
    content, path_diagnostic = _read_managed_bytes(project, _IGNORE_PATH)
    if path_diagnostic is not None:
        return [path_diagnostic]
    if content is None:
        return []
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        return [
            _diagnostic(
                "managed-path-unreadable",
                _IGNORE_PATH,
                f"nested ignore file is not valid UTF-8: {error}",
                "restore the nested ignore file from a trusted installation",
            )
        ]
    required = ("workspace/*", "!workspace/.gitkeep")
    missing = [rule for rule in required if rule not in lines]
    if not missing:
        return []
    return [
        _diagnostic(
            "missing-private-ignore-rule",
            _IGNORE_PATH,
            f"the nested ignore file is missing required rule(s): {', '.join(missing)}",
            "restore both workspace/* and !workspace/.gitkeep in the nested ignore file",
        )
    ]


def _git_marker(project: Path) -> Path | None:
    for directory in (project, *project.parents):
        marker = directory / ".git"
        if marker.exists() or marker.is_symlink():
            return marker
    return None


def _git_diagnostics(project: Path) -> list[Diagnostic]:
    marker = _git_marker(project)
    if marker is None:
        return []
    command = [
        "git",
        "-C",
        str(project),
        "ls-files",
        "--",
        f"{INSTALL_ROOT}/workspace",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return [
            _diagnostic(
                "git-check-failed",
                _relative_error_path(project, marker, ".git"),
                f"Git could not inspect tracked private files: {error}",
                "restore Git access and rerun doctor",
            )
        ]
    if result.returncode != 0:
        detail = result.stderr.strip() or f"Git exited with status {result.returncode}"
        return [
            _diagnostic(
                "git-check-failed",
                _relative_error_path(project, marker, ".git"),
                f"Git could not inspect tracked private files: {detail}",
                "repair the repository or Git installation and rerun doctor",
            )
        ]
    diagnostics = []
    for raw_path in result.stdout.splitlines():
        relative = raw_path.replace("\\", "/")
        if relative == _WORKSPACE_KEEP:
            continue
        diagnostics.append(
            _diagnostic(
                "tracked-private-file",
                relative,
                "a private workspace file is tracked by Git",
                f"remove {relative} from the Git index without deleting the local file",
            )
        )
    return diagnostics


def diagnose(project: Path) -> list[Diagnostic]:
    """Return read-only installation diagnostics in deterministic order."""

    resolved_project = _resolve_directory(project, "project")
    canonical_present = _path_exists_no_follow(
        resolved_project / INSTALL_ROOT
    )
    legacy_present = _path_exists_no_follow(
        resolved_project / LEGACY_INSTALL_ROOT
    )
    if canonical_present and legacy_present:
        return [
            _diagnostic(
                "installation-root-collision",
                ".",
                "canonical and legacy installation roots both exist",
                "preserve both roots and resolve the collision manually",
            )
        ]
    if legacy_present and not canonical_present:
        return _legacy_installation_diagnostics(resolved_project)
    receipt, diagnostics = _receipt_diagnostics(resolved_project)
    if receipt is None:
        return _ordered_diagnostics(diagnostics)

    if receipt.protocol_version != PROTOCOL_VERSION:
        diagnostics.append(
            _diagnostic(
                "protocol-mismatch",
                RECEIPT_PATH,
                (
                    f"the receipt protocol {receipt.protocol_version!r} does not "
                    f"match supported protocol {PROTOCOL_VERSION!r}"
                ),
                "install with a compatible socratic-learn version",
            )
        )
    diagnostics.extend(_owned_file_diagnostics(resolved_project, receipt))
    diagnostics.extend(_manifest_diagnostics(resolved_project))
    diagnostics.extend(_discovery_diagnostics(resolved_project, receipt))
    diagnostics.extend(_ignore_diagnostics(resolved_project))
    diagnostics.extend(_git_diagnostics(resolved_project))
    return _ordered_diagnostics(diagnostics)


def format_diagnostics(diagnostics: Sequence[Diagnostic]) -> str:
    """Format diagnostics as stable actionable blocks."""

    blocks = [
        (
            f"[{item.code}]\n"
            f"Path: {item.path}\n"
            f"Message: {item.message}\n"
            f"Remediation: {item.remediation}"
        )
        for item in diagnostics
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")
