# One-Command Learning Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a globally installable `socratic` command that detects an existing Pi, Claude Code, or Antigravity CLI and starts an interactive Socratic Learn session.

**Architecture:** Keep `python -m socratic_learn` as the existing administrative interface and add a separate console entry point for the learner-facing launcher. The launcher uses packaged deterministic protocol resources, a private managed home, small host adapters, and channel-aware release management; native artifacts and the Python package are produced from the same source.

**Tech Stack:** Python 3.11+ standard library, `unittest`, Hatchling for PEP 517 packaging, PyInstaller for native artifacts, PowerShell and POSIX shell bootstrap installers, GitHub Actions.

## Global Constraints

- The public command is exactly `socratic`.
- The first launcher targets are exactly `pi`, `claude`, and `antigravity`; Antigravity's executable is `agy`.
- The launcher reuses host authentication and never reads, requests, transmits, or stores provider credentials.
- The default private root is `~/.socratic-learn/`; tests may override it only through `SOCRATIC_LEARN_HOME`.
- `python -m socratic_learn` without a subcommand must retain its current usage error.
- Existing `build`, `export`, `install`, and `doctor` behavior, deterministic artifacts, ownership receipts, and no-overwrite guarantees remain release gates.
- Native release artifacts initially support x86-64 Windows, Linux, and macOS. Unsupported architectures receive the exact `pipx install socratic-learn` fallback.
- Native artifacts are unsigned in the first release and every installer must disclose SmartScreen or Gatekeeper warnings before download.
- SHA-256 verification is mandatory before installing or updating a native executable.
- Native update failure must leave the previous executable usable.
- PyPI installs are managed by `pipx`; `socratic update` and `socratic uninstall` must not mutate a Python environment.
- User goals entered as command arguments may enter shell history; the no-argument prompt is the documented privacy-preserving default.

---

## File Structure

New focused modules:

- `socratic_learn/resources.py`: read packaged protocol and template bytes and materialize an installer-compatible temporary source root.
- `socratic_learn/config.py`: validate and atomically persist non-secret launcher preferences.
- `socratic_learn/hosts.py`: host names, executable detection, and argument construction only.
- `socratic_learn/workspace.py`: prepare the personal or current-directory managed learning workspace.
- `socratic_learn/launcher.py`: select a host, obtain a goal, and own the child process lifecycle.
- `socratic_learn/cli.py`: parse the `socratic` console command and route launcher versus administrative operations.
- `socratic_learn/release.py`: parse signed-off release metadata, verify downloads, and select an artifact.
- `socratic_learn/self_manage.py`: installation-channel-aware update and uninstall behavior.
- `scripts/install.ps1` and `scripts/install.sh`: no-admin native bootstrap installers.
- `.github/workflows/release.yml`: build, test, hash, package, and publish release artifacts.

Tests mirror those boundaries in `tests/test_resources.py`, `tests/test_config.py`,
`tests/test_hosts.py`, `tests/test_workspace.py`, `tests/test_launcher.py`,
`tests/test_console_cli.py`, `tests/test_release.py`, and
`tests/test_self_manage.py`.

---

### Task 1: PEP 517 Package and Embedded Distribution Resources

**Files:**
- Create: `pyproject.toml`
- Create: `socratic_learn/resources.py`
- Create: `socratic_learn/cli.py`
- Modify: `socratic_learn/__init__.py`
- Create: `tests/test_resources.py`
- Create: `tests/test_packaging.py`

**Interfaces:**
- Produces: `socratic_learn.__version__: str`
- Produces: `resource_bytes(relative: str) -> bytes`
- Produces: `packaged_distribution_root() -> ContextManager[Path]`
- Produces: `socratic_learn.cli.main(argv: Sequence[str] | None = None) -> int`
- Produces: `socratic_learn.cli.entry_point() -> NoReturn`

- [ ] **Step 1: Write failing resource and packaging tests**

```python
# tests/test_resources.py
from __future__ import annotations

import json
import unittest
from pathlib import Path

from socratic_learn.resources import packaged_distribution_root, resource_bytes


class PackagedResourceTests(unittest.TestCase):
    def test_packaged_distribution_matches_checked_in_dist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (root / "dist/manifest.json").read_bytes(),
            resource_bytes("manifest.json"),
        )
        self.assertEqual(
            (root / "dist/socratic-learn.prompt.md").read_bytes(),
            resource_bytes("socratic-learn.prompt.md"),
        )

    def test_materialized_root_has_installer_layout(self) -> None:
        with packaged_distribution_root() as root:
            manifest = json.loads((root / "dist/manifest.json").read_text("utf-8"))
            self.assertEqual("socratic-learn", manifest["product"])
            self.assertTrue((root / "dist/socratic-learn.prompt.md").is_file())

    def test_unknown_resource_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resource_bytes("../LICENSE")
```

```python
# tests/test_packaging.py
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


class PackagingTests(unittest.TestCase):
    def test_wheel_contains_console_entry_and_protocol(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            subprocess.run(
                [sys.executable, "-m", "build", "--wheel", "--outdir", temporary],
                cwd=root,
                check=True,
            )
            wheel = next(Path(temporary).glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                self.assertIn(
                    "socratic_learn/data/socratic-learn.prompt.md",
                    names,
                )
                entry_points = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                self.assertIn(
                    "socratic = socratic_learn.cli:entry_point",
                    archive.read(entry_points).decode("utf-8"),
                )
```

- [ ] **Step 2: Run the focused tests and verify the expected failures**

Run:

```powershell
python -m unittest tests.test_resources tests.test_packaging -v
```

Expected: import failure for `socratic_learn.resources` and no `pyproject.toml`.

- [ ] **Step 3: Add package metadata and a compatibility console stub**

Create `pyproject.toml` with the complete initial packaging contract:

```toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "socratic-learn"
dynamic = ["version"]
description = "A portable, evidence-aware Socratic protocol for learning anything."
readme = "README.md"
requires-python = ">=3.11"
license = { file = "LICENSE" }
authors = [{ name = "Marcos Guilherme" }]
classifiers = [
  "Development Status :: 3 - Alpha",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3 :: Only",
  "Topic :: Education",
]
dependencies = []

[project.optional-dependencies]
build = [
  "build>=1.2,<2",
  "pyinstaller>=6.10,<7",
]

[project.scripts]
socratic = "socratic_learn.cli:entry_point"

[project.urls]
Homepage = "https://github.com/marcos-guilherme/socratic-learn"
Repository = "https://github.com/marcos-guilherme/socratic-learn"
Issues = "https://github.com/marcos-guilherme/socratic-learn/issues"

[tool.hatch.version]
path = "socratic_learn/__init__.py"

[tool.hatch.build.targets.sdist]
include = [
  "/LICENSE",
  "/README.md",
  "/dist",
  "/templates",
  "/socratic_learn",
  "/learning_tutor",
]

[tool.hatch.build.targets.wheel]
packages = ["socratic_learn", "learning_tutor"]

[tool.hatch.build.targets.wheel.force-include]
"dist/manifest.json" = "socratic_learn/data/manifest.json"
"dist/socratic-learn.prompt.md" = "socratic_learn/data/socratic-learn.prompt.md"
"templates/learner-profile.md" = "socratic_learn/data/templates/learner-profile.md"
"templates/learning-goal.md" = "socratic_learn/data/templates/learning-goal.md"
"templates/progress.md" = "socratic_learn/data/templates/progress.md"
"templates/session-log.md" = "socratic_learn/data/templates/session-log.md"
```

Add `__version__ = "0.1.0"` to `socratic_learn/__init__.py` without changing
the protocol or manifest versions.

Create the temporary compatibility entry point:

```python
# socratic_learn/cli.py
from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn

from .__main__ import main as administrative_main


def main(argv: Sequence[str] | None = None) -> int:
    return administrative_main(argv)


def entry_point() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    entry_point()
```

- [ ] **Step 4: Implement strict packaged resource loading**

```python
# socratic_learn/resources.py
from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path, PurePosixPath

from .errors import IntegrityError

_ALLOWED = {
    "manifest.json",
    "socratic-learn.prompt.md",
    "templates/learner-profile.md",
    "templates/learning-goal.md",
    "templates/progress.md",
    "templates/session-log.md",
}


def resource_bytes(relative: str) -> bytes:
    if relative not in _ALLOWED or PurePosixPath(relative).is_absolute():
        raise ValueError(f"unsupported packaged resource: {relative}")
    packaged = files("socratic_learn").joinpath("data", *PurePosixPath(relative).parts)
    if packaged.is_file():
        return packaged.read_bytes()
    repository = Path(__file__).resolve().parents[1]
    fallback = (
        repository / "dist" / relative
        if not relative.startswith("templates/")
        else repository / relative
    )
    try:
        return fallback.read_bytes()
    except OSError as error:
        raise IntegrityError(
            "packaged resource is unavailable",
            path=relative,
            remediation="reinstall socratic-learn",
        ) from error


@contextmanager
def packaged_distribution_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="socratic-learn-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        dist.mkdir()
        (dist / "manifest.json").write_bytes(resource_bytes("manifest.json"))
        (dist / "socratic-learn.prompt.md").write_bytes(
            resource_bytes("socratic-learn.prompt.md")
        )
        yield root
```

- [ ] **Step 5: Install build tooling and rerun focused tests**

Run:

```powershell
python -m pip install -e ".[build]"
python -m unittest tests.test_resources tests.test_packaging -v
```

Expected: all focused tests pass and the built wheel contains the protocol.

- [ ] **Step 6: Run the existing CLI and deterministic build tests**

Run:

```powershell
python -m unittest tests.test_cli tests.test_build tests.test_manifest -v
python -m socratic_learn build
git diff --exit-code -- dist
```

Expected: all tests pass and rebuilding does not change `dist/`.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml socratic_learn/__init__.py socratic_learn/cli.py socratic_learn/resources.py tests/test_resources.py tests/test_packaging.py
git commit -m "build: package the socratic command"
```

---

### Task 2: Launcher Configuration and Host Adapter Contract

**Files:**
- Create: `socratic_learn/config.py`
- Create: `socratic_learn/hosts.py`
- Create: `tests/test_config.py`
- Create: `tests/test_hosts.py`

**Interfaces:**
- Produces: `AgentName = Literal["pi", "claude", "antigravity"]`
- Produces: `LauncherConfig(default_agent: AgentName | None)`
- Produces: `load_config(path: Path) -> LauncherConfig`
- Produces: `save_config(path: Path, config: LauncherConfig) -> None`
- Produces: `HostAdapter(name, executable_names, build_argv)`
- Produces: `DetectedHost(adapter: HostAdapter, executable: str)`
- Produces: `detect_hosts(which: Callable[[str], str | None]) -> dict[AgentName, DetectedHost]`
- Produces: `command_for(adapter, executable, protocol, goal) -> tuple[str, ...]`

- [ ] **Step 1: Write failing configuration tests**

```python
# tests/test_config.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from socratic_learn.config import LauncherConfig, load_config, save_config
from socratic_learn.errors import IntegrityError


class LauncherConfigTests(unittest.TestCase):
    def test_missing_config_has_no_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(
                LauncherConfig(default_agent=None),
                load_config(Path(temporary) / "config.json"),
            )

    def test_round_trip_uses_schema_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            save_config(path, LauncherConfig(default_agent="pi"))
            self.assertEqual(LauncherConfig(default_agent="pi"), load_config(path))
            self.assertIn('"schema_version": 1', path.read_text("utf-8"))

    def test_corrupt_config_is_preserved_and_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(IntegrityError):
                load_config(path)
            self.assertEqual("{broken", path.read_text("utf-8"))
```

- [ ] **Step 2: Write failing adapter tests**

```python
# tests/test_hosts.py
from __future__ import annotations

import unittest
from pathlib import Path

from socratic_learn.hosts import ADAPTERS, command_for, detect_hosts


class HostAdapterTests(unittest.TestCase):
    def test_detection_uses_supported_executable_names(self) -> None:
        found = {
            "pi": "C:/bin/pi.exe",
            "claude": "C:/bin/claude.exe",
            "agy": "C:/bin/agy.exe",
        }
        detected = detect_hosts(found.get)
        self.assertEqual(["pi", "claude", "antigravity"], list(detected))

    def test_commands_are_argument_arrays_with_protocol_and_goal(self) -> None:
        protocol = Path("C:/Learning Home/protocol.md")
        goal = "learn cafés and probability"
        for name, executable in (
            ("pi", "pi"),
            ("claude", "claude"),
            ("antigravity", "agy"),
        ):
            with self.subTest(name=name):
                argv = command_for(ADAPTERS[name], executable, protocol, goal)
                self.assertEqual(executable, argv[0])
                self.assertTrue(any(str(protocol) in value for value in argv[1:]))
                self.assertTrue(any(goal in value for value in argv[1:]))
```

- [ ] **Step 3: Run tests and verify imports fail**

Run:

```powershell
python -m unittest tests.test_config tests.test_hosts -v
```

Expected: import failures for `config` and `hosts`.

- [ ] **Step 4: Implement exact-key configuration validation and atomic save**

Implement schema:

```python
{"schema_version": 1, "default_agent": "pi" | "claude" | "antigravity" | None}
```

`save_config` must create the parent with mode `0o700`, reject a symlinked
parent or destination, write UTF-8 JSON to an `O_CREAT | O_EXCL` temporary file
with mode `0o600`, flush and `fsync`, then publish with `os.replace`. On any
pre-publication failure it removes only the temporary path it created.
`load_config` must reject booleans, unknown keys, wrong schema versions, and
unknown agent names with `IntegrityError(path=path, remediation="move the file aside and rerun socratic")`.

- [ ] **Step 5: Implement immutable host adapters**

Use this adapter shape:

```python
AgentName = Literal["pi", "claude", "antigravity"]

@dataclass(frozen=True)
class HostAdapter:
    name: AgentName
    executable_names: tuple[str, ...]
    build_argv: Callable[[str, Path, str], tuple[str, ...]]
```

Define commands as:

```python
def _pi(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    return executable, "--append-system-prompt", str(protocol), goal


def _claude(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    return executable, "--append-system-prompt-file", str(protocol), goal


def _antigravity(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    bootstrap = (
        f"Before responding, read and follow the Socratic Learn protocol at "
        f"{protocol}. The learner's initial objective is: {goal}"
    )
    return executable, "--prompt-interactive", bootstrap
```

`detect_hosts` must preserve the canonical `pi`, `claude`, `antigravity`
order, call the injected `which` function for each executable name, and return
only the first executable found for each adapter. Store the resolved executable
on a separate `DetectedHost(adapter, executable)` dataclass so the immutable
adapter registry remains process-independent.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m unittest tests.test_config tests.test_hosts -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/config.py socratic_learn/hosts.py tests/test_config.py tests/test_hosts.py
git commit -m "feat: detect supported learning agents"
```

---

### Task 3: Personal and Current-Directory Learning Workspaces

**Files:**
- Create: `socratic_learn/workspace.py`
- Modify: `socratic_learn/resources.py`
- Test: `tests/test_workspace.py`
- Modify: `tests/test_install.py`

**Interfaces:**
- Consumes: `packaged_distribution_root`, `resource_bytes`, `plan_install`, `apply_install`, `load_receipt`
- Produces: `LearningWorkspace(root: Path, protocol: Path, records: Path)`
- Produces: `launcher_home(environ: Mapping[str, str] | None = None) -> Path`
- Produces: `prepare_personal_workspace(home: Path) -> LearningWorkspace`
- Produces: `prepare_here_workspace(project: Path) -> LearningWorkspace`

- [ ] **Step 1: Write failing workspace tests**

```python
# tests/test_workspace.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from socratic_learn.workspace import (
    launcher_home,
    prepare_here_workspace,
    prepare_personal_workspace,
)


class WorkspaceTests(unittest.TestCase):
    def test_home_override_is_test_only_boundary(self) -> None:
        self.assertEqual(
            Path("C:/isolated"),
            launcher_home({"SOCRATIC_LEARN_HOME": "C:/isolated"}),
        )

    def test_personal_workspace_is_idempotent_and_preserves_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            first = prepare_personal_workspace(home)
            profile = first.records / "learner-profile.md"
            profile.write_text("private learner evidence\n", encoding="utf-8")
            second = prepare_personal_workspace(home)
            self.assertEqual(first, second)
            self.assertEqual("private learner evidence\n", profile.read_text("utf-8"))

    def test_here_mode_reuses_existing_target_without_retargeting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            first = prepare_here_workspace(project)
            second = prepare_here_workspace(project)
            self.assertEqual(first.protocol, second.protocol)
            self.assertEqual(
                project / ".socratic-learn/socratic-learn.prompt.md",
                second.protocol,
            )
```

- [ ] **Step 2: Run tests and verify the workspace module is missing**

Run:

```powershell
python -m unittest tests.test_workspace -v
```

Expected: import failure for `socratic_learn.workspace`.

- [ ] **Step 3: Extend resources with template bytes**

Keep the strict allowlist from Task 1 and expose templates only through
`resource_bytes("templates/<name>.md")`. Add a test proving
`templates/learner-profile.md` in the wheel equals the repository template.

- [ ] **Step 4: Implement workspace preparation with existing transactions**

Use this data contract:

```python
@dataclass(frozen=True)
class LearningWorkspace:
    root: Path
    protocol: Path
    records: Path
```

`prepare_personal_workspace(home)` must:

1. reject a symlinked or non-directory `home`;
2. create `home/learning` without administrator access;
3. install `generic` there when no receipt exists;
4. otherwise load the receipt, reuse its recorded target, and execute an
   update through `plan_install(..., update=True)` and `apply_install(...)`;
5. create `learner-profile.md`, `learning-goal.md`, and `progress.md` with
   exclusive creation from packaged templates, never overwrite them, and
   create `sessions/`;
6. return the managed prompt and records paths.

`prepare_here_workspace(project)` follows the same receipt rule in the current
directory. A new directory gets the `generic` target. An existing healthy
Cursor, Claude Code, or Pi installation keeps its receipt target. A damaged or
conflicting installation propagates the existing actionable domain error.

Both functions materialize packaged distribution bytes with
`packaged_distribution_root()` and call `plan_install`/`apply_install`
directly so launcher startup does not print the installation loader.

- [ ] **Step 5: Add installer regression coverage**

Add a test to `tests/test_install.py` proving a packaged temporary root
produces byte-identical managed manifest and prompt files:

```python
def test_packaged_resources_install_without_repository_cwd(self) -> None:
    with TemporaryDirectory() as temporary:
        project = Path(temporary) / "project"
        project.mkdir()
        with packaged_distribution_root() as source:
            install("generic", project, source_root=source)
        self.assertEqual(
            resource_bytes("manifest.json"),
            (project / ".socratic-learn/manifest.json").read_bytes(),
        )
```

- [ ] **Step 6: Run focused and installer tests**

Run:

```powershell
python -m unittest tests.test_workspace tests.test_install -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/resources.py socratic_learn/workspace.py tests/test_workspace.py tests/test_install.py
git commit -m "feat: prepare private learning workspaces"
```

---

### Task 4: Interactive Launcher and Process Lifecycle

**Files:**
- Create: `socratic_learn/launcher.py`
- Create: `tests/test_launcher.py`

**Interfaces:**
- Consumes: host detection, launcher config, and workspace preparation
- Produces: `LaunchOptions(goal, agent, here, cwd)`
- Produces: `run_learning(options, *, input_fn=input, output=sys.stdout, which=shutil.which, run_process=subprocess.run, environ=None) -> int`

- [ ] **Step 1: Write failing launcher tests with fake process boundaries**

```python
# tests/test_launcher.py
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from socratic_learn.launcher import LaunchOptions, run_learning


class LauncherTests(unittest.TestCase):
    def test_first_run_prompts_goal_and_agent_then_saves_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            answers = iter(["probability", "1"])
            calls: list[tuple[list[str], Path]] = []

            def fake_run(argv: list[str], *, cwd: Path, check: bool) -> CompletedProcess:
                calls.append((argv, cwd))
                return CompletedProcess(argv, 0)

            result = run_learning(
                LaunchOptions(goal=None, agent=None, here=False, cwd=Path.cwd()),
                input_fn=lambda prompt: next(answers),
                output=io.StringIO(),
                which={"pi": "C:/bin/pi.exe"}.get,
                run_process=fake_run,
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )

            self.assertEqual(0, result)
            self.assertIn("probability", calls[0][0])
            self.assertIn('"default_agent": "pi"', (Path(temporary) / "config.json").read_text("utf-8"))

    def test_child_exit_code_is_returned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                input_fn=lambda prompt: "",
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: CompletedProcess(argv, 23),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )
            self.assertEqual(23, result)

    def test_no_agent_has_actionable_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(Exception, "compatible agent"):
                run_learning(
                    LaunchOptions("logic", None, False, Path.cwd()),
                    input_fn=lambda prompt: "",
                    output=io.StringIO(),
                    which=lambda name: None,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )
```

- [ ] **Step 2: Run tests and verify the launcher module is missing**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: import failure for `socratic_learn.launcher`.

- [ ] **Step 3: Implement deterministic selection and launch flow**

Use:

```python
@dataclass(frozen=True)
class LaunchOptions:
    goal: str | None
    agent: AgentName | None
    here: bool
    cwd: Path
```

The algorithm is:

1. detect hosts in canonical order;
2. fail with `UsageError("no compatible agent was found", remediation=...)`
   when none exist;
3. load config;
4. prompt `What do you want to learn? ` only when `goal is None`; reject empty
   or whitespace-only goals;
5. honor explicit `--agent`; otherwise use a still-detected saved agent;
6. when the saved agent disappeared, explain that fact and prompt from the
   remaining hosts;
7. when no saved agent exists, print a numbered list and accept only a listed
   number;
8. save a newly selected default;
9. prepare personal workspace or `--here`;
10. build an argument tuple and call `subprocess.run(list(argv), cwd=workspace.root, check=False)`;
11. return the exact child status.

Catch `KeyboardInterrupt` around the child only and return `130`. Do not catch
unexpected exceptions. Convert executable disappearance between detection and
spawn into `FilesystemError` naming the host and executable. Never pass
`shell=True` or captured stdio. Do not construct, inspect, log, or persist a
child environment; omit the `env` argument so the host inherits its normal
authentication environment directly from the parent process.

- [ ] **Step 4: Add coverage for saved-host disappearance, `--here`, spaces, Unicode, and interrupt**

Each case uses fake `which` and `run_process`. Assert that:

- a missing saved host causes one new selection and rewrites config;
- `--here` uses the supplied current directory;
- a goal containing `"Bayes cafés"` remains one argv element;
- `KeyboardInterrupt` returns `130`;
- neither output nor config contains `ANTHROPIC_API_KEY` supplied in the test
  environment.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/launcher.py tests/test_launcher.py
git commit -m "feat: launch interactive learning sessions"
```

---

### Task 5: Public `socratic` Command Surface

**Files:**
- Modify: `socratic_learn/cli.py`
- Create: `tests/test_console_cli.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `run_learning(LaunchOptions(...))`
- Produces: console grammar for default launch, `learn`, `--agent`, `--here`,
  `--version`, and existing administrative commands

- [ ] **Step 1: Write failing console contract tests**

```python
# tests/test_console_cli.py
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.cli import main
from socratic_learn.launcher import LaunchOptions


class ConsoleCliTests(unittest.TestCase):
    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_no_arguments_launches_with_prompt(self, run: mock.Mock) -> None:
        self.assertEqual(0, main([]))
        run.assert_called_once_with(
            LaunchOptions(None, None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_direct_goal_and_options_launch(self, run: mock.Mock) -> None:
        self.assertEqual(
            0,
            main(["--agent", "pi", "--here", "linear", "algebra"]),
        )
        run.assert_called_once_with(
            LaunchOptions("linear algebra", "pi", True, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.run_learning", return_value=0)
    def test_explicit_learn_allows_reserved_goal(self, run: mock.Mock) -> None:
        self.assertEqual(0, main(["learn", "doctor"]))
        run.assert_called_once_with(
            LaunchOptions("doctor", None, False, Path.cwd())
        )

    @mock.patch("socratic_learn.cli.administrative_main", return_value=7)
    def test_admin_command_is_forwarded_unchanged(self, admin: mock.Mock) -> None:
        self.assertEqual(7, main(["doctor", "project"]))
        admin.assert_called_once_with(["doctor", "project"])
```

- [ ] **Step 2: Run tests and verify no-argument launch fails**

Run:

```powershell
python -m unittest tests.test_console_cli -v
```

Expected: failures because `cli.main` still forwards to the administrative
parser.

- [ ] **Step 3: Implement two-phase parsing without changing module parsing**

Reserve these first tokens for administration:

```python
_ADMIN_COMMANDS = {"build", "export", "install", "doctor"}
_SELF_COMMANDS = {"update", "uninstall"}
```

Rules:

- `socratic --help` prints launcher help containing examples and all admin
  commands;
- `socratic --version` prints `socratic-learn <__version__>`;
- a first token in `_ADMIN_COMMANDS` forwards the original argv list to
  `administrative_main`;
- optional `learn` is removed before collecting the goal;
- launcher flags are `--agent {pi,claude,antigravity}` and `--here`;
- all remaining positional words are joined with one space;
- no remaining words means `goal=None`;
- parser abbreviation is disabled;
- known `LearningTutorError` values print without a traceback and return their
  stable exit code, matching the administrative CLI.

Do not modify `socratic_learn.__main__.main`. Preserve
`tests.test_cli.CliContractTests.test_no_command_returns_usage_error`.

- [ ] **Step 4: Add installed-console smoke coverage**

Build a wheel, install it into a temporary virtual environment, and assert:

```text
socratic --version
```

returns zero and starts with `socratic-learn 0.1.0`, while:

```text
python -m socratic_learn
```

still returns exit code 2.

- [ ] **Step 5: Run CLI suites**

Run:

```powershell
python -m unittest tests.test_console_cli tests.test_cli tests.test_packaging -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/cli.py tests/test_console_cli.py tests/test_cli.py tests/test_packaging.py
git commit -m "feat: expose the socratic launcher command"
```

---

### Task 6: Verified Release Metadata and Downloads

**Files:**
- Create: `socratic_learn/release.py`
- Create: `tests/test_release.py`
- Create: `release-manifest.schema.json`

**Interfaces:**
- Produces: `ReleaseArtifact(version, platform, architecture, filename, size, sha256, url)`
- Produces: `parse_release_manifest(data: bytes, base_url: str) -> tuple[ReleaseArtifact, ...]`
- Produces: `current_platform() -> tuple[str, str]`
- Produces: `select_artifact(artifacts, platform, architecture) -> ReleaseArtifact`
- Produces: `download_verified(artifact, destination, opener=urlopen) -> Path`

- [ ] **Step 1: Write failing release parser and hash tests**

```python
# tests/test_release.py
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from socratic_learn.errors import IntegrityError
from socratic_learn.release import (
    download_verified,
    parse_release_manifest,
    select_artifact,
)


class ReleaseTests(unittest.TestCase):
    def manifest(self, payload: bytes) -> bytes:
        return json.dumps({
            "schema_version": 1,
            "version": "0.1.0",
            "artifacts": [{
                "platform": "windows",
                "architecture": "x86_64",
                "filename": "socratic-windows-x86_64.exe",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }],
        }).encode("utf-8")

    def test_parse_and_select_exact_platform(self) -> None:
        artifacts = parse_release_manifest(
            self.manifest(b"binary"),
            "https://example.invalid/v0.1.0/",
        )
        selected = select_artifact(artifacts, "windows", "x86_64")
        self.assertEqual("socratic-windows-x86_64.exe", selected.filename)

    def test_hash_mismatch_preserves_no_destination(self) -> None:
        artifact = parse_release_manifest(
            self.manifest(b"expected"),
            "https://example.invalid/v0.1.0/",
        )[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename
            with self.assertRaises(IntegrityError):
                download_verified(
                    artifact,
                    destination,
                    opener=lambda url: io.BytesIO(b"tampered"),
                )
            self.assertFalse(destination.exists())
```

- [ ] **Step 2: Run tests and verify the release module is missing**

Run:

```powershell
python -m unittest tests.test_release -v
```

Expected: import failure for `socratic_learn.release`.

- [ ] **Step 3: Define and enforce the release manifest schema**

`release-manifest.schema.json` and the Python parser must require exactly:

```json
{
  "schema_version": 1,
  "version": "0.1.0",
  "artifacts": [
    {
      "platform": "windows",
      "architecture": "x86_64",
      "filename": "socratic-windows-x86_64.exe",
      "size": 123,
      "sha256": "64 lowercase hexadecimal characters"
    }
  ]
}
```

Reject unknown keys, path separators in filenames, duplicate
platform/architecture pairs, non-positive sizes, malformed semantic versions,
and non-lowercase hashes. Construct URLs only with `urllib.parse.urljoin` after
filename validation.

- [ ] **Step 4: Implement platform normalization and streamed verification**

Normalize:

- `win32` -> `windows`
- `linux` -> `linux`
- `darwin` -> `macos`
- `AMD64`, `x86_64`, `x64` -> `x86_64`

All other architectures raise `UsageError` with remediation
`pipx install socratic-learn`.

`download_verified` writes chunks to an exclusive sibling temporary file,
counts bytes, updates SHA-256, flushes and `fsync`s, verifies both expected
size and digest, then publishes with `os.replace`. A failed verification
removes only that temporary file and never touches an existing destination.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_release -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/release.py release-manifest.schema.json tests/test_release.py
git commit -m "feat: verify native release downloads"
```

---

### Task 7: Channel-Aware Update and Uninstall

**Files:**
- Create: `socratic_learn/self_manage.py`
- Create: `tests/test_self_manage.py`
- Modify: `socratic_learn/cli.py`
- Modify: `tests/test_console_cli.py`

**Interfaces:**
- Consumes: release manifest parsing and verified download
- Produces: `InstallChannel(schema_version, channel, executable, manifest_url)`
- Produces: `load_install_channel(home: Path) -> InstallChannel | None`
- Produces: `update_installation(home: Path, executable: Path, ...) -> int`
- Produces: `uninstall(home: Path, *, delete_data: bool, confirm: Callable) -> int`

- [ ] **Step 1: Write failing channel and rollback tests**

```python
# tests/test_self_manage.py
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.release import ReleaseArtifact
from socratic_learn.self_manage import uninstall, update_installation


def write_native_channel(home: Path, executable: Path) -> None:
    (home / "channel.json").write_text(
        json.dumps({
            "schema_version": 1,
            "channel": "native",
            "executable": str(executable.resolve()),
            "manifest_url": (
                "https://github.com/marcos-guilherme/socratic-learn/"
                "releases/latest/download/release-manifest.json"
            ),
        }),
        encoding="utf-8",
    )


def fake_manifest(url: str) -> bytes:
    payload = b"new"
    return json.dumps({
        "schema_version": 1,
        "version": "0.1.0",
        "artifacts": [{
            "platform": "windows",
            "architecture": "x86_64",
            "filename": "socratic-windows-x86_64.exe",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }],
    }).encode("utf-8")


def fake_artifact(artifact: ReleaseArtifact, destination: Path) -> Path:
    destination.write_bytes(b"new")
    return destination


class SelfManagementTests(unittest.TestCase):
    def test_python_install_reports_pipx_command_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            messages: list[str] = []
            self.assertEqual(
                0,
                update_installation(
                    home,
                    Path("python"),
                    output=messages.append,
                ),
            )
            self.assertEqual(["Run: pipx upgrade socratic-learn"], messages)

    def test_failed_native_replacement_preserves_old_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            executable = home / "bin/socratic"
            executable.parent.mkdir()
            executable.write_bytes(b"old")
            # Write a valid native channel fixture pointing at executable.
            write_native_channel(home, executable)
            with mock.patch(
                "socratic_learn.self_manage._replace_native",
                side_effect=OSError("blocked"),
            ):
                with self.assertRaises(OSError):
                    update_installation(
                        home,
                        executable,
                        fetch_manifest=fake_manifest,
                        fetch_artifact=fake_artifact,
                    )
            self.assertEqual(b"old", executable.read_bytes())

    def test_uninstall_preserves_records_without_delete_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            record = home / "learning/.socratic-learn/workspace/progress.md"
            record.parent.mkdir(parents=True)
            record.write_text("private\n", encoding="utf-8")
            uninstall(home, delete_data=False, confirm=lambda prompt: True)
            self.assertEqual("private\n", record.read_text("utf-8"))
```

- [ ] **Step 2: Run tests and verify the module is missing**

Run:

```powershell
python -m unittest tests.test_self_manage -v
```

Expected: import failure for `socratic_learn.self_manage`.

- [ ] **Step 3: Implement exact-key installation channel metadata**

Native installers write `~/.socratic-learn/channel.json`:

```json
{
  "schema_version": 1,
  "channel": "native",
  "executable": "/absolute/path/to/socratic",
  "manifest_url": "https://github.com/marcos-guilherme/socratic-learn/releases/latest/download/release-manifest.json"
}
```

Reject relative executable paths, unknown keys, symlinks, and unsupported
channels. Absence means Python/PyPI and returns `None`; in that case update and
uninstall print exact `pipx` commands and perform no filesystem mutation.

- [ ] **Step 4: Implement native replacement and removal**

On POSIX:

1. verified download is created beside the installed executable;
2. mode is set to `0o755`;
3. `os.replace(staged, executable)` performs same-filesystem atomic replacement;
4. the previous executable remains untouched until verification succeeds.

On Windows, generate a temporary PowerShell helper containing Base64-encoded
UTF-16 path values, not interpolated raw paths. It waits for the parent PID,
calls `[System.IO.File]::Move(staged, destination, $true)`, and removes itself.
Launch it detached with:

```python
subprocess.Popen(
    ["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(helper)],
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    | subprocess.DETACHED_PROCESS,
    close_fds=True,
)
```

The helper is created only after hash verification. If helper creation or
spawn fails, remove the staged artifact and preserve the old executable.
Unit tests decode the generated helper and assert the exact source and
destination values for paths containing spaces and apostrophes.

Uninstall uses the same deferred Windows pattern. `delete_data=False` removes
only the executable and `channel.json`. `delete_data=True` asks:

```text
Delete all Socratic Learn learner profiles, progress, and sessions? [y/N]
```

Only case-insensitive `y` or `yes` authorizes removal. A non-interactive
`--yes` flag is required together with `--delete-data`.

- [ ] **Step 5: Wire `update` and `uninstall` into the console parser**

Add:

```text
socratic update
socratic uninstall
socratic uninstall --delete-data
socratic uninstall --delete-data --yes
```

These tokens are console-only and must never be forwarded to the
administrative module parser. Add mock-based routing tests to
`tests/test_console_cli.py`.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
python -m unittest tests.test_self_manage tests.test_release tests.test_console_cli -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/self_manage.py socratic_learn/cli.py tests/test_self_manage.py tests/test_console_cli.py
git commit -m "feat: manage native launcher updates"
```

---

### Task 8: Native Bootstrap Installers

**Files:**
- Create: `scripts/install.ps1`
- Create: `scripts/install.sh`
- Create: `tests/test_bootstrap_installers.py`

**Interfaces:**
- Consumes: `release-manifest.json` on Windows and `SHA256SUMS` on POSIX
- Produces: user-local `socratic` executable and `channel.json`

- [ ] **Step 1: Write static and isolated installer tests**

Create tests that:

- assert PowerShell contains the canonical latest-manifest URL and the POSIX
  script contains the canonical latest-release base URL plus `SHA256SUMS`;
- assert both verify SHA-256 before moving the executable;
- assert neither requires elevation (`sudo`, `RunAs`, or machine-wide paths);
- serve a fixture manifest and artifact from a local HTTP server;
- execute the platform-matching installer with isolated `HOME`, `PATH`, and
  download base URL;
- assert the installed bytes match the fixture and `channel.json` is valid;
- corrupt the fixture hash and assert no executable is installed.

Run:

```powershell
python -m unittest tests.test_bootstrap_installers -v
```

Expected: failure because the scripts do not exist.

- [ ] **Step 2: Implement `scripts/install.ps1`**

The script must:

1. print the unsigned-binary SmartScreen warning and require an interactive
   confirmation unless `-Yes` is supplied;
2. reject non-x86-64 Windows with the pipx fallback;
3. fetch and exact-key validate the JSON manifest;
4. select `windows/x86_64`;
5. download to `$env:LOCALAPPDATA\SocraticLearn\bin\socratic.new.exe`;
6. compare file length and `Get-FileHash -Algorithm SHA256`;
7. atomically move to `socratic.exe`;
8. add only that user directory to the user `PATH` when absent;
9. write `channel.json` beneath `$HOME\.socratic-learn`;
10. print `Run: socratic`.

Use parameters `-ManifestUrl`, `-InstallDirectory`, and `-Yes` so tests do not
contact GitHub or alter the real user profile.

- [ ] **Step 3: Implement `scripts/install.sh`**

The script must:

1. use `set -eu`;
2. print the unsigned Gatekeeper warning and require confirmation unless
   `SOCRATIC_INSTALL_YES=1`;
3. normalize `uname -s` to `linux` or `macos` and require `uname -m` x86-64;
4. fetch with `curl --fail --location --proto '=https' --tlsv1.2`;
5. derive the fixed asset name `socratic-{linux|macos}-x86_64`, download that
   asset and `SHA256SUMS`, and select the checksum with
   `awk -v name="$asset" '$2 == name {print $1}'`;
6. reject zero or multiple exact checksum matches;
7. download to `${XDG_BIN_HOME:-$HOME/.local/bin}/socratic.new`;
8. verify with `sha256sum` or `shasum -a 256`;
9. `chmod 755` and atomically `mv` to `socratic`;
10. write channel metadata to `${SOCRATIC_LEARN_HOME:-$HOME/.socratic-learn}`;
11. print the exact shell profile line only when the bin directory is absent
    from `PATH`.

Allow `SOCRATIC_RELEASE_BASE_URL` and `SOCRATIC_INSTALL_DIR` overrides for
tests. The script must not require Python, `jq`, Node.js, or a package manager.

- [ ] **Step 4: Run installer tests on the current platform**

Run:

```powershell
python -m unittest tests.test_bootstrap_installers -v
```

Expected: all platform-independent tests and the current-platform isolated
install test pass; the other platform execution test is skipped with a named
reason.

- [ ] **Step 5: Commit**

```powershell
git add scripts/install.ps1 scripts/install.sh tests/test_bootstrap_installers.py
git commit -m "feat: add native launcher installers"
```

---

### Task 9: Native Build and Release Automation

**Files:**
- Create: `socratic-learn.spec`
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/native-python.yml`
- Modify: `tests/test_validate_repository.py`
- Modify: `tests/validate_repository.py`

**Interfaces:**
- Consumes: package resources, console entry point, installers, release schema
- Produces: wheel, source distribution, three x86-64 executables, checksums,
  `SHA256SUMS`, `release-manifest.json`, PyPI distributions, and GitHub Release
  assets

- [ ] **Step 1: Add failing repository validation requirements**

Require these paths:

```text
pyproject.toml
release-manifest.schema.json
socratic-learn.spec
scripts/install.ps1
scripts/install.sh
.github/workflows/release.yml
```

Add structural tests asserting:

- `pyproject.toml` maps `socratic` to `socratic_learn.cli:entry_point`;
- the release workflow runs on version tags and manual dispatch;
- the matrix contains Windows, Ubuntu, and macOS;
- release permissions are `contents: write` only at the publishing job;
- every native job runs the unit suite before PyInstaller;
- every artifact is smoke-tested with `socratic --version`;
- the manifest job computes hashes from downloaded artifacts rather than
  trusting build-job strings;
- the PyPI publishing job uses trusted publishing with `id-token: write` and
  runs only for version tags;
- the normal safety matrix installs `.[build]` before packaging tests.

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: failures listing the missing spec and workflow.

- [ ] **Step 2: Create the PyInstaller spec**

The spec must:

- use `socratic_learn/cli.py` as the entry module;
- include `dist/manifest.json`, `dist/socratic-learn.prompt.md`, and all four
  root templates under `socratic_learn/data/`;
- collect `socratic_learn` and `learning_tutor`;
- exclude test modules and third-party GUI libraries;
- produce one console executable named `socratic`;
- fail the build when the checked-in distribution differs after
  `python -m socratic_learn build`.

- [ ] **Step 3: Create `.github/workflows/release.yml`**

Triggers:

```yaml
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
```

Jobs:

1. `python-package` on Ubuntu: install `.[build]`, run the full suite and
   validator, build wheel and sdist, install the wheel in a clean venv, run
   `socratic --version`, upload both artifacts.
2. `native` matrix on `windows-latest`, `ubuntu-latest`, and `macos-13`: install
   `.[build]`, run the full suite and validator, run PyInstaller, rename output
   to `socratic-{platform}-x86_64[.exe]`, execute `--version`, upload it.
3. `manifest`: download all native artifacts, compute size and SHA-256 with a
   checked-in Python snippet in the workflow, validate against
   `release-manifest.schema.json`, generate standard two-space-delimited
   `SHA256SUMS`, and upload both files.
4. `publish-github`, only for `refs/tags/v*`, with `contents: write`: download package,
   native, installer, and manifest artifacts and create the GitHub Release
   using `gh release create`.
5. `publish-pypi`, only for `refs/tags/v*`, with `id-token: write` and the
   protected `pypi` environment: download the wheel and sdist and publish with
   `pypa/gh-action-pypi-publish@release/v1`.

All jobs use `actions/checkout@v4`, `actions/setup-python@v5` with Python 3.11,
and `actions/upload-artifact@v4`/`download-artifact@v4`. No pull-request job
receives write permission. A tag build must fail before publication unless the
tag `vX.Y.Z` exactly matches `socratic_learn.__version__ == "X.Y.Z"`.

- [ ] **Step 4: Extend the normal safety matrix**

Before tests, install:

```yaml
- name: Install build dependencies
  run: python -m pip install -e ".[build]"
```

Add a wheel build and installed-console smoke test on every OS, but leave
PyInstaller only in the release workflow to keep ordinary CI bounded.

- [ ] **Step 5: Run validator, package, and local native smoke checks**

Run:

```powershell
python -m socratic_learn build
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
python -m build
python -m PyInstaller socratic-learn.spec --noconfirm --distpath dist-native --workpath build-native
.\dist-native\socratic.exe --version
git diff --check
```

On POSIX use `./dist-native/socratic --version`. Expected: all commands pass,
the version is `0.1.0`, and generated build directories are ignored.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml release-manifest.schema.json socratic-learn.spec .github/workflows/native-python.yml .github/workflows/release.yml tests/test_validate_repository.py tests/validate_repository.py .gitignore
git commit -m "ci: build native socratic releases"
```

---

### Task 10: Public Documentation and End-to-End Acceptance

**Files:**
- Modify: `README.md`
- Modify: `docs/universal-installation.md`
- Create: `docs/launcher-adapters.md`
- Modify: `docs/adding-an-adapter.md`
- Modify: `tests/test_universal_smoke.py`
- Modify: `tests/test_validate_repository.py`
- Modify: `tests/validate_repository.py`

**Interfaces:**
- Documents: native install, PyPI fallback, first run, direct goal, `--here`,
  agent override, update, uninstall, privacy, unsigned warnings, and adapter
  extension contract
- Verifies: an installed console launches a fake host end to end

- [ ] **Step 1: Write failing README and documentation contract tests**

Require exact public examples:

```text
socratic
socratic "I want to learn linear algebra"
socratic --agent pi
socratic --here
socratic update
socratic uninstall
pipx install socratic-learn
```

Require the README to state:

- no repository clone is needed for normal use;
- no provider credentials are stored by Socratic Learn;
- no-argument prompting avoids putting the goal in shell history;
- first native binaries are unsigned and may trigger SmartScreen/Gatekeeper;
- Pi, Claude Code, and Antigravity are launcher hosts;
- Cursor remains a project integration.

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: failures identifying missing launcher onboarding.

- [ ] **Step 2: Rewrite Quick Start around one-command learning**

Order the README:

1. one-line native install links for Windows and POSIX;
2. PyPI alternative;
3. `socratic` first run;
4. direct goal and agent override;
5. `--here`;
6. current protocol explanation;
7. advanced administrative commands.

Move clone/build instructions into a contributor or source-development
subsection. Keep all existing universal-learning positioning and limitation
language.

- [ ] **Step 3: Document host and distribution behavior**

`docs/launcher-adapters.md` defines:

- adapter detection names;
- exact command construction;
- protocol delivery requirement;
- inherited authentication and terminal behavior;
- required fake-executable tests for new hosts.

Update `docs/adding-an-adapter.md` to distinguish project-discovery adapters
from launcher adapters. Update `docs/universal-installation.md` with native
channel metadata, hash verification, unsigned warnings, rollback, pipx channel
behavior, and data-preserving uninstall.

- [ ] **Step 4: Add installed-console end-to-end smoke test**

Extend `tests/test_universal_smoke.py` to:

1. build and install the wheel into a temporary virtual environment;
2. create fake `pi`/`pi.exe` in an isolated `PATH`;
3. make the fake executable record argv and cwd then exit 17;
4. run `socratic --agent pi "learn graph theory"` with an isolated home;
5. assert exit 17, protocol path and exact goal delivery, private workspace
   creation, and saved default;
6. assert no file outside the isolated home and test directory changed.

- [ ] **Step 5: Run the complete local release gate**

Run:

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
python -m build
git diff --check
git status --short --branch
```

Expected: all tests pass, repository validation passes, build artifacts match,
and only intended committed changes remain.

- [ ] **Step 6: Commit**

```powershell
git add README.md docs/universal-installation.md docs/launcher-adapters.md docs/adding-an-adapter.md tests/test_universal_smoke.py tests/test_validate_repository.py tests/validate_repository.py
git commit -m "docs: publish one-command learning workflow"
```

---

### Task 11: Whole-Branch Review and Hosted Verification

**Files:**
- Review: all changes since the design commit
- External: GitHub Actions runs and release dry run

**Interfaces:**
- Produces: reviewed, merge-ready branch with hosted cross-platform evidence

- [ ] **Step 1: Run an independent whole-branch review**

Review the diff from design commit `5dce122` through `HEAD` for:

- credential exposure;
- shell injection or unsafe path interpolation;
- overwrite, symlink, and update rollback regressions;
- mismatch between source, wheel, and native resources;
- host argv incompatibility;
- accidental changes to module CLI compatibility;
- missing tests or misleading installation claims.

Resolve every Critical or Important finding and rerun the affected focused
suites after each correction.

- [ ] **Step 2: Run the fresh final local gate**

Run:

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
python -m build
python -m PyInstaller socratic-learn.spec --noconfirm --distpath dist-native --workpath build-native
.\dist-native\socratic.exe --version
git diff --check
git status --short --branch
```

Expected: zero failures, repository validation passes, package and native
smokes pass, and the tree is clean.

- [ ] **Step 3: Push the feature branch and verify ordinary CI**

```powershell
git push -u origin feat/one-command-learning-launcher
gh run list --repo marcos-guilherme/socratic-learn --branch feat/one-command-learning-launcher --limit 1
```

Watch the run with `gh run watch RUN_ID --exit-status`. Expected: Windows,
Ubuntu, and macOS jobs all succeed.

- [ ] **Step 4: Exercise release automation without publishing**

Run the release workflow through `workflow_dispatch`. The workflow must build
and validate package, native, and manifest artifacts but skip the tag-only
publish job. Download artifacts and verify:

```powershell
gh run download RUN_ID --repo marcos-guilherme/socratic-learn --dir release-smoke
python -m json.tool release-smoke/release-manifest.json
```

Compare each downloaded native artifact's size and SHA-256 to the manifest and
run the current-platform binary with `--version`.

- [ ] **Step 5: Merge only after hosted evidence succeeds**

Fast-forward merge the reviewed branch, push `master`, and verify the resulting
master safety-matrix run. Do not create a version tag or public GitHub Release
without a separate explicit publication approval because tagging publishes
unsigned binaries and PyPI publication requires repository secrets.
