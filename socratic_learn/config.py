"""Validated, non-secret launcher preferences."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
from typing import Literal

from socratic_learn.errors import IntegrityError


AgentName = Literal["pi", "claude", "antigravity"]
_AGENT_NAMES = ("pi", "claude", "antigravity")
_CONFIG_KEYS = {"schema_version", "default_agent"}
_REMEDIATION = "move the file aside and rerun socratic"


@dataclass(frozen=True)
class LauncherConfig:
    default_agent: AgentName | None = None


def _invalid_config(path: Path, message: str) -> IntegrityError:
    return IntegrityError(message, path=path, remediation=_REMEDIATION)


def _validated_default_agent(value: object, path: Path) -> AgentName | None:
    if value is None:
        return None
    if type(value) is not str or value not in _AGENT_NAMES:
        raise _invalid_config(path, "launcher configuration has an invalid agent")
    return value


def load_config(path: Path) -> LauncherConfig:
    """Load an exact schema-one launcher configuration."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LauncherConfig()

    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _invalid_config(path, "launcher configuration is not valid JSON") from error

    if type(document) is not dict or set(document) != _CONFIG_KEYS:
        raise _invalid_config(path, "launcher configuration has unexpected keys")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise _invalid_config(path, "launcher configuration schema is not supported")

    return LauncherConfig(
        default_agent=_validated_default_agent(document["default_agent"], path)
    )


def _reject_symlink(path: Path, description: str) -> None:
    if path.is_symlink():
        raise _invalid_config(path, f"{description} must not be a symbolic link")


def save_config(path: Path, config: LauncherConfig) -> None:
    """Atomically save a schema-one launcher configuration."""
    default_agent = _validated_default_agent(config.default_agent, path)
    parent = path.parent
    _reject_symlink(parent, "launcher configuration parent")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink(parent, "launcher configuration parent")
    _reject_symlink(path, "launcher configuration destination")

    payload = json.dumps(
        {"schema_version": 1, "default_agent": default_agent},
        indent=2,
        sort_keys=True,
    ) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    temporary: Path | None = None
    descriptor: int | None = None
    try:
        while temporary is None:
            candidate = parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
            try:
                descriptor = os.open(candidate, flags, 0o600)
            except FileExistsError:
                continue
            temporary = candidate

        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
