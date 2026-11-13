from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from .errors import MissingDependencyError, RenderError


def resolve_ffmpeg(explicit: str | Path | None = None) -> Path:
    candidate = Path(explicit) if explicit is not None else None
    if candidate is None:
        discovered = shutil.which("ffmpeg")
        if discovered is None:
            raise MissingDependencyError(
                "FFmpeg is required for MP4 output. Install it or pass ffmpeg_path."
            )
        candidate = Path(discovered)
    if not candidate.is_file():
        raise MissingDependencyError(
            f"FFmpeg executable was not found: {candidate}"
        )
    return candidate


def encode_timeout_seconds(frame_count: int, fps: int) -> float:
    frames = max(frame_count, 1)
    rate = max(fps, 1)
    duration = frames / rate
    return min(600.0, max(30.0, duration * 8.0 + frames * 2.0))


def _verify_encoded_output(destination: Path) -> None:
    if not destination.is_file():
        raise RenderError(
            "FFmpeg reported success but the output file is missing"
        )
    if destination.stat().st_size == 0:
        raise RenderError(
            "FFmpeg reported success but the output file is empty"
        )


def encode_mp4(
    frames: Sequence[Image.Image],
    destination: Path,
    *,
    fps: int,
    ffmpeg_path: str | Path | None = None,
) -> None:
    executable = resolve_ffmpeg(ffmpeg_path)
    timeout = encode_timeout_seconds(len(frames), fps)
    with tempfile.TemporaryDirectory(prefix="pixel-scenes-") as directory:
        frame_dir = Path(directory)
        for index, frame in enumerate(frames):
            frame.save(frame_dir / f"frame-{index:04d}.png", format="PNG")
        arguments = [
            str(executable),
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        try:
            result = subprocess.run(
                arguments,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderError(
                f"FFmpeg timed out after {exc.timeout:.0f} seconds"
            ) from exc
        if result.returncode != 0:
            lines = [line for line in result.stderr.splitlines() if line.strip()]
            diagnostic = lines[-1] if lines else "unknown FFmpeg error"
            raise RenderError(f"FFmpeg could not encode MP4: {diagnostic}")
    _verify_encoded_output(destination)
