"""Pure host detection and argument-vector construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

READ_MODE_DELIMITER = "\n\n--- SOCRATIC LEARN SOURCE STUDY ---\n"

AgentName = Literal["pi", "claude", "antigravity"]


@dataclass(frozen=True)
class HostAdapter:
    name: AgentName
    executable_names: tuple[str, ...]
    build_argv: Callable[..., tuple[str, ...]]


@dataclass(frozen=True)
class DetectedHost:
    adapter: HostAdapter
    executable: str


def _pi(
    executable: str,
    protocol: Path,
    goal: str,
    source_study_payload: str | None = None,
) -> tuple[str, ...]:
    final_prompt = source_study_payload if source_study_payload is not None else goal
    return executable, "--append-system-prompt", str(protocol), final_prompt


def _claude(
    executable: str,
    protocol: Path,
    goal: str,
    source_study_payload: str | None = None,
) -> tuple[str, ...]:
    final_prompt = source_study_payload if source_study_payload is not None else goal
    return executable, "--append-system-prompt-file", str(protocol), final_prompt


def _antigravity(
    executable: str,
    protocol: Path,
    goal: str,
    source_study_payload: str | None = None,
) -> tuple[str, ...]:
    if source_study_payload is not None:
        bootstrap = (
            f"Before responding, read and follow the Socratic Learn protocol at "
            f"{protocol}.{READ_MODE_DELIMITER}{source_study_payload}"
        )
    else:
        bootstrap = (
            f"Before responding, read and follow the Socratic Learn protocol at "
            f"{protocol}. The learner's initial objective is: {goal}"
        )
    return executable, "--prompt-interactive", bootstrap


ADAPTERS: Mapping[AgentName, HostAdapter] = MappingProxyType(
    {
        "pi": HostAdapter("pi", ("pi",), _pi),
        "claude": HostAdapter("claude", ("claude",), _claude),
        "antigravity": HostAdapter("antigravity", ("agy",), _antigravity),
    }
)


def detect_hosts(
    which: Callable[[str], str | None],
) -> dict[AgentName, DetectedHost]:
    """Detect each adapter's first available executable in canonical order."""
    detected: dict[AgentName, DetectedHost] = {}
    for name, adapter in ADAPTERS.items():
        for executable_name in adapter.executable_names:
            executable = which(executable_name)
            if executable is not None:
                detected[name] = DetectedHost(adapter, executable)
                break
    return detected


def command_for(
    adapter: HostAdapter,
    executable: str,
    protocol: Path,
    goal: str,
    source_study_payload: str | None = None,
) -> tuple[str, ...]:
    """Build an argument vector without invoking a process."""
    return adapter.build_argv(executable, protocol, goal, source_study_payload)
