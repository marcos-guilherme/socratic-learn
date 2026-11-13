import pytest

from pixel_scenes import parse_scene
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.comparison import render_comparison


def comparison_data():
    return {
        "schema_version": "1",
        "template": "comparison",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "Ser and estar",
            "left": {"heading": "Ser", "description": "Identity or defining traits"},
            "right": {"heading": "Estar", "description": "State or location"},
            "points": [
                {"label": "Nature", "left": "Soy amable", "right": "Estoy cansado"},
                {"label": "Place", "left": "Es de Brasil", "right": "Está en casa"},
            ],
        },
        "animation": {"duration_seconds": 2, "fps": 4},
        "accessibility": {
            "description": "Two labeled columns compare uses of ser and estar."
        },
        "seed": 0,
    }


def test_comparison_renders_both_labeled_sides():
    scene = parse_scene(comparison_data())

    assert render_comparison(scene, 1.0).size == (960, 540)


def test_comparison_requires_one_through_four_points():
    data = comparison_data()
    data["content"]["points"] = []

    with pytest.raises(SceneValidationError, match="1 to 4"):
        parse_scene(data)
