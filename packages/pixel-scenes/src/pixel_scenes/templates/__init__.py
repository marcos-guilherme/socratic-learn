from __future__ import annotations

from ..errors import SceneValidationError
from ..model import Scene


def validate_template_content(scene: Scene) -> None:
    title = scene.content.get("title")
    if not isinstance(title, str) or not title.strip():
        raise SceneValidationError("content.title must be non-empty text")
    if len(title.strip()) > 80:
        raise SceneValidationError(
            "content.title must contain at most 80 characters"
        )
