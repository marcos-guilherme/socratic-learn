from dataclasses import dataclass


def _hex_color(value: str) -> tuple[int, int, int]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


@dataclass(frozen=True)
class Theme:
    background: tuple[int, int, int]
    paper: tuple[int, int, int]
    ink: tuple[int, int, int]
    muted_ink: tuple[int, int, int]
    coral: tuple[int, int, int]
    gold: tuple[int, int, int]
    green: tuple[int, int, int]
    blue: tuple[int, int, int]
    border: tuple[int, int, int]


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
