import pytest

from pixel_scenes import parse_scene
from pixel_scenes.drawing import PixelSurface
from pixel_scenes.errors import LayoutError, SceneValidationError
from pixel_scenes.templates.comparison import (
    POINTS_BOTTOM_MARGIN,
    comparison_content_bottom,
    render_comparison,
    revealed_point_count,
    visible_comparison_points,
)


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


def four_point_data():
    data = comparison_data()
    data["content"]["points"] = [
        {"label": "One", "left": "Alpha line", "right": "Beta line"},
        {"label": "Two", "left": "Gamma line", "right": "Delta line"},
        {"label": "Three", "left": "Epsilon", "right": "Zeta note"},
        {"label": "Four", "left": "Eta pair", "right": "Theta pair"},
    ]
    return data


def max_schema_data():
    data = four_point_data()
    data["content"]["left"]["description"] = (
        "Identity traits and permanent qualities described with concise wording"
    )
    data["content"]["right"]["description"] = (
        "Temporary states locations feelings and conditions that can change quickly"
    )
    long_line = "word " * 16  # 80 characters with spaces
    data["content"]["points"] = [
        {
            "label": f"Row-{index}-label",
            "left": long_line.strip(),
            "right": long_line.strip(),
        }
        for index in range(4)
    ]
    return data


def test_comparison_renders_both_labeled_sides():
    scene = parse_scene(comparison_data())

    assert render_comparison(scene, 1.0).size == (960, 540)


def test_comparison_requires_one_through_four_points():
    data = comparison_data()
    data["content"]["points"] = []

    with pytest.raises(SceneValidationError, match="1 to 4"):
        parse_scene(data)


def test_revealed_point_count_exposes_full_sequence_at_progress_one():
    scene = parse_scene(four_point_data())
    points = scene.content["points"]

    assert revealed_point_count(len(points), 1.0) == len(points)
    assert visible_comparison_points(points, 1.0) == points


def test_four_concise_points_stay_inside_panel():
    scene = parse_scene(four_point_data())
    surface = PixelSurface(scene.canvas)
    _, height = surface.image.size

    bottom = comparison_content_bottom(surface, scene, progress=1.0)

    assert bottom <= height - POINTS_BOTTOM_MARGIN
    render_comparison(scene, progress=1.0)


def test_partial_progress_reveals_a_subset_of_points():
    scene = parse_scene(four_point_data())
    points = scene.content["points"]

    assert revealed_point_count(len(points), 0.0) == 1
    assert revealed_point_count(len(points), 0.24) == 1
    assert revealed_point_count(len(points), 0.5) == 2
    assert revealed_point_count(len(points), 0.75) == 3
    assert revealed_point_count(len(points), 1.0) == 4
    assert len(visible_comparison_points(points, 0.5)) == 2


def test_wrapped_side_descriptions_stay_inside_columns():
    scene = parse_scene(max_schema_data())
    surface = PixelSurface(scene.canvas)
    from pixel_scenes.templates.comparison import (
        comparison_column_metrics,
        fit_comparison_lines,
    )

    metrics = comparison_column_metrics(surface)
    label_font = surface.font("label")

    for side_name in ("left", "right"):
        description = str(scene.content[side_name]["description"])
        lines = fit_comparison_lines(
            surface,
            description,
            metrics.column_width - 16,
            font=label_font,
        )

        assert "".join(lines).replace(" ", "") == description.replace(" ", "")
        assert all(
            surface.text_width(line, label_font) <= metrics.column_width - 16
            for line in lines
        )


def test_max_schema_content_fits_or_raises_layout_error():
    scene = parse_scene(max_schema_data())

    try:
        image = render_comparison(scene, progress=1.0)
    except LayoutError as exc:
        message = str(exc).lower()
        assert "fit" in message or "panel" in message or "wide" in message
        return

    assert image.size == (960, 540)
    surface = PixelSurface(scene.canvas)
    assert (
        comparison_content_bottom(surface, scene, 1.0)
        <= surface.image.size[1] - POINTS_BOTTOM_MARGIN
    )
