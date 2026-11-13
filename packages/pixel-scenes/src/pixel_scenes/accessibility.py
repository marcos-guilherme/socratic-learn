from __future__ import annotations

import os
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
    """Write the accessibility sidecar atomically via a sibling temp file.

  The final ``path`` appears only after ``os.replace``; readers never see a
  partial file. If encoding fails, any leftover ``.<name>.tmp`` is removed.
  The visual output and sidecar are still separate files with no cross-file
  transaction guarantee.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(accessibility_text(scene), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
