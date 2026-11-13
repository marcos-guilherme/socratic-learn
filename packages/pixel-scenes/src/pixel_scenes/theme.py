from dataclasses import dataclass

# Pillow RGB tuples used for Theme palette values and drawing fill colors.
Color = tuple[int, int, int]


def _hex_color(value: str) -> Color:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


@dataclass(frozen=True)
class Theme:
    background: Color
    paper: Color
    ink: Color
    muted_ink: Color
    coral: Color
    gold: Color
    green: Color
    blue: Color
    border: Color


COZY_CLASSROOM = Theme(
    background=_hex_color("#F7D9A6"),
    paper=_hex_color("#FFF0CF"),
    ink=_hex_color("#51362E"),
    muted_ink=_hex_color("#76584B"),
    coral=_hex_color("#E96F5B"),
    gold=_hex_color("#F2B35B"),
    green=_hex_color("#6FAE83"),
    blue=_hex_color("#79B7B0"),
    border=_hex_color("#6D4B3A"),
)
