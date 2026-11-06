"""Read-only installation and integrity diagnostics."""

from __future__ import annotations

import json
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from . import PROTOCOL_VERSION
from .conformance import Diagnostic
from .errors import FilesystemError, IntegrityError, LearningTutorError
from .install import (
    INSTALL_ROOT,
    RECEIPT_PATH,
    InstallReceipt,
    _claude_snippet,
    _is_reparse_or_symlink,
    _parse_receipt,
    _portable_relative_path,
    _resolve_directory,
    _template_bytes,
)
from .manifest import sha256_bytes, validate_manifest


_MANIFEST_PATH = f"{INSTALL_ROOT}/manifest.json"
_BUNDLE_PATH = f"{INSTALL_ROOT}/learning-tutor.prompt.md"
_GENERIC_LOADER_PATH = f"{INSTALL_ROOT}/loader.md"
_IGNORE_PATH = f"{INSTALL_ROOT}/.gitignore"
_WORKSPACE_KEEP = f"{INSTALL_ROOT}/workspace/.gitkeep"
_NATIVE_PATHS = {
    "cursor": ".cursor/skills/learning-tutor/SKILL.md",
    "claude-code": "CLAUDE.md",
    "pi": ".pi/skills/learning-tutor/SKILL.md",
}
_LOADER_REFERENCES = {
    "generic": ".learning-tutor/learning-tutor.prompt.md",
    "cursor": "../../../.learning-tutor/learning-tutor.prompt.md",
    "claude-code": ".learning-tutor/learning-tutor.prompt.md",
    "pi": "../../../.learning-tutor/learning-tutor.prompt.md",
}
_PARTIAL_MARKERS = (
    _MANIFEST_PATH,
    _BUNDLE_PATH,
    _GENERIC_LOADER_PATH,
    *_NATIVE_PATHS.values(),
)


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
        path = _safe_managed_path(project, relative)
    except LearningTutorError as error:
        return None, _path_diagnostic(error, relative)
    try:
        return path.read_bytes(), None
    except FileNotFoundError:
        return None, None
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
                "no learning tutor installation or ownership receipt was found",
                "install the learning tutor into this project",
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
        if "compatible learning-tutor version" in remediation:
            remediation = "reinstall with a compatible learning-tutor version"
        return None, [
            _diagnostic(
                "invalid-receipt",
                _relative_error_path(project, error.path, RECEIPT_PATH),
                error.message,
                remediation,
            )
        ]
    return receipt, []


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
    if receipt.loader_mode == "manual-snippet":
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
                "install with a compatible learning-tutor version",
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
