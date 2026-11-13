from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .errors import SceneValidationError
from .model import Accessibility, Animation, Canvas, Scene

TOP_LEVEL_FIELDS = {
    "schema_version",
    "template",
    "theme",
    "canvas",
    "content",
    "animation",
    "accessibility",
    "seed",
}
TEMPLATES = {"concept-card", "step-process", "comparison"}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SceneValidationError(f"{field} must be an object")
    return value


def _integer(value: object, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SceneValidationError(f"{field} must be an integer")
    if not low <= value <= high:
        raise SceneValidationError(
            f"{field} must be between {low} and {high}"
        )
    return value


def _number(
    value: object, field: str, low: float, high: float
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SceneValidationError(f"{field} must be a number")
    result = float(value)
    if not low <= result <= high:
        raise SceneValidationError(
            f"{field} must be between {low:g} and {high:g}"
        )
    return result


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SceneValidationError(f"{field} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise SceneValidationError(
            f"{field} must contain at most {maximum} characters"
        )
    return result


def parse_scene(data: Mapping[str, object]) -> Scene:
    unknown = sorted(set(data) - TOP_LEVEL_FIELDS)
    if unknown:
        raise SceneValidationError(f"unknown field: {unknown[0]}")

    version = data.get("schema_version")
    if version != "1":
        raise SceneValidationError("schema_version must be '1'")

    template = data.get("template")
    if template not in TEMPLATES:
        names = ", ".join(sorted(TEMPLATES))
        raise SceneValidationError(f"template must be one of: {names}")

    theme = data.get("theme", "cozy-classroom")
    if theme != "cozy-classroom":
        raise SceneValidationError("theme must be 'cozy-classroom'")

    canvas_data = _mapping(data.get("canvas"), "canvas")
    canvas = Canvas(
        width=_integer(canvas_data.get("width"), "canvas.width", 160, 1920),
        height=_integer(
            canvas_data.get("height"), "canvas.height", 90, 1080
        ),
    )

    animation_data = _mapping(
        data.get("animation", {"duration_seconds": 1, "fps": 1}),
        "animation",
    )
    animation = Animation(
        duration_seconds=_number(
            animation_data.get("duration_seconds", 1),
            "animation.duration_seconds",
            0.1,
            15,
        ),
        fps=_integer(
            animation_data.get("fps", 1), "animation.fps", 1, 30
        ),
    )
    if animation.frame_count > 450:
        raise SceneValidationError(
            "animation must contain at most 450 frames"
        )

    access_data = _mapping(data.get("accessibility"), "accessibility")
    accessibility = Accessibility(
        description=_text(
            access_data.get("description"),
            "accessibility.description",
            1000,
        )
    )
    content = _mapping(data.get("content"), "content")
    seed = _integer(data.get("seed", 0), "seed", 0, 2_147_483_647)

    scene = Scene(
        schema_version="1",
        template=str(template),
        theme=str(theme),
        canvas=canvas,
        content=Scene.frozen_content(content),
        animation=animation,
        accessibility=accessibility,
        seed=seed,
    )
    validate_scene(scene)
    return scene


def validate_scene(scene: Scene) -> None:
    from .templates import validate_template_content

    validate_template_content(scene)


def load_scene(path: str | Path) -> Scene:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SceneValidationError(
            f"could not read scene JSON: {exc}"
        ) from exc
    return parse_scene(_mapping(value, "scene"))
