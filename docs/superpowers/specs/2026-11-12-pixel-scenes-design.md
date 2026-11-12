# Pixel Scenes Design

## Status

Approved in conversation on 2026-11-12. Written specification awaiting final
user review.

## Purpose

Pixel Scenes is a standalone Python tool for making small, clear educational
and explanatory visuals in a friendly pixel-art style. It can produce static
images and short animations from a validated scene description.

The tool begins inside the Socratic Learn repository for convenient
development, but it must remain independently installable and reusable. It
must not import from, refer to, or require Socratic Learn. Socratic Learn may
call it later as one consumer among many.

## Intended uses

Pixel Scenes should be useful to:

1. illustrate a concept with a compact visual card;
2. animate a short process one step at a time;
3. compare two states, ideas, or quantities;
4. let an AI agent request a visual without allowing that agent to execute
   arbitrary Python code;
5. let a person render the same visual from a terminal or Python program.

The first version is intended for educational explanations, documentation,
presentations, and social media sized visual snippets. It is not a general
video editor, drawing program, plotting library, or image generation model.

## Project boundary

The project lives under `packages/pixel-scenes/` and owns its own:

1. `pyproject.toml`;
2. Python package;
3. command line entry point;
4. examples;
5. tests;
6. documentation.

Installing the root Socratic Learn project must not install Pixel Scenes
implicitly. Installing Pixel Scenes must not install or import Socratic Learn.
The only supported integration boundary is the public scene format, command
line interface, and Python API.

The distribution name is provisionally `pixel-scenes`, the import package is
`pixel_scenes`, and the command is `pixel-scenes`. Naming may be changed before
the first public release if package registry or trademark checks find a
conflict.

## Chosen approach

Pixel Scenes uses a hybrid rendering system. A caller supplies declarative
data, while the library owns the rendering code.

This approach is more flexible than a set of fixed templates and safer and
more predictable than executing code written by an AI model. Templates provide
the initial composition, while reusable scene elements allow controlled
variation.

The renderer must never evaluate Python, JavaScript, shell commands, template
expressions, or other executable content from a scene file.

## User interfaces

### Command line

The primary commands are:

```text
pixel-scenes validate scene.json
pixel-scenes render scene.json --output explanation.png
pixel-scenes render scene.json --output explanation.gif
pixel-scenes render scene.json --output explanation.mp4
pixel-scenes example concept-card --output example.json
pixel-scenes themes
```

The output extension selects the renderer. PNG uses a single frame. GIF uses
Pillow animation support. MP4 uses an external FFmpeg executable.

Commands return a nonzero exit code and a plain explanation when validation or
rendering fails. Normal operation must not print a Python traceback unless a
debug option is enabled.

### Python API

The public API exposes focused operations:

```python
from pixel_scenes import load_scene, render, validate_scene

scene = load_scene("scene.json")
validate_scene(scene)
result = render(scene, "explanation.png")
```

Public functions accept path-like objects. Rendering returns a result that
contains the output path, media type, dimensions, frame count, duration, and
accessibility description path.

### Scene format

A scene is UTF-8 JSON with a versioned top-level structure:

```json
{
  "schema_version": "1",
  "template": "concept-card",
  "theme": "cozy-classroom",
  "canvas": {"width": 960, "height": 540},
  "content": {
    "title": "Gradient descent",
    "summary": "Walk downhill one careful step at a time.",
    "steps": []
  },
  "animation": {"duration_seconds": 4, "fps": 12},
  "accessibility": {
    "description": "A sequence of points moves down a curved slope."
  }
}
```

Unknown top-level fields fail validation in schema version 1. This prevents
misspelled settings from being silently ignored. Template-specific content is
validated before any files are created.

JSON is the interchange format because it is widely supported and easy for
agents and other programs to produce. A Python dictionary may be passed
directly through the API.

## Initial templates

### Concept card

A concept card combines a title, a short explanation, one central visual, and
an optional key fact. It renders as PNG by default and may use a subtle
entrance animation for GIF or MP4.

### Step process

A step process presents two to six ordered states. Animation reveals or moves
one meaningful element at a time. Static output places the states in a readable
sequence so the explanation still works without motion.

### Comparison

A comparison presents two states or ideas with shared visual scales where
possible. Color is never the only way to distinguish sides. Labels, shapes, or
patterns carry the same distinction.

Templates control layout and reading order. They do not limit the subject.
Text and scene elements can describe mathematics, science, language, history,
software, or another domain.

## Visual system

The default `cozy-classroom` theme uses:

1. warm, limited color palettes;
2. crisp pixel edges and integer scaling;
3. friendly, simple characters and classroom objects;
4. compact labels in a pixel-compatible font;
5. restrained movement that explains rather than decorates.

Decorative elements must remain secondary to the concept. Text must remain
readable at the final output size. Charts, arrows, labels, and state changes
take priority over characters and background objects.

Theme definitions are data files owned by the package. Version 1 supports only
built-in themes. Custom theme loading is deferred until the theme contract is
stable.

## Scene elements

Templates compose a small set of renderer-owned elements:

1. text blocks and labels;
2. panels and callout boxes;
3. arrows, lines, axes, and paths;
4. bars, dots, grids, and simple charts;
5. pixel sprites from a built-in asset set;
6. step indicators and progress markers;
7. highlights and comparison markers.

Version 1 does not accept arbitrary SVG, HTML, remote images, fonts, or
user-supplied executable plugins. Local image import is also deferred to avoid
expanding path handling and media safety before the core format is proven.

## Rendering architecture

The package is divided into small units:

1. `schema` parses and validates versioned scene data.
2. `templates` converts validated content into an internal scene graph.
3. `themes` resolves colors, typography, spacing, and sprite choices.
4. `layout` measures text and places elements on integer coordinates.
5. `renderers.pillow` draws frames and writes PNG or GIF files.
6. `animation` calculates deterministic frame states and interpolation.
7. `encoders.ffmpeg` passes rendered frames to FFmpeg for MP4 output.
8. `accessibility` creates a plain text sidecar description.
9. `cli` maps terminal commands to the same public operations used by the
   Python API.

Pillow is a required runtime dependency. NumPy is optional and used only where
array operations materially simplify deterministic animation or chart data.
The core templates must still work without NumPy. FFmpeg is an optional system
dependency required only for MP4 output.

The renderer uses a deterministic seed stored in the scene or a documented
default. The same supported version, scene, fonts, and assets should produce
the same frames.

## Data flow

Rendering follows one direction:

1. load JSON or a Python dictionary;
2. validate the schema and template content;
3. resolve the built-in theme and assets;
4. build an internal scene graph;
5. calculate static layout;
6. generate one frame or a bounded frame sequence;
7. encode the selected output format;
8. write the accessibility description;
9. return rendering metadata.

No stage mutates the caller's input. Intermediate frames use a temporary
directory controlled by the library and are removed after successful or failed
encoding.

## Safety and resource limits

Version 1 enforces fixed defaults and hard upper bounds:

1. canvas dimensions from 160 by 90 through 1920 by 1080;
2. animation duration of at most 15 seconds;
3. frame rate from 1 through 30 frames per second;
4. at most 450 frames;
5. bounded text length and template item counts;
6. outputs only at an explicit caller-provided path;
7. temporary files only inside a library-created temporary directory.

FFmpeg is launched with an argument list and never through a shell. The
executable path is discovered through configuration or the system path and
validated before use. Scene content never becomes an FFmpeg option.

Rendering writes to a temporary sibling file and replaces the destination only
after encoding succeeds. Existing outputs are not overwritten unless the
caller supplies an explicit overwrite option.

## Error handling

Errors use a small public hierarchy:

1. `SceneValidationError` identifies the field and rejected value;
2. `LayoutError` explains content that cannot fit safely;
3. `MissingDependencyError` explains how to enable MP4 or an optional feature;
4. `RenderError` reports a drawing or encoding failure;
5. `OutputExistsError` protects an existing file.

Validation should report all independent scene errors in one pass when
possible. FFmpeg failures include the relevant final diagnostic without
printing the entire subprocess environment or command input.

## Accessibility

Every successful render produces a UTF-8 text sidecar next to the visual unless
the caller explicitly disables it. The sidecar includes the title, explanation,
reading order, important state changes, and any values represented by the
visual.

The schema requires a human-readable description. Templates may enrich it with
structured content, but they must not replace the author's intended
explanation. Animation must not be the only carrier of meaning. Static output
must preserve the main instructional sequence.

Built-in themes meet readable contrast targets for body text and labels.
Color-coded elements also use labels, shapes, patterns, or position.

## Verification strategy

The project verifies behavior at three levels:

1. schema and layout unit checks for valid and invalid scenes;
2. renderer checks for dimensions, frame counts, metadata, and deterministic
   pixel output on bundled fonts and assets;
3. command line checks that render bundled examples and exercise missing
   FFmpeg, protected outputs, and invalid input.

Small golden images may protect intentional pixel output. They must use bundled
assets and fixed rendering conditions. Tests should compare focused regions or
hashes only when deterministic behavior is guaranteed across supported
platforms.

The initial examples cover all three templates in PNG and GIF. MP4 checks run
only when a compatible FFmpeg executable is available.

## Documentation and examples

The independent project README explains installation, the first render, the
scene format, the three templates, output formats, accessibility files, limits,
and FFmpeg setup.

Examples use varied subjects so the tool does not appear limited to mathematics
or machine learning. The first set includes:

1. gradient descent as a step process;
2. a language comparison card;
3. a historical cause and effect sequence.

## Deferred work

The first version does not include:

1. arbitrary code execution;
2. free-form drawing primitives exposed directly in JSON;
3. remote assets or URLs;
4. custom fonts, sprites, or themes;
5. audio;
6. interactive output;
7. a graphical editor;
8. automatic natural-language-to-scene generation;
9. a direct Socratic Learn adapter.

These features can be considered after the scene contract and initial
templates have been used in real examples.

## Completion criteria

The first version is complete when:

1. the nested project installs without Socratic Learn;
2. its source imports no Socratic Learn modules;
3. each initial template renders a useful PNG and GIF example;
4. MP4 rendering works when FFmpeg is available and fails clearly when it is
   not;
5. invalid or excessive scenes fail before output creation;
6. existing files remain protected by default;
7. each render can produce an accessibility sidecar;
8. command line and Python API behavior match;
9. documentation lets a new user render a bundled example without reading the
   implementation;
10. the output follows the approved Cozy Pixel Classroom direction while
    keeping the explanation visually dominant.
