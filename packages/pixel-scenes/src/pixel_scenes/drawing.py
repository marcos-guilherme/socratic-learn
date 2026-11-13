from __future__ import annotations

from collections.abc import Iterable

from PIL import Image, ImageDraw, ImageFont

from .errors import LayoutError
from .model import Canvas
from .theme import COZY_CLASSROOM, Color, Theme


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
        fill: Color | None = None,
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
        fill: Color | None = None,
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
        fill: Color,
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
