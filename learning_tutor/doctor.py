"""Read-only installation and integrity diagnostics."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from . import PROTOCOL_VERSION
from .conformance import Diagnostic
from .errors import LearningTutorError
from .install import (
    INSTALL_ROOT,
    RECEIPT_PATH,
    InstallReceipt,
    _project_path,
    _read_receipt,
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


def _relative_error_path(project: Path, value: object, fallback: str) -> str:
    try:
        path = Path(value)  # type: ignore[arg-type]
        if path.is_absolute():
            return path.relative_to(project).as_posix()
        return path.as_posix()
    except (TypeError, ValueError):
        return fallback


def _has_partial_install(project: Path) -> bool:
    install_root = project / INSTALL_ROOT
    if install_root.exists() or install_root.is_symlink():
        return True
    return any(
        (project.joinpath(*PurePosixPath(relative).parts)).exists()
        for relative in _PARTIAL_MARKERS
    )


def _receipt_diagnostics(
    project: Path,
) -> tuple[InstallReceipt | None, list[Diagnostic]]:
    receipt_path = project / RECEIPT_PATH
    if not receipt_path.exists():
        if _has_partial_install(project):
            return None, [
                _diagnostic(
                    "missing-receipt",
                    RECEIPT_PATH,
                    "installation files exist but the ownership receipt is missing",
                    (
                        "preserve the partial installation and recovery artifacts, "
                        "then reinstall only after manual review"
                    ),
                )
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
        receipt, _ = _read_receipt(project)
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
        try:
            path = _project_path(project, relative)
        except LearningTutorError as error:
            diagnostics.append(
                _diagnostic(
                    "invalid-owned-path",
                    relative,
                    error.message,
                    error.remediation or "repair the receipt and reinstall",
                )
            )
            continue
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            diagnostics.append(
                _diagnostic(
                    "owned-file-missing",
                    relative,
                    "an installation-owned file is missing",
                    "restore the owned file from a trusted installation or reinstall",
                )
            )
            continue
        except OSError as error:
            diagnostics.append(
                _diagnostic(
                    "owned-file-unreadable",
                    relative,
                    f"an installation-owned file could not be read: {error}",
                    "check filesystem permissions and inspect the file",
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
    path = project / _MANIFEST_PATH
    try:
        manifest_bytes = path.read_bytes()
    except OSError:
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
    try:
        bundle_bytes = _project_path(project, bundle_relative).read_bytes()
    except (LearningTutorError, OSError):
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
    owned = set(receipt.owned_paths)
    if target == "generic":
        expected = _GENERIC_LOADER_PATH
    elif target == "claude-code" and "CLAUDE.md" not in owned:
        return []
    else:
        expected = _NATIVE_PATHS[target]
    expected_path = project.joinpath(*PurePosixPath(expected).parts)
    if not expected_path.is_file():
        if target in ("cursor", "pi"):
            expected_bytes = _template_bytes(f"{target}-skill.md", "../../../")
        else:
            expected_bytes = b""
        wrong = next(
            (
                relative
                for other_target, relative in _NATIVE_PATHS.items()
                if other_target != target
                and project.joinpath(*PurePosixPath(relative).parts).is_file()
                and project.joinpath(*PurePosixPath(relative).parts).read_bytes()
                == expected_bytes
            ),
            None,
        )
        if wrong is None:
            return []
        return [
            _diagnostic(
                "wrong-native-discovery-path",
                expected,
                f"the {target} loader is published at the wrong discovery path: {wrong}",
                f"restore the owned loader at {expected}",
            )
        ]
    try:
        content = expected_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    reference = _LOADER_REFERENCES[target]
    if reference in content:
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
    path = project / _IGNORE_PATH
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
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
        return sorted(diagnostics, key=lambda item: (item.code, item.path))

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
    return sorted(diagnostics, key=lambda item: (item.code, item.path))


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
