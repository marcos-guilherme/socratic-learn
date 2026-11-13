from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .accessibility import write_accessibility
from .animation import frame_progress
from .errors import OutputExistsError, RenderError
from .model import RenderResult, Scene
from .ffmpeg import encode_mp4
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


def _frames(scene: Scene) -> list:
    return [
        render_frame(scene, frame_progress(index, scene.animation.frame_count))
        for index in range(scene.animation.frame_count)
    ]


def _save_gif(scene: Scene, temporary: Path) -> int:
    frames = _frames(scene)
    duration_ms = round(1000 / scene.animation.fps)
    frames[0].save(
        temporary,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return len(frames)


def render(
    scene: Scene,
    output: str | Path,
    *,
    overwrite: bool = False,
    accessibility: bool = True,
    ffmpeg_path: str | Path | None = None,
) -> RenderResult:
    destination = Path(output)
    suffix = destination.suffix.lower()
    if suffix not in (".png", ".gif", ".mp4"):
        raise RenderError("this build currently supports PNG, GIF, and MP4 output")
    _protect_output(destination, overwrite)
    access_path = destination.with_suffix(".txt") if accessibility else None
    if access_path is not None:
        _protect_output(access_path, overwrite)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=destination.suffix,
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        if suffix == ".png":
            frame = render_frame(scene, 1.0)
            frame.save(temporary, format="PNG")
            frame_count = 1
            duration_seconds = 0.0
        elif suffix == ".gif":
            frame_count = _save_gif(scene, temporary)
            duration_seconds = scene.animation.duration_seconds
        else:
            frames = _frames(scene)
            encode_mp4(
                frames,
                temporary,
                fps=scene.animation.fps,
                ffmpeg_path=ffmpeg_path,
            )
            frame_count = len(frames)
            duration_seconds = scene.animation.duration_seconds
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
        frame_count=frame_count,
        duration_seconds=duration_seconds,
        accessibility_path=access_path,
    )
