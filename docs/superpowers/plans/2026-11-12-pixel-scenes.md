# Pixel Scenes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independently installable Python tool that turns validated JSON scenes into clear pixel-art PNG, GIF, and MP4 explanations.

**Architecture:** A strict schema parser converts JSON into immutable models. Template renderers use a shared Pillow drawing layer and built-in Cozy Pixel Classroom theme. One render service validates input, creates frames, writes safe outputs and accessibility text, and delegates MP4 encoding to a shell-free FFmpeg adapter.

**Tech Stack:** Python 3.11+, Pillow 11 or 12, optional NumPy 2, optional FFmpeg, pytest, Hatchling.

## Global Constraints

- The project lives entirely under `packages/pixel-scenes/` and owns its packaging, source, examples, tests, and documentation.
- The `pixel_scenes` package must not import or depend on Socratic Learn.
- Distribution name: `pixel-scenes`. Import package: `pixel_scenes`. Command: `pixel-scenes`.
- Scene input is UTF-8 JSON with `schema_version` equal to `"1"`.
- The renderer never evaluates code, invokes a shell, or loads remote assets.
- Version 1 accepts only built-in themes, fonts, sprites, and template fields.
- Supported templates are `concept-card`, `step-process`, and `comparison`.
- Supported outputs are PNG, GIF, and MP4. FFmpeg is required only for MP4.
- Canvas bounds are 160 by 90 through 1920 by 1080.
- Animation duration is at most 15 seconds, frame rate is 1 through 30, and total frames are at most 450.
- Existing outputs are protected unless `overwrite=True` or `--overwrite` is supplied.
- Every normal render writes an adjacent UTF-8 `.txt` accessibility description unless disabled explicitly.
- The default theme is `cozy-classroom`.
- Static output must preserve the main meaning of an animation.
- All generated prose and documentation use natural English without em dash or en dash characters.

---

## Planned file structure

```text
packages/pixel-scenes/
├── pyproject.toml
├── README.md
├── examples/
│   ├── gradient-descent.json
│   ├── language-comparison.json
│   └── historical-process.json
├── src/pixel_scenes/
│   ├── __init__.py
│   ├── __main__.py
│   ├── accessibility.py
│   ├── cli.py
│   ├── data/
│   │   ├── __init__.py
│   │   └── examples/
│   │       ├── __init__.py
│   │       ├── concept-card.json
│   │       ├── comparison.json
│   │       └── step-process.json
│   ├── drawing.py
│   ├── errors.py
│   ├── ffmpeg.py
│   ├── model.py
│   ├── render.py
│   ├── schema.py
│   ├── theme.py
│   └── templates/
│       ├── __init__.py
│       ├── comparison.py
│       ├── concept_card.py
│       └── step_process.py
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_comparison.py
    ├── test_concept_card.py
    ├── test_ffmpeg.py
    ├── test_independence.py
    ├── test_render.py
    ├── test_schema.py
    └── test_step_process.py
```

`model.py` owns public immutable data types. `schema.py` is the only boundary
from untrusted dictionaries to those types. `drawing.py` contains reusable
pixel-safe drawing operations. Each template owns its content validation and
frame composition. `render.py` owns output safety and dispatch. `ffmpeg.py`
contains the only subprocess call.

---

### Task 1: Independent package and strict scene schema

**Files:**
- Create: `packages/pixel-scenes/pyproject.toml`
- Create: `packages/pixel-scenes/src/pixel_scenes/__init__.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/errors.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/model.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/schema.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/templates/__init__.py`
- Create: `packages/pixel-scenes/tests/conftest.py`
- Create: `packages/pixel-scenes/tests/test_schema.py`

**Interfaces:**
- Produces: `Scene`, `Canvas`, `Animation`, `Accessibility`, and `RenderResult`.
- Produces: `parse_scene(data: Mapping[str, object]) -> Scene`.
- Produces: `load_scene(path: str | Path) -> Scene`.
- Produces: `validate_scene(scene: Scene) -> None`.
- Produces: public errors rooted at `PixelScenesError`.

- [ ] **Step 1: Write schema boundary tests**

Create `tests/conftest.py`:

```python
from __future__ import annotations

import pytest


@pytest.fixture
def concept_data() -> dict[str, object]:
    return {
        "schema_version": "1",
        "template": "concept-card",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "Gradient descent",
            "summary": "Walk downhill one careful step at a time.",
            "key_fact": "Smaller loss means a better fit.",
        },
        "animation": {"duration_seconds": 4, "fps": 12},
        "accessibility": {
            "description": "A marker moves down a stepped hill."
        },
        "seed": 0,
    }
```

Create `tests/test_schema.py`:

```python
from __future__ import annotations

import json

import pytest

from pixel_scenes import load_scene, parse_scene, validate_scene
from pixel_scenes.errors import SceneValidationError


def test_parse_scene_returns_immutable_model(concept_data):
    scene = parse_scene(concept_data)

    assert scene.template == "concept-card"
    assert scene.canvas.width == 960
    assert scene.animation.frame_count == 48
    assert scene.accessibility.description.startswith("A marker")

    with pytest.raises(AttributeError):
        scene.template = "comparison"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", "2", "schema_version must be '1'"),
        ("template", "poster", "template must be one of"),
        ("theme", "remote-theme", "theme must be 'cozy-classroom'"),
    ],
)
def test_rejects_unsupported_top_level_values(
    concept_data, field, value, message
):
    concept_data[field] = value

    with pytest.raises(SceneValidationError, match=message):
        parse_scene(concept_data)


def test_rejects_unknown_top_level_field(concept_data):
    concept_data["script"] = "print('unsafe')"

    with pytest.raises(
        SceneValidationError, match=r"unknown field: script"
    ):
        parse_scene(concept_data)


@pytest.mark.parametrize(
    ("canvas", "message"),
    [
        ({"width": 159, "height": 540}, "canvas.width"),
        ({"width": 960, "height": 1081}, "canvas.height"),
    ],
)
def test_rejects_canvas_outside_bounds(concept_data, canvas, message):
    concept_data["canvas"] = canvas

    with pytest.raises(SceneValidationError, match=message):
        parse_scene(concept_data)


def test_rejects_excessive_animation(concept_data):
    concept_data["animation"] = {"duration_seconds": 15, "fps": 31}

    with pytest.raises(SceneValidationError, match="animation.fps"):
        parse_scene(concept_data)


def test_load_scene_reads_utf8_json(tmp_path, concept_data):
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(concept_data), encoding="utf-8")

    assert load_scene(path) == parse_scene(concept_data)


def test_validate_scene_accepts_parsed_scene(concept_data):
    validate_scene(parse_scene(concept_data))
```

- [ ] **Step 2: Run the schema tests and confirm the package is absent**

Run:

```powershell
python -m pytest packages/pixel-scenes/tests/test_schema.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'pixel_scenes'`.

- [ ] **Step 3: Add independent packaging and public models**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "pixel-scenes"
version = "0.1.0"
description = "Create small explanatory visuals in a friendly pixel-art style."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = ["Pillow>=11,<13"]

[project.optional-dependencies]
motion = ["numpy>=2,<3"]
test = ["pytest>=8,<10"]

[project.scripts]
pixel-scenes = "pixel_scenes.cli:entry_point"

[tool.hatch.build.targets.wheel]
packages = ["src/pixel_scenes"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Create `errors.py`:

```python
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
```

Create `model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class Canvas:
    width: int
    height: int


@dataclass(frozen=True)
class Animation:
    duration_seconds: float
    fps: int

    @property
    def frame_count(self) -> int:
        return max(1, round(self.duration_seconds * self.fps))


@dataclass(frozen=True)
class Accessibility:
    description: str


@dataclass(frozen=True)
class Scene:
    schema_version: str
    template: str
    theme: str
    canvas: Canvas
    content: Mapping[str, object]
    animation: Animation
    accessibility: Accessibility
    seed: int

    @staticmethod
    def frozen_content(value: Mapping[str, object]) -> Mapping[str, object]:
        return MappingProxyType(dict(value))


@dataclass(frozen=True)
class RenderResult:
    output_path: Path
    media_type: str
    width: int
    height: int
    frame_count: int
    duration_seconds: float
    accessibility_path: Path | None
```

Create `__init__.py`:

```python
from .model import (
    Accessibility,
    Animation,
    Canvas,
    RenderResult,
    Scene,
)
from .schema import load_scene, parse_scene, validate_scene

__all__ = [
    "Accessibility",
    "Animation",
    "Canvas",
    "RenderResult",
    "Scene",
    "load_scene",
    "parse_scene",
    "validate_scene",
]

__version__ = "0.1.0"
```

- [ ] **Step 4: Implement strict parsing and validation**

Create `schema.py` with these exact rules:

```python
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
```

Temporarily create `templates/__init__.py` so Task 1 has a complete boundary:

```python
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
```

- [ ] **Step 5: Run the schema tests**

Run from `packages/pixel-scenes`:

```powershell
python -m pytest tests/test_schema.py -q
```

Expected: all schema tests pass.

- [ ] **Step 6: Commit the package boundary**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): add strict scene schema"
```

---

### Task 2: Cozy theme and shared pixel drawing layer

**Files:**
- Create: `packages/pixel-scenes/src/pixel_scenes/theme.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/drawing.py`
- Create: `packages/pixel-scenes/tests/test_concept_card.py`

**Interfaces:**
- Consumes: `Canvas`.
- Produces: `COZY_CLASSROOM: Theme`.
- Produces: `PixelSurface(canvas: Canvas)`.
- Produces: text measurement, wrapped text, panels, arrows, markers, and nearest-neighbor output scaling.

- [ ] **Step 1: Write drawing behavior tests**

Create the initial `tests/test_concept_card.py`:

```python
from PIL import Image

from pixel_scenes.drawing import PixelSurface
from pixel_scenes.model import Canvas
from pixel_scenes.theme import COZY_CLASSROOM


def test_pixel_surface_uses_integer_logical_canvas():
    surface = PixelSurface(Canvas(960, 540), scale=3)

    assert surface.image.size == (320, 180)
    assert surface.finish().size == (960, 540)


def test_wrapped_text_stays_inside_requested_width():
    surface = PixelSurface(Canvas(480, 270), scale=3)

    lines = surface.wrap(
        "A careful step can reduce the current error.",
        max_width=110,
        font=surface.font("body"),
    )

    assert len(lines) >= 2
    assert all(
        surface.text_width(line, surface.font("body")) <= 110
        for line in lines
    )


def test_finish_uses_nearest_neighbor_scaling():
    surface = PixelSurface(Canvas(160, 90), scale=2)
    surface.image.putpixel((1, 1), COZY_CLASSROOM.ink)

    result = surface.finish()

    assert isinstance(result, Image.Image)
    assert result.getpixel((2, 2)) == COZY_CLASSROOM.ink
    assert result.getpixel((3, 3)) == COZY_CLASSROOM.ink
```

- [ ] **Step 2: Run the drawing tests and see the missing module**

Run:

```powershell
python -m pytest tests/test_concept_card.py -q
```

Expected: collection fails because `pixel_scenes.drawing` does not exist.

- [ ] **Step 3: Implement the built-in theme**

Create `theme.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    background: str
    paper: str
    ink: str
    muted_ink: str
    coral: str
    gold: str
    green: str
    blue: str
    border: str


COZY_CLASSROOM = Theme(
    background="#F7D9A6",
    paper="#FFF0CF",
    ink="#51362E",
    muted_ink="#76584B",
    coral="#E96F5B",
    gold="#F2B35B",
    green="#6FAE83",
    blue="#79B7B0",
    border="#6D4B3A",
)
```

- [ ] **Step 4: Implement the low-resolution drawing surface**

Create `drawing.py`:

```python
from __future__ import annotations

from collections.abc import Iterable

from PIL import Image, ImageDraw, ImageFont

from .errors import LayoutError
from .model import Canvas
from .theme import COZY_CLASSROOM, Theme


class PixelSurface:
    def __init__(
        self,
        canvas: Canvas,
        *,
        scale: int | None = None,
        theme: Theme = COZY_CLASSROOM,
    ) -> None:
        if scale is None:
            scale = next(
                value
                for value in (3, 2, 1)
                if canvas.width % value == 0 and canvas.height % value == 0
            )
        if scale < 1 or canvas.width % scale or canvas.height % scale:
            raise LayoutError("pixel scale must divide both canvas dimensions")
        self.canvas = canvas
        self.scale = scale
        self.theme = theme
        self.image = Image.new(
            "RGB",
            (canvas.width // scale, canvas.height // scale),
            theme.background,
        )
        self.draw = ImageDraw.Draw(self.image)

    def font(self, role: str) -> ImageFont.ImageFont:
        sizes = {"title": 16, "heading": 13, "body": 10, "label": 8}
        return ImageFont.load_default(size=sizes[role])

    def text_width(
        self, text: str, font: ImageFont.ImageFont
    ) -> int:
        box = self.draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    def wrap(
        self,
        text: str,
        *,
        max_width: int,
        font: ImageFont.ImageFont,
    ) -> list[str]:
        lines: list[str] = []
        current: list[str] = []
        for word in text.split():
            candidate = " ".join([*current, word])
            if current and self.text_width(candidate, font) > max_width:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        if any(self.text_width(line, font) > max_width for line in lines):
            raise LayoutError("a word is too wide for the text area")
        return lines

    def panel(
        self,
        box: tuple[int, int, int, int],
        *,
        fill: str | None = None,
    ) -> None:
        self.draw.rectangle(
            box,
            fill=fill or self.theme.paper,
            outline=self.theme.border,
            width=2,
        )

    def arrow(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        fill: str | None = None,
    ) -> None:
        color = fill or self.theme.ink
        self.draw.line([start, end], fill=color, width=2)
        x, y = end
        self.draw.polygon(
            [(x, y), (x - 5, y - 3), (x - 5, y + 3)],
            fill=color,
        )

    def dots(
        self,
        points: Iterable[tuple[int, int]],
        *,
        fill: str,
        size: int = 4,
    ) -> None:
        for x, y in points:
            self.draw.rectangle(
                (x, y, x + size - 1, y + size - 1), fill=fill
            )

    def finish(self) -> Image.Image:
        return self.image.resize(
            (self.canvas.width, self.canvas.height),
            resample=Image.Resampling.NEAREST,
        )
```

- [ ] **Step 5: Run the drawing tests**

Run:

```powershell
python -m pytest tests/test_concept_card.py -q
```

Expected: all drawing tests pass.

- [ ] **Step 6: Commit the visual foundation**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): add cozy pixel drawing layer"
```

---

### Task 3: Concept card, static render service, and accessibility output

**Files:**
- Create: `packages/pixel-scenes/src/pixel_scenes/accessibility.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/render.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/templates/concept_card.py`
- Modify: `packages/pixel-scenes/src/pixel_scenes/templates/__init__.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/templates/step_process.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/templates/comparison.py`
- Modify: `packages/pixel-scenes/src/pixel_scenes/__init__.py`
- Extend: `packages/pixel-scenes/tests/test_concept_card.py`
- Create: `packages/pixel-scenes/tests/test_render.py`

**Interfaces:**
- Consumes: `Scene`, `PixelSurface`, `COZY_CLASSROOM`.
- Produces: `render_concept_card(scene: Scene, progress: float) -> Image.Image`.
- Produces: `render(scene, output, *, overwrite=False, accessibility=True) -> RenderResult`.
- Produces: `write_accessibility(scene, path) -> Path`.

- [ ] **Step 1: Add template and safe-output tests**

Append to `tests/test_concept_card.py`:

```python
import pytest

from pixel_scenes import parse_scene
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.concept_card import render_concept_card


def test_concept_card_renders_requested_size(concept_data):
    scene = parse_scene(concept_data)

    image = render_concept_card(scene, progress=1.0)

    assert image.size == (960, 540)
    assert image.mode == "RGB"


def test_concept_card_rejects_unknown_content(concept_data):
    concept_data["content"]["html"] = "<iframe>"

    with pytest.raises(SceneValidationError, match="content.html"):
        parse_scene(concept_data)
```

Create `tests/test_render.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

from pixel_scenes import parse_scene, render
from pixel_scenes.errors import OutputExistsError


def test_render_writes_png_and_accessibility_text(
    tmp_path, concept_data
):
    output = tmp_path / "card.png"

    result = render(parse_scene(concept_data), output)

    assert Image.open(output).size == (960, 540)
    assert result.output_path == output
    assert result.media_type == "image/png"
    assert result.frame_count == 1
    assert result.accessibility_path == output.with_suffix(".txt")
    assert "Gradient descent" in output.with_suffix(".txt").read_text(
        encoding="utf-8"
    )


def test_render_protects_existing_output(tmp_path, concept_data):
    output = tmp_path / "card.png"
    output.write_bytes(b"keep")

    with pytest.raises(OutputExistsError):
        render(parse_scene(concept_data), output)

    assert output.read_bytes() == b"keep"


def test_render_protects_existing_accessibility_file(
    tmp_path, concept_data
):
    output = tmp_path / "card.png"
    description = tmp_path / "card.txt"
    description.write_text("keep", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        render(parse_scene(concept_data), output)

    assert not output.exists()
    assert description.read_text(encoding="utf-8") == "keep"


def test_failed_render_does_not_leave_partial_output(
    tmp_path, concept_data, monkeypatch
):
    output = tmp_path / "card.png"

    def fail(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(Image.Image, "save", fail)

    with pytest.raises(OSError, match="disk failure"):
        render(parse_scene(concept_data), output)

    assert not output.exists()
```

- [ ] **Step 2: Run the focused tests and confirm missing render functions**

Run:

```powershell
python -m pytest tests/test_concept_card.py tests/test_render.py -q
```

Expected: collection fails for missing `render` and `concept_card`.

- [ ] **Step 3: Validate and render concept card content**

Create `templates/concept_card.py`:

```python
from __future__ import annotations

from PIL import Image

from ..drawing import PixelSurface
from ..errors import SceneValidationError
from ..model import Scene

FIELDS = {"title", "summary", "key_fact"}


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
    title = str(scene.content["title"])
    summary = str(scene.content["summary"])
    surface.draw.text((18, 18), title, font=title_font, fill=surface.theme.ink)

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

    lines = surface.wrap(
        summary, max_width=width - 42, font=body_font
    )
    y = 47
    for line in lines[:4]:
        surface.draw.text(
            (18, y), line, font=body_font, fill=surface.theme.ink
        )
        y += 14

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
```

Replace `templates/__init__.py` with:

```python
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
```

Until Tasks 4 and 5 replace them, create `step_process.py` and
`comparison.py` with an explicit unsupported implementation:

```python
# step_process.py
from PIL import Image

from ..errors import SceneValidationError
from ..model import Scene


def validate(scene: Scene) -> None:
    raise SceneValidationError(
        f"template {scene.template} is not implemented in this build"
    )


def render_step_process(scene: Scene, progress: float) -> Image.Image:
    raise SceneValidationError("step-process is not implemented")
```

```python
# comparison.py
from PIL import Image

from ..errors import SceneValidationError
from ..model import Scene


def validate(scene: Scene) -> None:
    raise SceneValidationError(
        f"template {scene.template} is not implemented in this build"
    )


def render_comparison(scene: Scene, progress: float) -> Image.Image:
    raise SceneValidationError("comparison is not implemented")
```

- [ ] **Step 4: Implement accessibility and atomic PNG rendering**

Create `accessibility.py`:

```python
from __future__ import annotations

from pathlib import Path

from .model import Scene


def accessibility_text(scene: Scene) -> str:
    title = str(scene.content["title"]).strip()
    description = scene.accessibility.description.strip()
    lines = [title, "", description]
    summary = scene.content.get("summary")
    if isinstance(summary, str):
        lines.extend(["", f"Summary: {summary.strip()}"])
    fact = scene.content.get("key_fact")
    if isinstance(fact, str):
        lines.append(f"Key fact: {fact.strip()}")
    steps = scene.content.get("steps")
    if isinstance(steps, list):
        lines.extend(["", "Reading order:"])
        for index, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                lines.append(
                    f"{index}. {step['label']}: {step['detail']}"
                )
    points = scene.content.get("points")
    if isinstance(points, list):
        left = dict(scene.content["left"])
        right = dict(scene.content["right"])
        lines.extend(
            [
                "",
                f"Left, {left['heading']}: {left['description']}",
                f"Right, {right['heading']}: {right['description']}",
            ]
        )
        for point in points:
            if isinstance(point, dict):
                lines.append(
                    f"{point['label']}: {point['left']} | {point['right']}"
                )
    return "\n".join(lines) + "\n"


def write_accessibility(scene: Scene, path: Path) -> Path:
    path.write_text(accessibility_text(scene), encoding="utf-8")
    return path
```

Create the initial `render.py`:

```python
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .accessibility import write_accessibility
from .errors import OutputExistsError, RenderError
from .model import RenderResult, Scene
from .templates import render_frame

MEDIA_TYPES = {
    ".png": "image/png",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
}


def _protect_output(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise OutputExistsError(f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def render(
    scene: Scene,
    output: str | Path,
    *,
    overwrite: bool = False,
    accessibility: bool = True,
) -> RenderResult:
    destination = Path(output)
    suffix = destination.suffix.lower()
    if suffix != ".png":
        raise RenderError("this build currently supports PNG output")
    _protect_output(destination, overwrite)
    access_path = destination.with_suffix(".txt") if accessibility else None
    if access_path is not None:
        _protect_output(access_path, overwrite)
    frame = render_frame(scene, 1.0)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-",
        suffix=destination.suffix,
        dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        frame.save(temporary, format="PNG")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    if access_path is not None:
        write_accessibility(scene, access_path)
    return RenderResult(
        output_path=destination,
        media_type=MEDIA_TYPES[suffix],
        width=scene.canvas.width,
        height=scene.canvas.height,
        frame_count=1,
        duration_seconds=0.0,
        accessibility_path=access_path,
    )
```

Add `render` to the imports and `__all__` in `__init__.py`.

- [ ] **Step 5: Run concept and render tests**

Run:

```powershell
python -m pytest tests/test_concept_card.py tests/test_render.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit the first useful renderer**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): render accessible concept cards"
```

---

### Task 4: Step process template and deterministic GIF animation

**Files:**
- Replace: `packages/pixel-scenes/src/pixel_scenes/templates/step_process.py`
- Modify: `packages/pixel-scenes/src/pixel_scenes/render.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/animation.py`
- Create: `packages/pixel-scenes/tests/test_step_process.py`
- Extend: `packages/pixel-scenes/tests/test_render.py`

**Interfaces:**
- Produces: `frame_progress(frame_index: int, frame_count: int) -> float`.
- Produces: validated `step-process` content with two through six steps.
- Extends: `render` with deterministic GIF output.

- [ ] **Step 1: Write process and GIF tests**

Create `tests/test_step_process.py`:

```python
import pytest

from pixel_scenes import parse_scene
from pixel_scenes.animation import frame_progress
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.step_process import render_step_process


def process_data():
    return {
        "schema_version": "1",
        "template": "step-process",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "How a seed begins to grow",
            "steps": [
                {"label": "Water", "detail": "The seed absorbs water."},
                {"label": "Open", "detail": "The shell opens."},
                {"label": "Grow", "detail": "The first root emerges."},
            ],
        },
        "animation": {"duration_seconds": 2, "fps": 4},
        "accessibility": {
            "description": "Three labeled stages show a seed beginning to grow."
        },
        "seed": 7,
    }


def test_frame_progress_includes_both_endpoints():
    assert [frame_progress(i, 3) for i in range(3)] == [0.0, 0.5, 1.0]


def test_step_process_renders_static_summary():
    scene = parse_scene(process_data())

    image = render_step_process(scene, progress=1.0)

    assert image.size == (960, 540)


def test_step_process_accepts_two_through_six_steps():
    data = process_data()
    data["content"]["steps"] = data["content"]["steps"][:1]

    with pytest.raises(SceneValidationError, match="2 to 6"):
        parse_scene(data)
```

Append to `tests/test_render.py`:

```python
from PIL import Image, ImageSequence
from test_step_process import process_data


def test_render_writes_deterministic_gif(tmp_path):
    output = tmp_path / "process.gif"

    result = render(parse_scene(process_data()), output)

    with Image.open(output) as image:
        frames = list(ImageSequence.Iterator(image))
        assert len(frames) == 8
        assert image.size == (960, 540)
    assert result.media_type == "image/gif"
    assert result.frame_count == 8
    assert result.duration_seconds == 2
```

- [ ] **Step 2: Run the process tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_step_process.py tests/test_render.py -q
```

Expected: failures report the temporary unsupported process template and GIF
output.

- [ ] **Step 3: Implement deterministic progress and process composition**

Create `animation.py`:

```python
def frame_progress(frame_index: int, frame_count: int) -> float:
    if frame_count <= 1:
        return 1.0
    return frame_index / (frame_count - 1)
```

Replace `templates/step_process.py`:

```python
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
```

- [ ] **Step 4: Extend the render service with atomic GIF writing**

In `render.py`, add:

```python
from .animation import frame_progress


def _frames(scene: Scene) -> list:
    return [
        render_frame(scene, frame_progress(index, scene.animation.frame_count))
        for index in range(scene.animation.frame_count)
    ]


def _save_gif(scene: Scene, temporary: Path) -> int:
    frames = _frames(scene)
    duration_ms = round(1000 / scene.animation.fps)
    frames[0].save(
        temporary,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return len(frames)
```

Change the suffix check to accept `.png` and `.gif`. Select `format="PNG"`
with one frame for PNG, or `_save_gif` for GIF. Set the result duration to
`scene.animation.duration_seconds` for GIF and `0.0` for PNG.

- [ ] **Step 5: Run process and GIF tests**

Run:

```powershell
python -m pytest tests/test_step_process.py tests/test_render.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit process animation**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): animate step processes"
```

---

### Task 5: Comparison template

**Files:**
- Replace: `packages/pixel-scenes/src/pixel_scenes/templates/comparison.py`
- Create: `packages/pixel-scenes/tests/test_comparison.py`

**Interfaces:**
- Consumes: common drawing layer and scene models.
- Produces: validated comparison content with two labeled sides and one through four paired points.
- Produces: `render_comparison(scene: Scene, progress: float) -> Image.Image`.

- [ ] **Step 1: Write comparison tests**

Create `tests/test_comparison.py`:

```python
import pytest

from pixel_scenes import parse_scene
from pixel_scenes.errors import SceneValidationError
from pixel_scenes.templates.comparison import render_comparison


def comparison_data():
    return {
        "schema_version": "1",
        "template": "comparison",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "Ser and estar",
            "left": {"heading": "Ser", "description": "Identity or defining traits"},
            "right": {"heading": "Estar", "description": "State or location"},
            "points": [
                {"label": "Nature", "left": "Soy amable", "right": "Estoy cansado"},
                {"label": "Place", "left": "Es de Brasil", "right": "Está en casa"},
            ],
        },
        "animation": {"duration_seconds": 2, "fps": 4},
        "accessibility": {
            "description": "Two labeled columns compare uses of ser and estar."
        },
        "seed": 0,
    }


def test_comparison_renders_both_labeled_sides():
    scene = parse_scene(comparison_data())

    assert render_comparison(scene, 1.0).size == (960, 540)


def test_comparison_requires_one_through_four_points():
    data = comparison_data()
    data["content"]["points"] = []

    with pytest.raises(SceneValidationError, match="1 to 4"):
        parse_scene(data)
```

- [ ] **Step 2: Run comparison tests and confirm unsupported failure**

Run:

```powershell
python -m pytest tests/test_comparison.py -q
```

Expected: tests fail because the temporary comparison module rejects the
template.

- [ ] **Step 3: Implement comparison validation and rendering**

Replace `templates/comparison.py`:

```python
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
```

- [ ] **Step 4: Run all template tests**

Run:

```powershell
python -m pytest tests/test_concept_card.py tests/test_step_process.py tests/test_comparison.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit comparison rendering**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): render pixel comparisons"
```

---

### Task 6: Safe FFmpeg MP4 encoding

**Files:**
- Create: `packages/pixel-scenes/src/pixel_scenes/ffmpeg.py`
- Modify: `packages/pixel-scenes/src/pixel_scenes/render.py`
- Create: `packages/pixel-scenes/tests/test_ffmpeg.py`

**Interfaces:**
- Produces: `resolve_ffmpeg(explicit: str | Path | None = None) -> Path`.
- Produces: `encode_mp4(frames, destination, fps, ffmpeg_path=None) -> None`.
- Extends: `render(..., ffmpeg_path=None)` with MP4 output.

- [ ] **Step 1: Write shell-free encoder tests**

Create `tests/test_ffmpeg.py`:

```python
from pathlib import Path

import pytest
from PIL import Image

from pixel_scenes.errors import MissingDependencyError, RenderError
from pixel_scenes.ffmpeg import encode_mp4, resolve_ffmpeg


def test_resolve_ffmpeg_explains_missing_dependency(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(MissingDependencyError, match="FFmpeg"):
        resolve_ffmpeg()


def test_encode_mp4_uses_argument_list_without_shell(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"binary")
    destination = tmp_path / "movie.mp4"
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        destination.write_bytes(b"video")
        return type("Result", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_run)
    frames = [Image.new("RGB", (160, 90), "white")]

    encode_mp4(frames, destination, fps=4, ffmpeg_path=executable)

    arguments, kwargs = calls[0]
    assert isinstance(arguments, list)
    assert kwargs["shell"] is False
    assert str(executable) == arguments[0]
    assert destination.read_bytes() == b"video"


def test_encode_mp4_reports_final_ffmpeg_message(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"binary")

    def fail(arguments, **kwargs):
        return type(
            "Result",
            (),
            {"returncode": 1, "stderr": "header\ninvalid encoder"},
        )()

    monkeypatch.setattr("subprocess.run", fail)

    with pytest.raises(RenderError, match="invalid encoder"):
        encode_mp4(
            [Image.new("RGB", (160, 90))],
            tmp_path / "movie.mp4",
            fps=4,
            ffmpeg_path=executable,
        )
```

- [ ] **Step 2: Run encoder tests and confirm the module is missing**

Run:

```powershell
python -m pytest tests/test_ffmpeg.py -q
```

Expected: collection fails for missing `pixel_scenes.ffmpeg`.

- [ ] **Step 3: Implement the FFmpeg adapter**

Create `ffmpeg.py`:

```python
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image

from .errors import MissingDependencyError, RenderError


def resolve_ffmpeg(explicit: str | Path | None = None) -> Path:
    candidate = Path(explicit) if explicit is not None else None
    if candidate is None:
        discovered = shutil.which("ffmpeg")
        if discovered is None:
            raise MissingDependencyError(
                "FFmpeg is required for MP4 output. Install it or pass ffmpeg_path."
            )
        candidate = Path(discovered)
    if not candidate.is_file():
        raise MissingDependencyError(
            f"FFmpeg executable was not found: {candidate}"
        )
    return candidate


def encode_mp4(
    frames: Sequence[Image.Image],
    destination: Path,
    *,
    fps: int,
    ffmpeg_path: str | Path | None = None,
) -> None:
    executable = resolve_ffmpeg(ffmpeg_path)
    with tempfile.TemporaryDirectory(prefix="pixel-scenes-") as directory:
        frame_dir = Path(directory)
        for index, frame in enumerate(frames):
            frame.save(frame_dir / f"frame-{index:04d}.png", format="PNG")
        arguments = [
            str(executable),
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame-%04d.png"),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ]
        result = subprocess.run(
            arguments,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            lines = [line for line in result.stderr.splitlines() if line.strip()]
            diagnostic = lines[-1] if lines else "unknown FFmpeg error"
            raise RenderError(f"FFmpeg could not encode MP4: {diagnostic}")
```

- [ ] **Step 4: Extend atomic rendering for MP4**

Add `ffmpeg_path: str | Path | None = None` to `render`. Accept `.mp4`, call
`_frames(scene)`, and pass the temporary sibling path to:

```python
encode_mp4(
    frames,
    temporary,
    fps=scene.animation.fps,
    ffmpeg_path=ffmpeg_path,
)
```

Keep `os.replace(temporary, destination)` in the shared success path. Return
`video/mp4`, the actual frame count, and the configured duration.

- [ ] **Step 5: Run encoder and render tests**

Run:

```powershell
python -m pytest tests/test_ffmpeg.py tests/test_render.py -q
```

Expected: all tests pass. MP4 tests use a fake subprocess and require no local
FFmpeg installation.

- [ ] **Step 6: Commit safe MP4 support**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): encode MP4 with safe FFmpeg calls"
```

---

### Task 7: Command line interface, examples, and independent documentation

**Files:**
- Create: `packages/pixel-scenes/src/pixel_scenes/cli.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/__main__.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/data/__init__.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/data/examples/__init__.py`
- Create: `packages/pixel-scenes/src/pixel_scenes/data/examples/concept-card.json`
- Create: `packages/pixel-scenes/src/pixel_scenes/data/examples/step-process.json`
- Create: `packages/pixel-scenes/src/pixel_scenes/data/examples/comparison.json`
- Create: `packages/pixel-scenes/examples/gradient-descent.json`
- Create: `packages/pixel-scenes/examples/language-comparison.json`
- Create: `packages/pixel-scenes/examples/historical-process.json`
- Create: `packages/pixel-scenes/README.md`
- Create: `packages/pixel-scenes/tests/test_cli.py`
- Create: `packages/pixel-scenes/tests/test_independence.py`

**Interfaces:**
- Produces: `entry_point(argv: Sequence[str] | None = None) -> int`.
- Produces commands: `validate`, `render`, `example`, `themes`, and `--version`.
- Consumes the same `load_scene`, `validate_scene`, and `render` APIs used by Python callers.

- [ ] **Step 1: Write CLI and independence tests**

Create `tests/test_cli.py`:

```python
import json

from pixel_scenes.cli import entry_point


def test_validate_command_reports_success(tmp_path, concept_data, capsys):
    scene = tmp_path / "scene.json"
    scene.write_text(json.dumps(concept_data), encoding="utf-8")

    assert entry_point(["validate", str(scene)]) == 0
    assert "Scene is valid." in capsys.readouterr().out


def test_render_command_creates_output(
    tmp_path, concept_data, capsys
):
    scene = tmp_path / "scene.json"
    output = tmp_path / "card.png"
    scene.write_text(json.dumps(concept_data), encoding="utf-8")

    assert entry_point(["render", str(scene), "--output", str(output)]) == 0
    assert output.exists()
    assert str(output) in capsys.readouterr().out


def test_expected_error_has_no_traceback(capsys):
    assert entry_point(["validate", "missing.json"]) == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_themes_lists_builtin_theme(capsys):
    assert entry_point(["themes"]) == 0
    assert capsys.readouterr().out.strip() == "cozy-classroom"
```

Create `tests/test_independence.py`:

```python
import ast
from pathlib import Path


def test_pixel_scenes_source_never_imports_socratic_learn():
    source_root = Path(__file__).parents[1] / "src" / "pixel_scenes"
    offenders = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "socratic_learn" or name.startswith("socratic_learn.") for name in names):
                offenders.append(path)
    assert offenders == []
```

- [ ] **Step 2: Run CLI and independence tests**

Run:

```powershell
python -m pytest tests/test_cli.py tests/test_independence.py -q
```

Expected: collection fails because `pixel_scenes.cli` does not exist.

- [ ] **Step 3: Implement the command line interface**

Create `cli.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path

from . import __version__, load_scene, render
from .errors import PixelScenesError

def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pixel-scenes")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)

    validate_command = commands.add_parser("validate")
    validate_command.add_argument("scene")

    render_command = commands.add_parser("render")
    render_command.add_argument("scene")
    render_command.add_argument("--output", required=True)
    render_command.add_argument("--overwrite", action="store_true")
    render_command.add_argument("--no-accessibility", action="store_true")
    render_command.add_argument("--ffmpeg")

    example_command = commands.add_parser("example")
    example_command.add_argument(
        "name",
        choices=["concept-card", "step-process", "comparison"],
    )
    example_command.add_argument("--output", required=True)

    commands.add_parser("themes")
    return root


def entry_point(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            load_scene(arguments.scene)
            print("Scene is valid.")
            return 0
        if arguments.command == "themes":
            print("cozy-classroom")
            return 0
        if arguments.command == "example":
            names = {
                "concept-card": "concept-card.json",
                "step-process": "step-process.json",
                "comparison": "comparison.json",
            }
            value = json.loads(
                files("pixel_scenes.data.examples")
                .joinpath(names[arguments.name])
                .read_text(encoding="utf-8")
            )
            Path(arguments.output).write_text(
                json.dumps(value, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(arguments.output)
            return 0
        result = render(
            load_scene(arguments.scene),
            arguments.output,
            overwrite=arguments.overwrite,
            accessibility=not arguments.no_accessibility,
            ffmpeg_path=arguments.ffmpeg,
        )
        print(result.output_path)
        return 0
    except (PixelScenesError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
```

Create `__main__.py`:

```python
from .cli import entry_point

raise SystemExit(entry_point())
```

- [ ] **Step 4: Add three complete example scenes**

Create `examples/gradient-descent.json`:

```json
{
  "schema_version": "1",
  "template": "concept-card",
  "theme": "cozy-classroom",
  "canvas": {"width": 960, "height": 540},
  "content": {
    "title": "Gradient descent",
    "summary": "Walk downhill one careful step at a time.",
    "key_fact": "Smaller loss means a better fit."
  },
  "animation": {"duration_seconds": 4, "fps": 12},
  "accessibility": {
    "description": "A marker moves down a stepped hill as the loss becomes smaller."
  },
  "seed": 0
}
```

Create `examples/language-comparison.json`:

```json
{
  "schema_version": "1",
  "template": "comparison",
  "theme": "cozy-classroom",
  "canvas": {"width": 960, "height": 540},
  "content": {
    "title": "Ser and estar",
    "left": {
      "heading": "Ser",
      "description": "Identity or defining traits"
    },
    "right": {
      "heading": "Estar",
      "description": "State or location"
    },
    "points": [
      {"label": "Nature", "left": "Soy amable", "right": "Estoy cansado"},
      {"label": "Place", "left": "Es de Brasil", "right": "Está en casa"}
    ]
  },
  "animation": {"duration_seconds": 4, "fps": 12},
  "accessibility": {
    "description": "Two labeled columns compare uses of the Spanish verbs ser and estar."
  },
  "seed": 0
}
```

Create `examples/historical-process.json`:

```json
{
  "schema_version": "1",
  "template": "step-process",
  "theme": "cozy-classroom",
  "canvas": {"width": 960, "height": 540},
  "content": {
    "title": "How printing spread ideas",
    "steps": [
      {"label": "Copy", "detail": "A page is prepared once."},
      {"label": "Print", "detail": "The press makes many copies."},
      {"label": "Share", "detail": "Readers carry the ideas farther."}
    ]
  },
  "animation": {"duration_seconds": 4, "fps": 12},
  "accessibility": {
    "description": "Three stages show preparation, repeated printing, and distribution."
  },
  "seed": 0
}
```

Copy the same three scene objects into the packaged files
`concept-card.json`, `comparison.json`, and `step-process.json`. The packaged
copies make the `example` command work from wheels as well as editable installs.

- [ ] **Step 5: Write standalone README**

Create `packages/pixel-scenes/README.md` with these sections and commands:

````markdown
# Pixel Scenes

Pixel Scenes turns small JSON descriptions into clear pixel-art explanations.
It works on its own from a terminal or as a Python library.

## Install for development

```powershell
python -m pip install -e ".[test]"
```

## Render your first visual

```powershell
pixel-scenes render examples/gradient-descent.json --output gradient.png
pixel-scenes render examples/historical-process.json --output history.gif
```

MP4 output uses FFmpeg:

```powershell
pixel-scenes render examples/historical-process.json --output history.mp4
```

## Scene format

A scene is a UTF-8 JSON object. `schema_version` is `"1"`. `template` is
`concept-card`, `step-process`, or `comparison`. `theme` is
`cozy-classroom`. `canvas` sets the output width and height. `content` contains
the fields owned by the selected template. `animation` sets a duration and
frame rate. `accessibility.description` explains the visual in words. `seed`
makes supported motion deterministic.

Start from a bundled scene:

```powershell
pixel-scenes example concept-card --output my-scene.json
```

## Templates

`concept-card` requires a title and summary and accepts a key fact.
`step-process` requires a title and two through six steps. Each step has a
label and detail. `comparison` requires a title, left and right headings and
descriptions, and one through four paired points.

## Python API

```python
from pixel_scenes import load_scene, render, validate_scene

scene = load_scene("examples/gradient-descent.json")
validate_scene(scene)
result = render(scene, "gradient.png")
print(result.accessibility_path)
```

## Output safety and accessibility

Pixel Scenes protects existing files unless you pass `--overwrite`. Canvas
size, duration, frame rate, text length, and frame count are bounded before
rendering. FFmpeg receives an argument list without a command shell. Scene
content cannot become a command option.

Each render also writes a text description beside the visual. Use
`--no-accessibility` only when another part of your application provides an
equivalent description.

## Current limits

Version 1 uses built-in assets and the Cozy Pixel Classroom theme. It does not
load URLs, execute scene code, accept custom plugins, or generate scenes from
natural language.
````

- [ ] **Step 6: Run CLI tests and render all examples**

Run from `packages/pixel-scenes`:

```powershell
python -m pytest tests/test_cli.py tests/test_independence.py -q
python -m pixel_scenes validate examples/gradient-descent.json
python -m pixel_scenes render examples/gradient-descent.json --output build/gradient.png
python -m pixel_scenes render examples/historical-process.json --output build/history.gif
python -m pixel_scenes render examples/language-comparison.json --output build/language.png
```

Expected: tests pass, validation prints `Scene is valid.`, and each render
prints its output path and creates the output plus its `.txt` description.

- [ ] **Step 7: Commit the usable standalone tool**

```powershell
git add packages/pixel-scenes
git commit -m "feat(pixel-scenes): add CLI examples and documentation"
```

---

### Task 8: Package installation and complete verification

**Files:**
- Modify only files under `packages/pixel-scenes/` if verification exposes a defect.

**Interfaces:**
- Verifies the complete public CLI and Python package from an editable install.
- Verifies the nested project remains independent from the root project.

- [ ] **Step 1: Install the nested project in editable mode**

Run from `packages/pixel-scenes`:

```powershell
python -m pip install -e ".[test]"
```

Expected: pip installs `pixel-scenes==0.1.0` with Pillow and pytest without
installing `socratic-learn`.

- [ ] **Step 2: Run the complete nested suite**

Run:

```powershell
python -m pytest -q
```

Expected: every test under `packages/pixel-scenes/tests` passes.

- [ ] **Step 3: Exercise the installed command**

Run:

```powershell
pixel-scenes --version
pixel-scenes themes
pixel-scenes validate examples/gradient-descent.json
pixel-scenes render examples/gradient-descent.json --output build/installed.png --overwrite
```

Expected:

```text
0.1.0
cozy-classroom
Scene is valid.
build\installed.png
```

The PNG and `build/installed.txt` must exist.

- [ ] **Step 4: Verify package contents and source independence**

Run:

```powershell
python -m pip show pixel-scenes
python -c "import pixel_scenes; print(pixel_scenes.__version__)"
python -m pytest tests/test_independence.py -q
```

Expected: package metadata points to `packages/pixel-scenes`, version output is
`0.1.0`, and the independence test passes.

- [ ] **Step 5: Inspect the three visual examples**

Open:

```text
packages/pixel-scenes/build/gradient.png
packages/pixel-scenes/build/history.gif
packages/pixel-scenes/build/language.png
```

Confirm that text is readable at final size, labels do not overlap, animation
explains the sequence, color is not the only distinction, and decorative
pixel elements remain secondary.

- [ ] **Step 6: Run repository hygiene checks**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. The status contains only intended Pixel Scenes
changes plus the two pre-existing untracked IOI documents, which must remain
untouched.

- [ ] **Step 7: Commit verification fixes if any were required**

If Step 2 through Step 6 required a code or documentation correction:

```powershell
git add packages/pixel-scenes
git commit -m "fix(pixel-scenes): complete standalone verification"
```

If no correction was required, do not create an empty commit.
