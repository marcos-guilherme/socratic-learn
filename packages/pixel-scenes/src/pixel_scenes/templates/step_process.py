from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image

from ..drawing import PixelSurface
from ..errors import SceneValidationError
from ..model import Scene

FIELDS = {"title", "steps"}
STEP_FIELDS = {"label", "detail"}


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
    revealed = max(1, round(progress * len(steps)))
    gap = max(4, (width - 36) // len(steps))
    baseline = height // 2
    for index, raw_step in enumerate(steps):
        step = dict(raw_step)
        x = 22 + index * gap
        active = index < revealed
        color = surface.theme.coral if active else surface.theme.muted_ink
        surface.dots([(x, baseline)], fill=color, size=7)
        if index + 1 < len(steps):
            surface.arrow((x + 8, baseline + 3), (x + gap - 4, baseline + 3))
        surface.draw.text(
            (x - 4, baseline + 14),
            str(step["label"]),
            font=surface.font("label"),
            fill=color,
        )
        if active:
            detail_lines = surface.wrap(
                str(step["detail"]),
                max_width=max(40, gap - 8),
                font=surface.font("label"),
            )
            for line_index, line in enumerate(detail_lines[:3]):
                surface.draw.text(
                    (x - 4, baseline + 28 + line_index * 10),
                    line,
                    font=surface.font("label"),
                    fill=surface.theme.ink,
                )
    track_left, track_right = 22, width - 22
    track_y = height - 22
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
