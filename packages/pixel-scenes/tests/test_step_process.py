import pytest

from pixel_scenes import parse_scene
from pixel_scenes.animation import frame_progress
from pixel_scenes.drawing import PixelSurface
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.step_process import (
    fit_label_lines,
    render_step_process,
    revealed_step_count,
    visible_step_details,
)


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


def test_revealed_step_count_exposes_full_sequence_at_progress_one():
    scene = parse_scene(process_data())
    steps = scene.content["steps"]

    assert revealed_step_count(len(steps), 1.0) == len(steps)
    assert visible_step_details(steps, 1.0) == [
        step["detail"] for step in steps
    ]


def test_six_max_length_labels_wrap_inside_columns():
    data = process_data()
    labels = [f"Stage-{index:02d}-abcdefghijklmnopqrst" for index in range(6)]
    data["content"]["steps"] = [
        {"label": label, "detail": f"Detail line for step {index}."}
        for index, label in enumerate(labels)
    ]
    scene = parse_scene(data)
    surface = PixelSurface(scene.canvas)
    column_width = max(4, (surface.image.size[0] - 36) // 6)
    label_width = max(8, column_width - 8)
    label_font = surface.font("label")

    wrapped_labels = [
        fit_label_lines(surface, label, label_width, font=label_font)
        for label in labels
    ]

    assert all(
        "".join(lines).replace(" ", "") == label.replace(" ", "")
        for label, lines in zip(labels, wrapped_labels, strict=True)
    )
    assert all(
        surface.text_width(line, label_font) <= label_width for lines in wrapped_labels for line in lines
    )
    render_step_process(scene, progress=1.0)


def test_unbroken_label_wraps_by_character_within_column():
    from pixel_scenes.model import Canvas

    canvas = Canvas(width=960, height=540)
    surface = PixelSurface(canvas)
    label_font = surface.font("label")
    label = "X" * 32
    label_width = 24

    lines = fit_label_lines(surface, label, label_width, font=label_font)

    assert "".join(lines) == label
    assert len(lines) > 1
    assert all(surface.text_width(line, label_font) <= label_width for line in lines)


def test_step_process_accepts_two_through_six_steps():
    data = process_data()
    data["content"]["steps"] = data["content"]["steps"][:1]

    with pytest.raises(SceneValidationError, match="2 to 6"):
        parse_scene(data)
