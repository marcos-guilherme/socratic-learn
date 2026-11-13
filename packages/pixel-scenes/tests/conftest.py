from __future__ import annotations

import pytest


@pytest.fixture
def concept_data() -> dict[str, object]:
    return {
        "schema_version": "1",
        "template": "concept-card",
        "theme": "cozy-classroom",
        "canvas": {"width": 960, "height": 540},
        "content": {
            "title": "Gradient descent",
            "summary": "Walk downhill one careful step at a time.",
            "key_fact": "Smaller loss means a better fit.",
        },
        "animation": {"duration_seconds": 4, "fps": 12},
        "accessibility": {
            "description": "A marker moves down a stepped hill."
        },
        "seed": 0,
    }
