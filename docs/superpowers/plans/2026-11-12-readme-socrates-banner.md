# README Socrates Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a professional pixel-art Socrates banner and place it at the top of the Socratic Learn README.

**Architecture:** Generate the artwork without text, preserving negative space on the left. Composite exact product typography with Pillow, save the final PNG under `docs/assets/`, and reference it from the README. A standard-library test protects dimensions, path, and alt text.

**Tech Stack:** Cursor image generation, Python 3.11, Pillow, PNG, pytest.

## Global Constraints

- Final asset path: `docs/assets/socratic-learn-hero.png`.
- Final dimensions: exactly 1600 by 560 pixels.
- Exact title: `Socratic Learn`.
- Exact tagline: `Learn anything. Prove it by doing.`
- The right side shows a serious pixel-art interpretation of a classical Socrates bust in a thoughtful pose.
- The left side keeps clear negative space for product text.
- Palette: charcoal background, limestone and muted gray bust, restrained teal accent.
- No robots, brains, speech bubbles, classroom props, gradients, glow, signatures, watermarks, or unrelated text.
- Pixel styling is deliberate and restrained rather than cartoon-like.
- README alt text is exactly `Pixel-art Socrates thinking beside the Socratic Learn name and the line Learn anything. Prove it by doing.`
- Keep the two unrelated untracked IOI documents untouched.

---

### Task 1: Generate, verify, and integrate the README banner

**Files:**
- Create: `docs/assets/socratic-learn-hero.png`
- Create: `tests/test_readme_hero.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the approved visual specification and generated text-free artwork.
- Produces: a stable README asset referenced by repository-relative path.

- [ ] **Step 1: Write the failing repository contract**

Create `tests/test_readme_hero.py`:

```python
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
```

- [ ] **Step 2: Run the contract and verify RED**

Run:

```powershell
python -m pytest tests/test_readme_hero.py -q
```

Expected: failure because `docs/assets/socratic-learn-hero.png` does not exist.

- [ ] **Step 3: Generate the text-free base artwork**

Generate a 1600 by 560 image from this prompt:

```text
Wide editorial banner, 1600 by 560. Charcoal black background. On the right,
a serious pixel-art interpretation of a classical marble bust of Socrates in
a thoughtful pose, hand near chin, gaze turned toward the empty left side.
Limestone and muted gray stone palette, restrained teal square-pixel reasoning
trail around the bust. Sophisticated contemporary research-publication art
direction. Crisp deliberate pixel edges mixed with generous negative space.
Leave the entire left 55 percent visually quiet for typography. No text,
letters, logos, watermark, robots, brains, speech bubbles, classroom objects,
glow, gradient, cartoon style, game interface, or decorative scenery.
```

Save the selected result temporarily outside the repository until typography
is added.

- [ ] **Step 4: Composite exact typography and save the final PNG**

Use Pillow to resize or crop the base art to 1600 by 560, then draw:

```text
Socratic Learn
Learn anything. Prove it by doing.
```

Place both lines inside the quiet left region with at least 100 pixels of outer
padding. Use a clean editorial sans-serif font, off-white title, muted gray
tagline, and no synthetic effects. Save as RGB or RGBA PNG at
`docs/assets/socratic-learn-hero.png`.

- [ ] **Step 5: Add the README reference**

Insert immediately after `# Socratic Learn`:

```markdown
![Pixel-art Socrates thinking beside the Socratic Learn name and the line Learn anything. Prove it by doing.](docs/assets/socratic-learn-hero.png)
```

- [ ] **Step 6: Run automated verification**

Run:

```powershell
python -m pytest tests/test_readme_hero.py -q
python tests/validate_repository.py
git diff --check
```

Expected: two hero tests pass, repository validation passes, and diff check is
clean.

- [ ] **Step 7: Inspect the rendered README asset**

Open `docs/assets/socratic-learn-hero.png` and verify:

1. title and tagline are exact and readable;
2. the bust is recognizable as Socrates and looks thoughtful;
3. the composition remains professional at README width;
4. no generated text, watermark, or unrelated symbol remains;
5. pixel styling is restrained;
6. the title area does not compete with the bust.

- [ ] **Step 8: Commit the banner**

```powershell
git add README.md docs/assets/socratic-learn-hero.png tests/test_readme_hero.py
git commit -m "docs: add Socrates README banner"
```
