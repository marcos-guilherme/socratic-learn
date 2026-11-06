"""Interactive host selection and learning-process lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TextIO

from .config import LauncherConfig, load_config, save_config
from .errors import FilesystemError, UsageError
from .hosts import AgentName, DetectedHost, command_for, detect_hosts
from .workspace import (
    launcher_home,
    prepare_here_workspace,
    prepare_personal_workspace,
)


@dataclass(frozen=True)
class LaunchOptions:
    goal: str | None
    agent: AgentName | None
    here: bool
    cwd: Path


def _prompt_for_agent(
    detected: Mapping[AgentName, DetectedHost],
    *,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> AgentName:
    names = tuple(detected)
    output.write("Available agents:\n")
    for number, name in enumerate(names, start=1):
        output.write(f"{number}. {name}\n")

    while True:
        answer = input_fn("Select an agent by number: ")
        try:
            index = int(answer)
        except ValueError:
            continue
        if 1 <= index <= len(names) and answer.strip() == str(index):
            return names[index - 1]


def run_learning(
    options: LaunchOptions,
    *,
    input_fn: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
    which: Callable[[str], str | None] = shutil.which,
    run_process: Callable[..., subprocess.CompletedProcess[object]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Select an installed host, prepare a workspace, and run the child."""
    detected = detect_hosts(which)
    if not detected:
        raise UsageError(
            "no compatible agent was found",
            remediation="install Pi, Claude Code, or Antigravity and retry",
        )

    home = launcher_home(environ)
    config_path = home / "config.json"
    config = load_config(config_path)

    goal = options.goal
    if goal is None:
        goal = input_fn("What do you want to learn? ")
    if not goal.strip():
        raise UsageError(
            "a learning goal is required",
            remediation="provide a non-empty learning goal",
        )

    selected = options.agent
    if selected is not None:
        if selected not in detected:
            raise UsageError(
                f"requested agent '{selected}' was not detected",
                remediation="choose an installed compatible agent",
            )
    elif config.default_agent in detected:
        selected = config.default_agent
    else:
        if config.default_agent is not None:
            output.write(
                f"Saved agent '{config.default_agent}' is no longer available.\n"
            )
        selected = _prompt_for_agent(
            detected,
            input_fn=input_fn,
            output=output,
        )
        save_config(config_path, LauncherConfig(default_agent=selected))

    workspace = (
        prepare_here_workspace(options.cwd)
        if options.here
        else prepare_personal_workspace(home)
    )
    host = detected[selected]
    argv = command_for(host.adapter, host.executable, workspace.protocol, goal)

    try:
        result = run_process(list(argv), cwd=workspace.root, check=False)
    except KeyboardInterrupt:
        return 130
    except FileNotFoundError as error:
        raise FilesystemError(
            f"agent '{selected}' executable disappeared before launch",
            path=host.executable,
            remediation="restore the executable or select another agent",
        ) from error
    return result.returncode
