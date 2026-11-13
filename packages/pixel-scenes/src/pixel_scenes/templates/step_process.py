from PIL import Image

from ..errors import SceneValidationError
from ..model import Scene


def validate(scene: Scene) -> None:
    raise SceneValidationError(
        f"template {scene.template} is not implemented in this build"
    )


def render_step_process(scene: Scene, progress: float) -> Image.Image:
    raise SceneValidationError("step-process is not implemented")
