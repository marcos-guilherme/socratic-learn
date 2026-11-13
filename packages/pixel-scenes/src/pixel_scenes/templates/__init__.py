from __future__ import annotations

from collections.abc import Callable

from PIL import Image

from ..model import Scene
from . import comparison, concept_card, step_process

Validator = Callable[[Scene], None]
Renderer = Callable[[Scene, float], Image.Image]

VALIDATORS: dict[str, Validator] = {
    "concept-card": concept_card.validate,
    "step-process": step_process.validate,
    "comparison": comparison.validate,
}
RENDERERS: dict[str, Renderer] = {
    "concept-card": concept_card.render_concept_card,
    "step-process": step_process.render_step_process,
    "comparison": comparison.render_comparison,
}


def validate_template_content(scene: Scene) -> None:
    VALIDATORS[scene.template](scene)


def render_frame(scene: Scene, progress: float) -> Image.Image:
    return RENDERERS[scene.template](scene, progress)
