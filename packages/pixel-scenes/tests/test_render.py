from pathlib import Path

import pytest
from PIL import Image

from pixel_scenes import parse_scene, render
from pixel_scenes.errors import OutputExistsError


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
