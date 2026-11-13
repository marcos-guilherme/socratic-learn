from PIL import Image

from ..errors import SceneValidationError
from ..model import Scene


def validate(scene: Scene) -> None:
    raise SceneValidationError(
        f"template {scene.template} is not implemented in this build"
    )


def render_comparison(scene: Scene, progress: float) -> Image.Image:
    raise SceneValidationError("comparison is not implemented")
