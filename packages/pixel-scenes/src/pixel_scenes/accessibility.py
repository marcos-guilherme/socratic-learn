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
