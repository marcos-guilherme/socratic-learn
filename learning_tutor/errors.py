"""Domain errors with stable command-line exit codes."""

from __future__ import annotations

from pathlib import Path


class LearningTutorError(Exception):
    """Base class for expected, actionable command failures."""

    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        path: str | Path | None = None,
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = path
        self.remediation = remediation

    def __str__(self) -> str:
        details = [self.message]
        if self.path is not None:
            details.append(f"path: {self.path}")
        if self.remediation is not None:
            details.append(f"remediation: {self.remediation}")
        return "; ".join(details)


class UsageError(LearningTutorError):
    """The command line does not match the supported interface."""

    exit_code = 2


class CollisionError(LearningTutorError):
    """A requested write would replace existing user content."""

    exit_code = 3


class IntegrityError(LearningTutorError):
    """Required package or generated content is unavailable or invalid."""

    exit_code = 4


class FilesystemError(LearningTutorError):
    """A filesystem operation failed."""

    exit_code = 5
