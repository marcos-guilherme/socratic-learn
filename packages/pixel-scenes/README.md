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
