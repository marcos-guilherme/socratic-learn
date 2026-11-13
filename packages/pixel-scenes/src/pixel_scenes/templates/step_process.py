from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image, ImageFont

from ..drawing import PixelSurface
from ..errors import LayoutError, SceneValidationError
from ..model import Scene

FIELDS = {"title", "steps"}
STEP_FIELDS = {"label", "detail"}

LABEL_LINE_HEIGHT = 10
DETAIL_LINE_HEIGHT = 10
DETAIL_GAP = 4


def revealed_step_count(step_count: int, progress: float) -> int:
    if step_count <= 0:
        return 0
    clamped = max(0.0, min(1.0, progress))
    return max(1, min(step_count, round(clamped * step_count)))


def visible_step_details(steps: Sequence[object], progress: float) -> list[str]:
    count = revealed_step_count(len(steps), progress)
    return [str(steps[index]["detail"]) for index in range(count)]


def _wrap_characters(
    surface: PixelSurface,
    text: str,
    max_width: int,
    font: ImageFont.ImageFont,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = f"{current}{character}"
        if current and surface.text_width(candidate, font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    if not lines:
        raise LayoutError("label text is empty")
    overflow = [
        line
        for line in lines
        if surface.text_width(line, font) > max_width
    ]
    if overflow:
        raise LayoutError("label text is too wide for its column")
    return lines


def fit_label_lines(
    surface: PixelSurface,
    label: str,
    max_width: int,
    *,
    font: ImageFont.ImageFont,
) -> list[str]:
    text = label.strip()
    if not text:
        raise LayoutError("label text is empty")
    try:
        lines = surface.wrap(text, max_width=max_width, font=font)
    except LayoutError:
        lines = _wrap_characters(surface, text, max_width, font)
    overflow = [
        line for line in lines if surface.text_width(line, font) > max_width
    ]
    if overflow:
        return _wrap_characters(surface, text, max_width, font)
    return lines


def validate(scene: Scene) -> None:
    unknown = sorted(set(scene.content) - FIELDS)
    if unknown:
        raise SceneValidationError(f"unknown field: content.{unknown[0]}")
    title = scene.content.get("title")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 80:
        raise SceneValidationError("content.title must contain 1 to 80 characters")
    steps = scene.content.get("steps")
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise SceneValidationError("content.steps must be a list")
    if not 2 <= len(steps) <= 6:
        raise SceneValidationError("content.steps must contain 2 to 6 steps")
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise SceneValidationError(f"content.steps[{index}] must be an object")
        unknown_step = sorted(set(step) - STEP_FIELDS)
        if unknown_step:
            raise SceneValidationError(
                f"unknown field: content.steps[{index}].{unknown_step[0]}"
            )
        for field, maximum in (("label", 32), ("detail", 120)):
            value = step.get(field)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                raise SceneValidationError(
                    f"content.steps[{index}].{field} must contain "
                    f"1 to {maximum} characters"
                )


def render_step_process(scene: Scene, progress: float) -> Image.Image:
    surface = PixelSurface(scene.canvas)
    width, height = surface.image.size
    surface.panel((8, 8, width - 9, height - 9))
    surface.draw.text(
        (18, 17),
        str(scene.content["title"]),
        font=surface.font("title"),
        fill=surface.theme.ink,
    )
    steps = list(scene.content["steps"])
    revealed = revealed_step_count(len(steps), progress)
    gap = max(4, (width - 36) // len(steps))
    baseline = height // 2
    label_font = surface.font("label")
    label_column_width = max(8, gap - 8)
    track_y = height - 22
    for index, raw_step in enumerate(steps):
        step = dict(raw_step)
        x = 22 + index * gap
        active = index < revealed
        color = surface.theme.coral if active else surface.theme.muted_ink
        surface.dots([(x, baseline)], fill=color, size=7)
        if index + 1 < len(steps):
            surface.arrow((x + 8, baseline + 3), (x + gap - 4, baseline + 3))
        label_lines = fit_label_lines(
            surface,
            str(step["label"]),
            label_column_width,
            font=label_font,
        )
        for line_index, line in enumerate(label_lines):
            surface.draw.text(
                (x - 4, baseline + 14 + line_index * LABEL_LINE_HEIGHT),
                line,
                font=label_font,
                fill=color,
            )
        if active:
            detail_top = (
                baseline + 14 + len(label_lines) * LABEL_LINE_HEIGHT + DETAIL_GAP
            )
            available_height = track_y - detail_top - 8
            max_detail_lines = max(
                0, available_height // DETAIL_LINE_HEIGHT
            )
            detail_lines = surface.wrap(
                str(step["detail"]),
                max_width=label_column_width,
                font=label_font,
            )
            for line_index, line in enumerate(detail_lines[:max_detail_lines]):
                surface.draw.text(
                    (x - 4, detail_top + line_index * DETAIL_LINE_HEIGHT),
                    line,
                    font=label_font,
                    fill=surface.theme.ink,
                )
    track_left, track_right = 22, width - 22
    surface.draw.line(
        [(track_left, track_y), (track_right, track_y)],
        fill=surface.theme.muted_ink,
        width=2,
    )
    marker_x = track_left + round(
        max(0.0, min(1.0, progress)) * (track_right - track_left - 5)
    )
    surface.dots(
        [(marker_x, track_y - 2)], fill=surface.theme.coral, size=5
    )
    return surface.finish()
