class PixelScenesError(Exception):
    """Base error for expected Pixel Scenes failures."""


class SceneValidationError(PixelScenesError):
    """Scene data does not satisfy the public schema."""


class LayoutError(PixelScenesError):
    """Validated content cannot fit the requested canvas."""


class MissingDependencyError(PixelScenesError):
    """An optional output dependency is unavailable."""


class RenderError(PixelScenesError):
    """A renderer or encoder could not create the output."""


class OutputExistsError(PixelScenesError):
    """The destination exists and overwrite was not requested."""
