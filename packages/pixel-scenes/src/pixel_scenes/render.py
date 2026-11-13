from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .accessibility import write_accessibility
from .errors import OutputExistsError, RenderError
from .model import RenderResult, Scene
from .templates import render_frame

MEDIA_TYPES = {
    ".png": "image/png",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
}


def _protect_output(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise OutputExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def render(
    scene: Scene,
    output: str | Path,
    *,
    overwrite: bool = False,
    accessibility: bool = True,
) -> RenderResult:
    destination = Path(output)
    suffix = destination.suffix.lower()
    if suffix != ".png":
        raise RenderError("this build currently supports PNG output")
    _protect_output(destination, overwrite)
    access_path = destination.with_suffix(".txt") if accessibility else None
    if access_path is not None:
        _protect_output(access_path, overwrite)
    frame = render_frame(scene, 1.0)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=destination.suffix,
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        frame.save(temporary, format="PNG")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    if access_path is not None:
        write_accessibility(scene, access_path)
    return RenderResult(
        output_path=destination,
        media_type=MEDIA_TYPES[suffix],
        width=scene.canvas.width,
        height=scene.canvas.height,
        frame_count=1,
        duration_seconds=0.0,
        accessibility_path=access_path,
    )
