from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).parents[1]
ASSET = ROOT / "docs" / "assets" / "socratic-learn-hero.png"
README = ROOT / "README.md"
ALT = (
    "Pixel-art Socrates thinking beside the Socratic Learn name and the line "
    "Learn anything. Prove it by doing."
)


def test_readme_hero_is_expected_png_size():
    data = ASSET.read_bytes()

    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    assert struct.unpack(">II", data[16:24]) == (1600, 560)


def test_readme_references_hero_after_title():
    readme = README.read_text(encoding="utf-8")
    reference = f"![{ALT}](docs/assets/socratic-learn-hero.png)"

    assert reference in readme
    assert readme.index("# Socratic Learn") < readme.index(reference)
    assert readme.index(reference) < readme.index(
        "**Turn any AI agent into a tutor that checks whether you actually learned.**"
    )
