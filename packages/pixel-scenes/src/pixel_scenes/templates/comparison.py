from __future__ import annotations

from collections.abc import Mapping, Sequence

from PIL import Image

from ..drawing import PixelSurface
from ..errors import SceneValidationError
from ..model import Scene

FIELDS = {"title", "left", "right", "points"}
SIDE_FIELDS = {"heading", "description"}
POINT_FIELDS = {"label", "left", "right"}


def _short_text(value: object, field: str, maximum: int) -> None:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise SceneValidationError(
            f"{field} must contain 1 to {maximum} characters"
        )


def validate(scene: Scene) -> None:
    unknown = sorted(set(scene.content) - FIELDS)
    if unknown:
        raise SceneValidationError(f"unknown field: content.{unknown[0]}")
    _short_text(scene.content.get("title"), "content.title", 80)
    for side_name in ("left", "right"):
        side = scene.content.get(side_name)
        if not isinstance(side, Mapping):
            raise SceneValidationError(f"content.{side_name} must be an object")
        extra = sorted(set(side) - SIDE_FIELDS)
        if extra:
            raise SceneValidationError(
                f"unknown field: content.{side_name}.{extra[0]}"
            )
        _short_text(side.get("heading"), f"content.{side_name}.heading", 32)
        _short_text(
            side.get("description"),
            f"content.{side_name}.description",
            120,
        )
    points = scene.content.get("points")
    if not isinstance(points, Sequence) or isinstance(points, (str, bytes)):
        raise SceneValidationError("content.points must be a list")
    if not 1 <= len(points) <= 4:
        raise SceneValidationError("content.points must contain 1 to 4 points")
    for index, point in enumerate(points):
        if not isinstance(point, Mapping):
            raise SceneValidationError(f"content.points[{index}] must be an object")
        extra = sorted(set(point) - POINT_FIELDS)
        if extra:
            raise SceneValidationError(
                f"unknown field: content.points[{index}].{extra[0]}"
            )
        _short_text(point.get("label"), f"content.points[{index}].label", 24)
        _short_text(point.get("left"), f"content.points[{index}].left", 80)
        _short_text(point.get("right"), f"content.points[{index}].right", 80)


def render_comparison(scene: Scene, progress: float) -> Image.Image:
    surface = PixelSurface(scene.canvas)
    width, height = surface.image.size
    surface.panel((8, 8, width - 9, height - 9))
    surface.draw.text(
        (18, 17),
        str(scene.content["title"]),
        font=surface.font("title"),
        fill=surface.theme.ink,
    )
    middle = width // 2
    surface.draw.line(
        [(middle, 48), (middle, height - 20)],
        fill=surface.theme.border,
        width=2,
    )
    sides = (
        ("left", 18, surface.theme.blue),
        ("right", middle + 12, surface.theme.coral),
    )
    column_width = middle - 36
    for side_name, x, color in sides:
        side = dict(scene.content[side_name])
        surface.draw.rectangle(
            (x, 48, x + column_width, 76), fill=color
        )
        surface.draw.text(
            (x + 8, 54),
            str(side["heading"]),
            font=surface.font("heading"),
            fill=surface.theme.ink,
        )
        surface.draw.text(
            (x + 8, 80),
            str(side["description"]),
            font=surface.font("label"),
            fill=surface.theme.ink,
        )
    points = list(scene.content["points"])
    visible = max(1, round(progress * len(points)))
    for index, raw_point in enumerate(points[:visible]):
        point = dict(raw_point)
        y = 112 + index * 34
        surface.draw.text(
            (middle - 28, y),
            str(point["label"]),
            font=surface.font("label"),
            fill=surface.theme.muted_ink,
        )
        surface.draw.text(
            (20, y + 12),
            str(point["left"]),
            font=surface.font("body"),
            fill=surface.theme.ink,
        )
        surface.draw.text(
            (middle + 14, y + 12),
            str(point["right"]),
            font=surface.font("body"),
            fill=surface.theme.ink,
        )
    return surface.finish()
