import pytest

from pixel_scenes import parse_scene
from pixel_scenes.animation import frame_progress
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.step_process import render_step_process


def process_data():
    return {
        "schema_version": "1",
        "template": "step-process",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "How a seed begins to grow",
            "steps": [
                {"label": "Water", "detail": "The seed absorbs water."},
                {"label": "Open", "detail": "The shell opens."},
                {"label": "Grow", "detail": "The first root emerges."},
            ],
        },
        "animation": {"duration_seconds": 2, "fps": 4},
        "accessibility": {
            "description": "Three labeled stages show a seed beginning to grow."
        },
        "seed": 7,
    }


def test_frame_progress_includes_both_endpoints():
    assert [frame_progress(i, 3) for i in range(3)] == [0.0, 0.5, 1.0]


def test_step_process_renders_static_summary():
    scene = parse_scene(process_data())

    image = render_step_process(scene, progress=1.0)

    assert image.size == (960, 540)


def test_step_process_accepts_two_through_six_steps():
    data = process_data()
    data["content"]["steps"] = data["content"]["steps"][:1]

    with pytest.raises(SceneValidationError, match="2 to 6"):
        parse_scene(data)
