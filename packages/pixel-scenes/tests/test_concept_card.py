import pytest
from PIL import Image

from pixel_scenes import parse_scene
from pixel_scenes.drawing import PixelSurface
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.concept_card import render_concept_card
from pixel_scenes.model import Canvas
from pixel_scenes.theme import COZY_CLASSROOM


def test_pixel_surface_uses_integer_logical_canvas():
    surface = PixelSurface(Canvas(960, 540), scale=3)

    assert surface.image.size == (320, 180)
    assert surface.finish().size == (960, 540)


def test_wrapped_text_stays_inside_requested_width():
    surface = PixelSurface(Canvas(480, 270), scale=3)

    lines = surface.wrap(
        "A careful step can reduce the current error.",
        max_width=110,
        font=surface.font("body"),
    )

    assert len(lines) >= 2
    assert all(
        surface.text_width(line, surface.font("body")) <= 110
        for line in lines
    )


def test_finish_uses_nearest_neighbor_scaling():
    surface = PixelSurface(Canvas(160, 90), scale=2)
    surface.image.putpixel((1, 1), COZY_CLASSROOM.ink)

    result = surface.finish()

    assert isinstance(result, Image.Image)
    assert result.getpixel((2, 2)) == COZY_CLASSROOM.ink
    assert result.getpixel((3, 3)) == COZY_CLASSROOM.ink


def test_dots_accepts_builtin_theme_color():
    surface = PixelSurface(Canvas(40, 40), scale=1)

    surface.dots([(5, 5)], fill=COZY_CLASSROOM.coral, size=2)

    assert surface.image.getpixel((5, 5)) == COZY_CLASSROOM.coral
    assert surface.image.getpixel((6, 6)) == COZY_CLASSROOM.coral


def test_concept_card_renders_requested_size(concept_data):
    scene = parse_scene(concept_data)

    image = render_concept_card(scene, progress=1.0)

    assert image.size == (960, 540)
    assert image.mode == "RGB"


def test_concept_card_rejects_unknown_content(concept_data):
    concept_data["content"]["html"] = "<iframe>"

    with pytest.raises(SceneValidationError, match="content.html"):
        parse_scene(concept_data)
