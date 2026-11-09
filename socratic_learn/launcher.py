"""Interactive host selection and learning-process lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import TextIO

from .config import LauncherConfig, load_config, save_config
from .errors import FilesystemError, UsageError
from .hosts import AgentName, DetectedHost, command_for, detect_hosts
from .sources.ingest import ingest_source
from .sources.model import SourceRequest
from .sources.payload import build_source_study_payload
from .windows_security import (
    safe_regular_windows_file,
    trusted_windows_powershell,
)
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
    source: SourceRequest | None = None


def _safe_windows_host_argv(
    executable: str,
    argv: tuple[str, ...],
    environ: Mapping[str, str] | None,
) -> tuple[str, ...]:
    if os.name != "nt" or Path(executable).suffix.lower() not in {".cmd", ".bat"}:
        return argv
    batch = safe_regular_windows_file(
        Path(executable),
        label="detected Windows batch shim",
    )
    counterpart = batch.with_suffix(".ps1")
    if not counterpart.exists():
        raise UsageError(
            "a Windows batch host requires a sibling PowerShell counterpart",
            path=batch,
            remediation=f"install a regular non-linked shim at {counterpart}",
        )
    script = safe_regular_windows_file(
        counterpart,
        label="PowerShell counterpart",
    )
    powershell = trusted_windows_powershell(environ)
    return (
        str(powershell),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *argv[1:],
    )


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

    goal = options.goal
    if goal is None:
        prompt = (
            "What do you want to be able to do with this source?"
            if options.source is not None
            else "What do you want to learn? "
        )
        goal = input_fn(prompt)
    if not goal.strip():
        raise UsageError(
            "a learning goal is required",
            remediation="provide a non-empty learning goal",
        )

    home = launcher_home(environ)
    config_path = home / "config.json"
    config = load_config(config_path)

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

    payload: str | None = None
    if options.source is not None:
        ingested = ingest_source(workspace.records, options.source)
        bundle_path = ingested.bundle_path.resolve()
        payload = build_source_study_payload(
            learner_goal=goal,
            index_path=bundle_path / "index.md",
            metadata_path=bundle_path / "metadata.json",
        )

    host = detected[selected]
    argv = command_for(
        host.adapter,
        host.executable,
        workspace.protocol,
        goal,
        source_study_payload=payload,
    )
    argv = _safe_windows_host_argv(host.executable, argv, environ)

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
