"""Deprecated compatibility imports for Socratic Learn."""

from socratic_learn import (
    MANIFEST_SCHEMA_VERSION,
    PRODUCT_ID,
    PROTOCOL_VERSION,
    TARGETS,
)
from socratic_learn.errors import LearningTutorError

__all__ = [
    "LearningTutorError",
    "MANIFEST_SCHEMA_VERSION",
    "PRODUCT_ID",
    "PROTOCOL_VERSION",
    "TARGETS",
]
