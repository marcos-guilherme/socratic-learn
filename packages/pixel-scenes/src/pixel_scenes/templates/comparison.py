from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from PIL import Image, ImageFont

from ..drawing import PixelSurface
from ..errors import LayoutError, SceneValidationError
from ..model import Scene

FIELDS = {"title", "left", "right", "points"}
SIDE_FIELDS = {"heading", "description"}
POINT_FIELDS = {"label", "left", "right"}

LABEL_LINE_HEIGHT = 9
BODY_LINE_HEIGHT = 10
DESCRIPTION_GAP = 4
ROW_GAP = 2
POINTS_BOTTOM_MARGIN = 12
HEADER_TOP = 40
HEADER_BOTTOM = 58
DESCRIPTION_START_Y = 60
TITLE_TOP = 17
TITLE_LINE_HEIGHT = 16
HEADER_TEXT_TOP = HEADER_TOP + 6
HEADING_LINE_HEIGHT = 12
TITLE_BOTTOM = HEADER_TOP - 2


def _short_text(value: object, field: str, maximum: int) -> None:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise SceneValidationError(
            f"{field} must contain 1 to {maximum} characters"
        )


def revealed_point_count(point_count: int, progress: float) -> int:
    if point_count <= 0:
        return 0
    clamped = max(0.0, min(1.0, progress))
    return max(1, min(point_count, round(clamped * point_count)))


def visible_comparison_points(
    points: Sequence[object], progress: float
) -> list[object]:
    count = revealed_point_count(len(points), progress)
    return list(points[:count])


@dataclass(frozen=True)
class ComparisonColumnMetrics:
    middle: int
    column_width: int
    left_x: int
    right_x: int
    label_x: int
    label_max_width: int


def comparison_column_metrics(surface: PixelSurface) -> ComparisonColumnMetrics:
    width, _height = surface.image.size
    middle = width // 2
    column_width = middle - 36
    if column_width < 8:
        raise LayoutError("comparison columns are too narrow for content")
    return ComparisonColumnMetrics(
        middle=middle,
        column_width=column_width,
        left_x=18,
        right_x=middle + 12,
        label_x=middle - 28,
        label_max_width=56,
    )


def _wrap_characters(
    surface: PixelSurface,
    text: str,
    max_width: int,
    font: ImageFont.ImageFont,
) -> list[str]:
    lines: list[str] = []
    current = ""
    for character in text:
        candidate = f"{current}{character}"
        if current and surface.text_width(candidate, font) > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    if current:
        lines.append(current)
    if not lines:
        raise LayoutError("comparison text is empty")
    overflow = [
        line for line in lines if surface.text_width(line, font) > max_width
    ]
    if overflow:
        raise LayoutError("comparison text is too wide for its column")
    return lines


def fit_comparison_lines(
    surface: PixelSurface,
    text: str,
    max_width: int,
    *,
    font: ImageFont.ImageFont,
) -> list[str]:
    return surface.fit_text_lines(
        text,
        max_width,
        font=font,
        empty_message="comparison text is empty",
        wide_message="comparison text is too wide for its column",
    )


@dataclass(frozen=True)
class ComparisonPointRow:
    label_lines: tuple[str, ...]
    left_lines: tuple[str, ...]
    right_lines: tuple[str, ...]
    height: int
    y: int = 0


def _row_height(
    label_lines: Sequence[str],
    left_lines: Sequence[str],
    right_lines: Sequence[str],
) -> int:
    label_block = max(1, len(label_lines)) * LABEL_LINE_HEIGHT
    body_lines = max(len(left_lines), len(right_lines), 1)
    return label_block + 2 + body_lines * BODY_LINE_HEIGHT


def _plan_point_rows(
    surface: PixelSurface,
    metrics: ComparisonColumnMetrics,
    points: Sequence[Mapping[str, object]],
    visible_count: int,
) -> list[ComparisonPointRow]:
    label_font = surface.font("label")
    body_font = surface.font("body")
    text_width = metrics.column_width - 16
    rows: list[ComparisonPointRow] = []
    for raw_point in points[:visible_count]:
        point = dict(raw_point)
        label_lines = fit_comparison_lines(
            surface,
            str(point["label"]),
            metrics.label_max_width,
            font=label_font,
        )
        left_lines = fit_comparison_lines(
            surface,
            str(point["left"]),
            text_width,
            font=body_font,
        )
        right_lines = fit_comparison_lines(
            surface,
            str(point["right"]),
            text_width,
            font=body_font,
        )
        rows.append(
            ComparisonPointRow(
                label_lines=tuple(label_lines),
                left_lines=tuple(left_lines),
                right_lines=tuple(right_lines),
                height=_row_height(label_lines, left_lines, right_lines),
            )
        )
    return rows


def _description_bottom(
    surface: PixelSurface,
    metrics: ComparisonColumnMetrics,
    scene: Scene,
) -> int:
    label_font = surface.font("label")
    text_width = metrics.column_width - 16
    line_counts = []
    for side_name in ("left", "right"):
        side = dict(scene.content[side_name])
        lines = fit_comparison_lines(
            surface,
            str(side["description"]),
            text_width,
            font=label_font,
        )
        line_counts.append(len(lines))
    return DESCRIPTION_START_Y + max(line_counts) * LABEL_LINE_HEIGHT


def _layout_point_rows(
    rows: list[ComparisonPointRow],
    *,
    points_start: int,
    points_end: int,
) -> list[ComparisonPointRow]:
    if not rows:
        return []
    natural_total = sum(row.height for row in rows) + ROW_GAP * (len(rows) - 1)
    available = points_end - points_start
    if natural_total > available:
        raise LayoutError("comparison points do not fit the panel")
    extra = available - natural_total
    gap = ROW_GAP + (extra // (len(rows) - 1) if len(rows) > 1 else 0)
    positioned: list[ComparisonPointRow] = []
    y = points_start
    for index, row in enumerate(rows):
        positioned.append(
            ComparisonPointRow(
                label_lines=row.label_lines,
                left_lines=row.left_lines,
                right_lines=row.right_lines,
                height=row.height,
                y=y,
            )
        )
        if index + 1 < len(rows):
            y += row.height + gap
    return positioned


def comparison_content_bottom(
    surface: PixelSurface, scene: Scene, *, progress: float
) -> int:
    _width, height = surface.image.size
    metrics = comparison_column_metrics(surface)
    desc_bottom = _description_bottom(surface, metrics, scene)
    points_start = desc_bottom + DESCRIPTION_GAP
    points_end = height - POINTS_BOTTOM_MARGIN
    points = list(scene.content["points"])
    visible = revealed_point_count(len(points), progress)
    rows = _plan_point_rows(surface, metrics, points, visible)
    positioned = _layout_point_rows(
        rows,
        points_start=points_start,
        points_end=points_end,
    )
    if not positioned:
        return desc_bottom
    last = positioned[-1]
    return last.y + last.height


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
    title_font = surface.font("title")
    title_lines = surface.fit_text_lines(
        str(scene.content["title"]),
        width - 36,
        font=title_font,
        empty_message="title text is empty",
        wide_message="title is too wide for the panel",
    )
    max_title_lines = max(
        1, (TITLE_BOTTOM - TITLE_TOP) // TITLE_LINE_HEIGHT
    )
    if len(title_lines) > max_title_lines:
        raise LayoutError("title does not fit the panel")
    for line_index, line in enumerate(title_lines):
        surface.draw.text(
            (18, TITLE_TOP + line_index * TITLE_LINE_HEIGHT),
            line,
            font=title_font,
            fill=surface.theme.ink,
        )
    metrics = comparison_column_metrics(surface)
    surface.draw.line(
        [
            (metrics.middle, HEADER_TOP),
            (metrics.middle, height - POINTS_BOTTOM_MARGIN),
        ],
        fill=surface.theme.border,
        width=2,
    )
    sides = (
        ("left", metrics.left_x, surface.theme.blue),
        ("right", metrics.right_x, surface.theme.coral),
    )
    label_font = surface.font("label")
    heading_font = surface.font("heading")
    text_width = metrics.column_width - 16
    heading_max_lines = max(
        1,
        (HEADER_BOTTOM - HEADER_TEXT_TOP) // HEADING_LINE_HEIGHT,
    )
    for side_name, x, color in sides:
        side = dict(scene.content[side_name])
        surface.draw.rectangle(
            (x, HEADER_TOP, x + metrics.column_width, HEADER_BOTTOM),
            fill=color,
        )
        heading_lines = surface.fit_text_lines(
            str(side["heading"]),
            text_width,
            font=heading_font,
            empty_message="comparison heading is empty",
            wide_message="comparison heading is too wide for its column",
        )
        if len(heading_lines) > heading_max_lines:
            raise LayoutError("comparison heading does not fit the panel")
        for line_index, line in enumerate(heading_lines):
            surface.draw.text(
                (x + 8, HEADER_TEXT_TOP + line_index * HEADING_LINE_HEIGHT),
                line,
                font=heading_font,
                fill=surface.theme.ink,
            )
        description_lines = fit_comparison_lines(
            surface,
            str(side["description"]),
            text_width,
            font=label_font,
        )
        for line_index, line in enumerate(description_lines):
            surface.draw.text(
                (x + 8, DESCRIPTION_START_Y + line_index * LABEL_LINE_HEIGHT),
                line,
                font=label_font,
                fill=surface.theme.ink,
            )
    desc_bottom = _description_bottom(surface, metrics, scene)
    points_start = desc_bottom + DESCRIPTION_GAP
    points_end = height - POINTS_BOTTOM_MARGIN
    points = list(scene.content["points"])
    visible = revealed_point_count(len(points), progress)
    rows = _layout_point_rows(
        _plan_point_rows(surface, metrics, points, visible),
        points_start=points_start,
        points_end=points_end,
    )
    body_font = surface.font("body")
    for row in rows:
        for line_index, line in enumerate(row.label_lines):
            surface.draw.text(
                (metrics.label_x, row.y + line_index * LABEL_LINE_HEIGHT),
                line,
                font=label_font,
                fill=surface.theme.muted_ink,
            )
        body_top = row.y + len(row.label_lines) * LABEL_LINE_HEIGHT + 2
        for line_index, line in enumerate(row.left_lines):
            surface.draw.text(
                (metrics.left_x + 2, body_top + line_index * BODY_LINE_HEIGHT),
                line,
                font=body_font,
                fill=surface.theme.ink,
            )
        for line_index, line in enumerate(row.right_lines):
            surface.draw.text(
                (metrics.right_x + 2, body_top + line_index * BODY_LINE_HEIGHT),
                line,
                font=body_font,
                fill=surface.theme.ink,
            )
    return surface.finish()
