from __future__ import annotations

import json

import pytest

from pixel_scenes import load_scene, parse_scene, validate_scene
from pixel_scenes.errors import SceneValidationError


def test_parse_scene_returns_immutable_model(concept_data):
    scene = parse_scene(concept_data)

    assert scene.template == "concept-card"
    assert scene.canvas.width == 960
    assert scene.animation.frame_count == 48
    assert scene.accessibility.description.startswith("A marker")

    with pytest.raises(AttributeError):
        scene.template = "comparison"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "2", "schema_version must be '1'"),
        ("template", "poster", "template must be one of"),
        ("theme", "remote-theme", "theme must be 'cozy-classroom'"),
    ],
)
def test_rejects_unsupported_top_level_values(
    concept_data, field, value, message
):
    concept_data[field] = value

    with pytest.raises(SceneValidationError, match=message):
        parse_scene(concept_data)


def test_rejects_unknown_top_level_field(concept_data):
    concept_data["script"] = "print('unsafe')"

    with pytest.raises(
        SceneValidationError, match=r"unknown field: script"
    ):
        parse_scene(concept_data)


@pytest.mark.parametrize(
    ("canvas", "message"),
    [
        ({"width": 159, "height": 540}, "canvas.width"),
        ({"width": 960, "height": 1081}, "canvas.height"),
    ],
)
def test_rejects_canvas_outside_bounds(concept_data, canvas, message):
    concept_data["canvas"] = canvas

    with pytest.raises(SceneValidationError, match=message):
        parse_scene(concept_data)


def test_rejects_excessive_animation(concept_data):
    concept_data["animation"] = {"duration_seconds": 15, "fps": 31}

    with pytest.raises(SceneValidationError, match="animation.fps"):
        parse_scene(concept_data)


def test_load_scene_reads_utf8_json(tmp_path, concept_data):
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(concept_data), encoding="utf-8")

    assert load_scene(path) == parse_scene(concept_data)


def test_validate_scene_accepts_parsed_scene(concept_data):
    validate_scene(parse_scene(concept_data))
