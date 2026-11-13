# README Socrates Banner Design

## Status

Approved in conversation on 2026-11-12. Written specification awaiting final
user review.

## Purpose

Create a polished hero banner for the Socratic Learn README. The image should
make the project memorable without making it look childish, game-like, or
limited to mathematics and AI.

## Composition

The banner is a wide 1600 by 560 pixel image.

The left side contains the exact text:

```text
Socratic Learn
Learn anything. Prove it by doing.
```

The right side contains a pixel-art interpretation of a classical Socrates
bust in a thoughtful pose. The figure should look sculptural and serious,
with a hand near the chin and the gaze directed toward the title area. It
must not look like a cartoon character, game avatar, mascot, or photorealistic
person.

A restrained trail of square pixels suggests the sequence:

```text
question → attempt → evidence
```

The sequence is visual rather than written in small text. It must support the
composition without competing with the title or face.

## Visual direction

The design uses:

1. a charcoal background;
2. limestone and muted gray tones for the bust;
3. one restrained teal accent for the reasoning trail;
4. crisp pixel edges mixed with editorial negative space;
5. subtle geometric structure rather than decorative scenery.

The design avoids robots, brains, speech bubbles, classroom props, gradients,
glow, cartoon expressions, and busy retro-game interfaces.

## Production approach

Generate the Socrates artwork without typography, leaving deliberate negative
space on the left. Add the title and tagline afterward with Pillow so the text
is exact, sharp, and reproducible. Do not rely on an image model to spell
product copy.

The final asset is saved as:

```text
docs/assets/socratic-learn-hero.png
```

The README places it directly below the `# Socratic Learn` heading and before
the current product promise.

## Accessibility

README alt text:

```text
Pixel-art Socrates thinking beside the Socratic Learn name and the line
Learn anything. Prove it by doing.
```

The composition must remain understandable without color. Teal is an accent,
not the sole carrier of meaning.

## Acceptance criteria

1. The output is exactly 1600 by 560 pixels.
2. Product text is spelled exactly as approved.
3. Text remains readable when the README is viewed at typical GitHub width.
4. Socrates is recognizable as a classical philosopher in a thoughtful pose.
5. The result feels editorial and professional rather than childish.
6. Pixel styling is deliberate and restrained.
7. The image contains no unrelated logos, signatures, watermarks, or text.
8. The README references the asset with the approved alt text.
