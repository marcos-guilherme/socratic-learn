from pathlib import Path
import subprocess

import pytest
from PIL import Image

from pixel_scenes.errors import MissingDependencyError, RenderError
from pixel_scenes.ffmpeg import encode_mp4, encode_timeout_seconds, resolve_ffmpeg


def test_resolve_ffmpeg_explains_missing_dependency(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(MissingDependencyError, match="FFmpeg"):
        resolve_ffmpeg()


def test_encode_mp4_uses_argument_list_without_shell(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"binary")
    destination = tmp_path / "movie.mp4"
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        destination.write_bytes(b"video")
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    frames = [Image.new("RGB", (160, 90), "white")]

    encode_mp4(frames, destination, fps=4, ffmpeg_path=executable)

    arguments, kwargs = calls[0]
    assert isinstance(arguments, list)
    assert kwargs["shell"] is False
    assert str(executable) == arguments[0]
    assert destination.read_bytes() == b"video"


def test_encode_mp4_reports_final_ffmpeg_message(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"binary")

    def fail(arguments, **kwargs):
        return type(
            "Result",
            (),
            {"returncode": 1, "stderr": "header\ninvalid encoder"},
        )()

    monkeypatch.setattr("subprocess.run", fail)

    with pytest.raises(RenderError, match="invalid encoder"):
        encode_mp4(
            [Image.new("RGB", (160, 90))],
            tmp_path / "movie.mp4",
            fps=4,
            ffmpeg_path=executable,
        )


def test_encode_timeout_scales_with_frame_count():
    assert encode_timeout_seconds(8, fps=4) >= encode_timeout_seconds(1, fps=4)


def test_encode_mp4_timeout_becomes_render_error(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"binary")

    def slow(arguments, **kwargs):
        raise subprocess.TimeoutExpired(cmd=arguments, timeout=kwargs["timeout"])

    monkeypatch.setattr("subprocess.run", slow)

    with pytest.raises(RenderError, match="timed out"):
        encode_mp4(
            [Image.new("RGB", (160, 90))] * 8,
            tmp_path / "movie.mp4",
            fps=4,
            ffmpeg_path=executable,
        )


def test_encode_mp4_rejects_missing_output_after_success(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"binary")
    destination = tmp_path / "movie.mp4"

    def succeed(arguments, **kwargs):
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", succeed)

    with pytest.raises(RenderError, match="missing"):
        encode_mp4(
            [Image.new("RGB", (160, 90))],
            destination,
            fps=4,
            ffmpeg_path=executable,
        )


def test_encode_mp4_rejects_empty_output_after_success(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"binary")
    destination = tmp_path / "movie.mp4"

    def succeed(arguments, **kwargs):
        destination.write_bytes(b"")
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", succeed)

    with pytest.raises(RenderError, match="empty"):
        encode_mp4(
            [Image.new("RGB", (160, 90))],
            destination,
            fps=4,
            ffmpeg_path=executable,
        )
