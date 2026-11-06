from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path, PurePosixPath

from .errors import IntegrityError

_ALLOWED = {
    "manifest.json",
    "socratic-learn.prompt.md",
    "templates/learner-profile.md",
    "templates/learning-goal.md",
    "templates/progress.md",
    "templates/session-log.md",
}


def resource_bytes(relative: str) -> bytes:
    if relative not in _ALLOWED or PurePosixPath(relative).is_absolute():
        raise ValueError(f"unsupported packaged resource: {relative}")
    packaged = files("socratic_learn").joinpath("data", *PurePosixPath(relative).parts)
    if packaged.is_file():
        return packaged.read_bytes()
    repository = Path(__file__).resolve().parents[1]
    fallback = (
        repository / "dist" / relative
        if not relative.startswith("templates/")
        else repository / relative
    )
    try:
        return fallback.read_bytes()
    except OSError as error:
        raise IntegrityError(
            "packaged resource is unavailable",
            path=relative,
            remediation="reinstall socratic-learn",
        ) from error


@contextmanager
def packaged_distribution_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="socratic-learn-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        dist.mkdir()
        (dist / "manifest.json").write_bytes(resource_bytes("manifest.json"))
        (dist / "socratic-learn.prompt.md").write_bytes(
            resource_bytes("socratic-learn.prompt.md")
        )
        yield root
