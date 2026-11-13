from importlib import import_module
from pathlib import Path

import pytest
from PIL import Image, ImageSequence

from pixel_scenes import parse_scene, render

render_py = import_module("pixel_scenes.render")
from pixel_scenes.errors import OutputExistsError, RenderError
from test_step_process import process_data


def test_render_writes_png_and_accessibility_text(
    tmp_path, concept_data
):
    output = tmp_path / "card.png"

    result = render(parse_scene(concept_data), output)

    assert Image.open(output).size == (960, 540)
    assert result.output_path == output
    assert result.media_type == "image/png"
    assert result.frame_count == 1
    assert result.accessibility_path == output.with_suffix(".txt")
    assert "Gradient descent" in output.with_suffix(".txt").read_text(
        encoding="utf-8"
    )


def test_render_protects_existing_output(tmp_path, concept_data):
    output = tmp_path / "card.png"
    output.write_bytes(b"keep")

    with pytest.raises(OutputExistsError):
        render(parse_scene(concept_data), output)

    assert output.read_bytes() == b"keep"


def test_render_protects_existing_accessibility_file(
    tmp_path, concept_data
):
    output = tmp_path / "card.png"
    description = tmp_path / "card.txt"
    description.write_text("keep", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        render(parse_scene(concept_data), output)

    assert not output.exists()
    assert description.read_text(encoding="utf-8") == "keep"


def test_failed_render_does_not_leave_partial_output(
    tmp_path, concept_data, monkeypatch
):
    output = tmp_path / "card.png"

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(Image.Image, "save", fail)

    with pytest.raises(OSError, match="disk failure"):
        render(parse_scene(concept_data), output)

    assert not output.exists()


def test_render_writes_deterministic_gif(tmp_path):
    output = tmp_path / "process.gif"

    result = render(parse_scene(process_data()), output)

    with Image.open(output) as image:
        frames = list(ImageSequence.Iterator(image))
        assert len(frames) == 8
        assert image.size == (960, 540)
    assert result.media_type == "image/gif"
    assert result.frame_count == 8
    assert result.duration_seconds == 2


def test_render_dispatches_mp4_through_encode_mp4(tmp_path, monkeypatch):
    output = tmp_path / "process.mp4"
    calls = []

    def fake_encode(frames, destination, *, fps, ffmpeg_path=None):
        calls.append((len(frames), destination, fps, ffmpeg_path))
        destination.write_bytes(b"encoded-mp4")

    monkeypatch.setattr(render_py, "encode_mp4", fake_encode)

    result = render(parse_scene(process_data()), output, ffmpeg_path=tmp_path / "ffmpeg.exe")

    assert len(calls) == 1
    frame_count, destination, fps, ffmpeg_path = calls[0]
    assert frame_count == 8
    assert destination.suffix == ".mp4"
    assert fps == 4
    assert ffmpeg_path == tmp_path / "ffmpeg.exe"
    assert output.read_bytes() == b"encoded-mp4"
    assert result.media_type == "video/mp4"
    assert result.frame_count == 8
    assert result.duration_seconds == 2


def test_failed_mp4_render_does_not_leave_partial_output(
    tmp_path, concept_data, monkeypatch
):
    output = tmp_path / "card.mp4"

    def fail(*args, **kwargs):
        raise RenderError("FFmpeg could not encode MP4: fail")

    monkeypatch.setattr(render_py, "encode_mp4", fail)

    with pytest.raises(RenderError, match="FFmpeg could not encode MP4"):
        render(parse_scene(concept_data), output)

    assert not output.exists()


def test_accessibility_write_uses_atomic_replace(tmp_path, concept_data):
    output = tmp_path / "card.png"
    render(parse_scene(concept_data), output)
    text_path = output.with_suffix(".txt")
    assert text_path.exists()
    assert text_path.stat().st_size > 0
    stale_temp = text_path.with_name(f".{text_path.name}.tmp")
    assert not stale_temp.exists()
