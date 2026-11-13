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
