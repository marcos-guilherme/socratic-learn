"""Trusted Windows executable path validation."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import stat

from .errors import UsageError


def safe_regular_windows_file(path: Path, *, label: str) -> Path:
    """Require a regular file reached without links or reparse points."""
    absolute = Path(os.path.abspath(path))
    for component in (*reversed(absolute.parents), absolute):
        try:
            status = os.lstat(component)
        except OSError as error:
            raise UsageError(
                f"{label} must be an inspectable safe regular file",
                path=absolute,
                remediation="repair or reinstall the trusted executable and retry",
            ) from error
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(status.st_mode) or (
            getattr(status, "st_file_attributes", 0) & reparse_flag
        ):
            raise UsageError(
                f"{label} must be a safe regular file without links",
                path=absolute,
                remediation="replace the linked path with regular local files",
            )
    if not stat.S_ISREG(os.lstat(absolute).st_mode):
        raise UsageError(
            f"{label} must be a safe regular file",
            path=absolute,
            remediation="repair or reinstall the trusted executable and retry",
        )
    return absolute


def trusted_windows_powershell(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve Windows PowerShell from SystemRoot without PATH fallback."""
    source = os.environ if environ is None else environ
    system_root = source.get("SystemRoot") or source.get("SYSTEMROOT")
    if not system_root:
        raise UsageError(
            "the trusted Windows PowerShell location could not be determined",
            remediation="restore SystemRoot and retry",
        )
    powershell = (
        Path(system_root)
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    )
    return safe_regular_windows_file(
        powershell,
        label="trusted Windows PowerShell executable",
    )
