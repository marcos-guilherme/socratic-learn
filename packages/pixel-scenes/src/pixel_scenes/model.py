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
