from __future__ import annotations

from PIL import Image

from ..drawing import PixelSurface
from ..errors import LayoutError, SceneValidationError
from ..model import Scene

FIELDS = {"title", "summary", "key_fact"}

TITLE_TOP = 18
SUMMARY_TOP = 47
TITLE_LINE_HEIGHT = 14
SUMMARY_LINE_HEIGHT = 14
SUMMARY_MAX_LINES = 4


def validate(scene: Scene) -> None:
    unknown = sorted(set(scene.content) - FIELDS)
    if unknown:
        raise SceneValidationError(f"unknown field: content.{unknown[0]}")
    for name, maximum in (("title", 80), ("summary", 240)):
        value = scene.content.get(name)
        if not isinstance(value, str) or not value.strip():
            raise SceneValidationError(
                f"content.{name} must be non-empty text"
            )
        if len(value.strip()) > maximum:
            raise SceneValidationError(
                f"content.{name} must contain at most {maximum} characters"
            )
    fact = scene.content.get("key_fact")
    if fact is not None and (
        not isinstance(fact, str) or not fact.strip() or len(fact) > 160
    ):
        raise SceneValidationError(
            "content.key_fact must contain 1 to 160 characters"
        )


def render_concept_card(scene: Scene, progress: float) -> Image.Image:
    surface = PixelSurface(scene.canvas)
    width, height = surface.image.size
    surface.panel((8, 8, width - 9, height - 9))
    title_font = surface.font("title")
    body_font = surface.font("body")
    label_font = surface.font("label")
    panel_text_width = width - 36
    title_lines = surface.fit_text_lines(
        str(scene.content["title"]),
        panel_text_width,
        font=title_font,
        empty_message="title text is empty",
        wide_message="title is too wide for the panel",
    )
    max_title_lines = max(
        1, (SUMMARY_TOP - TITLE_TOP) // TITLE_LINE_HEIGHT
    )
    if len(title_lines) > max_title_lines:
        raise LayoutError("title does not fit the panel")
    for line_index, line in enumerate(title_lines):
        surface.draw.text(
            (18, TITLE_TOP + line_index * TITLE_LINE_HEIGHT),
            line,
            font=title_font,
            fill=surface.theme.ink,
        )

    hill = [
        (20, height - 42),
        (width // 3, height - 66),
        (width // 2, height - 36),
        (width - 22, height - 74),
    ]
    surface.draw.line(hill, fill=surface.theme.green, width=4)
    travel = max(0.0, min(1.0, progress))
    marker_x = int(26 + travel * (width - 60))
    marker_y = height - 82 + int(travel * 35)
    surface.dots([(marker_x, marker_y)], fill=surface.theme.coral, size=7)

    summary = str(scene.content["summary"])
    summary_lines = surface.fit_text_lines(
        summary,
        max_width=width - 42,
        font=body_font,
        empty_message="summary text is empty",
        wide_message="summary is too wide for the panel",
    )
    if len(summary_lines) > SUMMARY_MAX_LINES:
        raise LayoutError("summary does not fit the panel")
    y = SUMMARY_TOP
    for line in summary_lines:
        surface.draw.text(
            (18, y), line, font=body_font, fill=surface.theme.ink
        )
        y += SUMMARY_LINE_HEIGHT

    fact = scene.content.get("key_fact")
    if fact:
        surface.draw.rectangle(
            (18, height - 30, width - 18, height - 17),
            fill=surface.theme.gold,
        )
        surface.draw.text(
            (22, height - 28),
            str(fact),
            font=label_font,
            fill=surface.theme.ink,
        )
    return surface.finish()
