# Runtime Command UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace launcher-facing agent/host terminology with runtime terminology and deliver schema-2 configuration, discoverable runtime commands, bounded launcher diagnostics, operational runtime documentation, and package/native parity without changing the learning protocol.

**Architecture:** Keep runtime metadata and process argument construction in one pure `runtimes.py` module, keep launcher preference migration in `config.py`, and route the learner-facing command tree through `cli.py`. Add `runtime_commands.py` for non-launching runtime preference commands and a separate read-only `launcher_doctor.py`; the existing project-installation diagnostics remain in `doctor.py` and remain available through the module CLI.

**Tech Stack:** Python 3.11+ standard library only, `argparse`, `dataclasses`, `typing.Literal`, `unittest`, Hatchling wheel packaging, PyInstaller native packaging, repository validators, and GitHub Actions.

## Global Constraints

- Execute this subproject only after the tracked sanitized Antigravity baseline report exists at `evaluation/reports/2026-11-06-antigravity-baseline.md`; the report is an input and is not rewritten here.
- This is the complete, independently testable runtime-command UX subproject. Evidence-derived pedagogy and semantic-evaluation changes are a later subproject.
- Preserve the checkout-only `evaluation/` system, its tracked sanitized report, its ignored `.semantic-runs/` boundary, and its exclusion from wheels, source distributions, native executables, public commands, and ordinary CI.
- Do not modify `core/*.md`, `dist/socratic-learn.prompt.md`, `dist/manifest.json`, `PROTOCOL_VERSION`, manifest bytes, or any protocol-delivery argument bytes.
- The canonical public concepts are **protocol**, **runtime**, **model**, **provider**, and **learner workspace**.
- The canonical runtime type is exactly `RuntimeName = Literal["pi", "claude", "antigravity"]`.
- Public launcher names and messages use `runtime`; `agent` remains only in the deprecated `--agent` compatibility flag, schema-1 `default_agent` migration, and truthful product descriptions such as “Anthropic's agent CLI.”
- Runtime display order is exactly Antigravity, Pi, Claude Code. This deterministic order is not a product-category claim.
- Runtime descriptions are exactly:
  - `Antigravity — full agentic environment`
  - `Pi — terminal harness; configure its provider and model separately`
  - `Claude Code — Anthropic's agent CLI`
- Configuration schema 2 is exactly `{"schema_version": 2, "default_runtime": RUNTIME_OR_NULL}`.
- Loading schema 1 maps exact-key `default_agent` to `default_runtime` in memory without writing. The next explicit preference write publishes schema 2 atomically.
- Unknown keys, duplicate keys, malformed JSON, invalid runtime values, booleans in integer fields, symbolic links, and unsupported schemas fail closed without replacing the original file.
- `socratic`, `socratic start`, direct goals, and `socratic learn ...` remain launch paths. `socratic learn ...` is the escape for goals beginning with reserved command words.
- The public command surface is `socratic`, `socratic start`, `socratic runtimes`, `socratic use RUNTIME`, `socratic config`, `socratic doctor`, `socratic project doctor`, `socratic update`, and `socratic uninstall`.
- `--runtime` is a one-session override and never mutates configuration. Deprecated `--agent` has the same non-mutating behavior and prints one concise stderr warning.
- `socratic update`, `socratic uninstall`, `socratic build`, `socratic export`, `socratic install`, `python -m socratic_learn`, and `python -m socratic_learn doctor PROJECT` retain their existing behavior.
- `socratic doctor` is launcher diagnostics. `socratic project doctor` diagnoses the current directory through the existing project diagnostics in `socratic_learn/doctor.py`.
- Create `socratic_learn/launcher_doctor.py`; do not move or duplicate project diagnostic logic from `socratic_learn/doctor.py`.
- Launcher diagnostics are read-only and perform no provider/model invocation, network request, credential-store read, authentication test, billing test, quota test, or model-access claim.
- The launcher returns the runtime child exit status and does not parse arbitrary provider output to infer authentication, billing, quota, or model failures.
- Do not add `socratic model`, shared provider configuration, credential storage, model catalog normalization, or any unified model-management API.
- Keep runtime command construction byte-for-byte compatible with the current Pi, Claude Code, and Antigravity argument vectors.
- Keep the implementation dependency-free and follow the repository's existing `unittest`, dataclass, injected-callable, atomic-write, and actionable-error patterns.
- Update user-facing documentation and its deterministic validator requirements in the same commit.
- No release, tag, GitHub publication, PyPI publication, or package upload is part of this plan.

---

## Execution Prerequisite: Prove the Baseline and Lock Protocol Bytes

Run this before Task 1:

```powershell
$baseline = "evaluation/reports/2026-11-06-antigravity-baseline.md"
if (-not (git ls-files --error-unmatch $baseline 2>$null)) {
    throw "Missing tracked sanitized baseline report: $baseline"
}
$baseline
Get-FileHash core\*.md, dist\socratic-learn.prompt.md, dist\manifest.json -Algorithm SHA256 |
    Sort-Object Path |
    Format-Table -AutoSize
```

Expected: the exact tracked baseline report path is printed, followed by hashes for the four canonical core files and the two generated protocol artifacts. Save the command output in the implementation session record. If the report is absent or untracked, stop; do not begin this subproject.

Read that report and classify only its runtime UX, launcher, documentation, and infrastructure findings into this plan's fixed scope. Do not convert pedagogy findings into runtime code or edit the protocol.

## Exact File Responsibilities

### Runtime implementation

- Delete `socratic_learn/hosts.py`: retire the old launcher host vocabulary in the same task that moves every production import to `runtimes.py`.
- Create `socratic_learn/runtimes.py`: own `RuntimeName`, deterministic runtime metadata, first-run descriptions, executable detection, detected-runtime records, and unchanged argument-vector construction.
- Modify `evaluation/antigravity.py`: consume `RUNTIMES["antigravity"]` and `command_for` from `socratic_learn.runtimes` so the private baseline evaluator keeps exact launcher-bootstrap parity after the source rename.
- Modify `socratic_learn/config.py`: own exact schema-1/schema-2 parsing, duplicate-key rejection, in-memory schema-1 migration, runtime validation, and atomic schema-2 writes.
- Modify `socratic_learn/launcher.py`: own goal prompting, first-run runtime selection, saved-runtime use, stale-runtime errors, one-shot overrides, workspace preparation, Windows shim safety, and child-process lifecycle.
- Create `socratic_learn/runtime_commands.py`: own the `runtimes`, `use`, and interactive `config` command behavior without launching a model.
- Create `socratic_learn/launcher_doctor.py`: own read-only launcher/package/PATH/home/config/runtime/resource/personal-workspace diagnostics and the explicit diagnostic boundary.
- Modify `socratic_learn/cli.py`: own the learner-facing command tree, `start` equivalence, reserved-command dispatch, `learn` goal escape, deprecated `--agent` warning, current-directory project-doctor namespace, and unchanged self-management/administrative forwarding.
- Keep `socratic_learn/doctor.py` unchanged except for no edits: it remains the sole project-installation diagnostic implementation.
- Keep `socratic_learn/__main__.py` unchanged except for no edits: it remains the administrative module CLI.

### Runtime tests

- Delete `tests/test_hosts.py` after moving its unchanged command-contract assertions to `tests/test_runtimes.py`.
- Create `tests/test_runtimes.py`: test canonical names, immutable metadata, descriptions, ordering, executable detection, and exact command vectors.
- Modify `tests/test_evaluation_antigravity.py`: update the public-bootstrap parity import and retain exact evaluation/launcher bootstrap equality.
- Modify `tests/test_config.py`: test schema-2 writes, schema-1 in-memory migration, fail-closed parsing, symlink rules, and atomic publication.
- Modify `tests/test_launcher.py`: test first-run descriptions, saved/stale runtime behavior, override non-mutation, child status, unchanged argv, Windows shim safety, and diagnostic boundary behavior at launch.
- Create `tests/test_runtime_commands.py`: test listing, `use`, interactive configuration, detection validation, deterministic output, and non-secret state.
- Create `tests/test_launcher_doctor.py`: test every launcher diagnostic, deterministic formatting, read-only behavior, and explicit prohibition on model/network/credential access.
- Modify `tests/test_console_cli.py`: test the complete command grammar, `start` equivalence, goal escape, aliases, warnings, project-doctor routing, and compatibility commands.
- Modify `tests/test_universal_smoke.py`: update installed-wheel fake-runtime acceptance to schema 2 and `--runtime`, while retaining a deprecated `--agent` smoke assertion.
- Modify `tests/test_packaging.py`: prove wheel-installed command parity for `--help`, `runtimes`, launcher doctor, current-directory project doctor, module doctor, and fake-runtime launch.

### Public documentation and validation

- Modify `README.md`: present the shortest start path, runtime terminology, command surface, privacy behavior, and links to the focused guides.
- Modify `docs/launcher-adapters.md`: rename public host/agent concepts to runtime concepts while preserving exact executable and argv contracts.
- Modify `docs/adding-an-adapter.md`: distinguish project-discovery adapters from launcher runtime adapters.
- Modify `docs/universal-installation.md`: document launcher versus project doctor and preserve update/uninstall/admin compatibility.
- Create `docs/runtime-model-protocol.md`: define protocol/runtime/model/provider/workspace boundaries.
- Create `docs/runtimes.md`: compare Pi, Claude Code, and Antigravity without normalizing their model management.
- Create `docs/runtimes/pi.md`: explain Pi installation/detection, `/login`, `/model`, llama.cpp local inference, free-tier limitations, 429s, exact protocol delivery, inherited behavior, and changing the Socratic Learn default.
- Create `docs/runtimes/claude-code.md`: give the same operational structure for Claude Code.
- Create `docs/runtimes/antigravity.md`: give the same operational structure for Antigravity.
- Create `docs/launcher-configuration.md`: document schema migration, `runtimes`, `use`, `config`, `--runtime`, deprecated `--agent`, and launcher doctor.
- Create `docs/troubleshooting.md`: separate Socratic Learn setup failures from runtime/provider/authentication/quota/network/model failures and give runtime-specific next actions.
- Modify `tests/validate_repository.py`: require the new files, command examples, runtime vocabulary, diagnostic boundary, guide structure, and absence of unified model-management commands.
- Modify `tests/test_validate_repository.py`: test each new validator rule and update README/documentation fixtures atomically.

### Package and native parity

- Modify `.github/workflows/native-python.yml`: smoke-test the new read-only commands and project-doctor namespace on Windows, Ubuntu, and macOS without invoking a provider.
- Verify `pyproject.toml`: the existing console entry point remains `socratic_learn.cli:entry_point`; no dependency is added.
- Verify `socratic-learn.spec`: `collect_submodules("socratic_learn")` includes `runtimes`, `runtime_commands`, and `launcher_doctor`; no protocol resource or native artifact layout changes.
- Do not modify `.github/workflows/release.yml`, release manifests, installers, version numbers, tags, or publication jobs.

---

### Task 1: Canonical Runtime Registry and Source Naming

**Files:**
- Create: `socratic_learn/runtimes.py`
- Delete: `socratic_learn/hosts.py`
- Modify: `socratic_learn/launcher.py`
- Create: `tests/test_runtimes.py`
- Delete: `tests/test_hosts.py`
- Modify: `evaluation/antigravity.py`
- Modify: `tests/test_evaluation_antigravity.py`

**Interfaces:**
- Produces: `RuntimeName = Literal["pi", "claude", "antigravity"]`
- Produces: `RUNTIME_ORDER: tuple[RuntimeName, ...]`
- Produces: `RuntimeAdapter(name: RuntimeName, display_name: str, description: str, executable_names: tuple[str, ...], build_argv: Callable[[str, Path, str], tuple[str, ...]])`
- Produces: `DetectedRuntime(adapter: RuntimeAdapter, executable: str)`
- Produces: `RUNTIMES: Mapping[RuntimeName, RuntimeAdapter]`
- Produces: `detect_runtimes(which: Callable[[str], str | None]) -> dict[RuntimeName, DetectedRuntime]`
- Produces: `command_for(adapter: RuntimeAdapter, executable: str, protocol: Path, goal: str) -> tuple[str, ...]`
- Preserves: `evaluation.antigravity.initial_bootstrap(protocol: Path, goal: str) -> str` equality with the public Antigravity command.

- [ ] **Step 1: Move the old test file and write failing runtime-vocabulary tests**

Run:

```powershell
git mv tests/test_hosts.py tests/test_runtimes.py
```

Replace its import and class header, then add these tests:

```python
from socratic_learn.runtimes import (
    RUNTIMES,
    RUNTIME_ORDER,
    DetectedRuntime,
    RuntimeAdapter,
    command_for,
    detect_runtimes,
)


class RuntimeAdapterTests(unittest.TestCase):
    def test_runtime_order_and_descriptions_are_public_contracts(self) -> None:
        self.assertEqual(("antigravity", "pi", "claude"), RUNTIME_ORDER)
        self.assertEqual(
            [
                ("Antigravity", "full agentic environment"),
                ("Pi", "terminal harness; configure its provider and model separately"),
                ("Claude Code", "Anthropic's agent CLI"),
            ],
            [
                (RUNTIMES[name].display_name, RUNTIMES[name].description)
                for name in RUNTIME_ORDER
            ],
        )

    def test_detection_returns_runtime_records_in_display_order(self) -> None:
        found = {
            "agy": "C:/bin/agy.exe",
            "pi": "C:/bin/pi.exe",
            "claude": "C:/bin/claude.exe",
        }
        detected = detect_runtimes(found.get)
        self.assertEqual(["antigravity", "pi", "claude"], list(detected))
        self.assertIsInstance(detected["pi"], DetectedRuntime)
```

Keep the current exact Pi, Claude Code, and Antigravity `command_for` assertions unchanged except for `RUNTIMES` naming.

Update the baseline evaluator parity test without duplicating the bootstrap:

```python
def test_evaluation_initial_message_matches_public_antigravity_bootstrap(
    self,
) -> None:
    from pathlib import Path

    from evaluation.antigravity import initial_bootstrap
    from socratic_learn.runtimes import RUNTIMES, command_for

    protocol = Path("C:/isolated/.socratic-learn/socratic-learn.prompt.md")
    goal = "learn cafés"
    public = command_for(
        RUNTIMES["antigravity"],
        "agy",
        protocol,
        goal,
    )
    self.assertEqual(public[2], initial_bootstrap(protocol, goal))
```

- [ ] **Step 2: Run the focused test and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_runtimes -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'socratic_learn.runtimes'`.

- [ ] **Step 3: Rename the implementation file and implement canonical runtime metadata**

Run:

```powershell
git mv socratic_learn/hosts.py socratic_learn/runtimes.py
```

Replace the public types and registry with:

```python
"""Pure runtime detection, descriptions, and argument-vector construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

RuntimeName = Literal["pi", "claude", "antigravity"]
RUNTIME_ORDER: tuple[RuntimeName, ...] = ("antigravity", "pi", "claude")


@dataclass(frozen=True)
class RuntimeAdapter:
    name: RuntimeName
    display_name: str
    description: str
    executable_names: tuple[str, ...]
    build_argv: Callable[[str, Path, str], tuple[str, ...]]


@dataclass(frozen=True)
class DetectedRuntime:
    adapter: RuntimeAdapter
    executable: str


def _pi(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    return executable, "--append-system-prompt", str(protocol), goal


def _claude(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    return executable, "--append-system-prompt-file", str(protocol), goal


def _antigravity(executable: str, protocol: Path, goal: str) -> tuple[str, ...]:
    bootstrap = (
        "Before responding, read and follow the Socratic Learn protocol at "
        f"{protocol}. The learner's initial objective is: {goal}"
    )
    return executable, "--prompt-interactive", bootstrap


RUNTIMES: Mapping[RuntimeName, RuntimeAdapter] = MappingProxyType(
    {
        "antigravity": RuntimeAdapter(
            "antigravity",
            "Antigravity",
            "full agentic environment",
            ("agy",),
            _antigravity,
        ),
        "pi": RuntimeAdapter(
            "pi",
            "Pi",
            "terminal harness; configure its provider and model separately",
            ("pi",),
            _pi,
        ),
        "claude": RuntimeAdapter(
            "claude",
            "Claude Code",
            "Anthropic's agent CLI",
            ("claude",),
            _claude,
        ),
    }
)


def detect_runtimes(
    which: Callable[[str], str | None],
) -> dict[RuntimeName, DetectedRuntime]:
    detected: dict[RuntimeName, DetectedRuntime] = {}
    for name in RUNTIME_ORDER:
        adapter = RUNTIMES[name]
        for executable_name in adapter.executable_names:
            executable = which(executable_name)
            if executable is not None:
                detected[name] = DetectedRuntime(adapter, executable)
                break
    return detected


def command_for(
    adapter: RuntimeAdapter,
    executable: str,
    protocol: Path,
    goal: str,
) -> tuple[str, ...]:
    return adapter.build_argv(executable, protocol, goal)
```

In `evaluation/antigravity.py`, replace the old host import and lookup with:

```python
from socratic_learn.runtimes import RUNTIMES, command_for


def initial_bootstrap(protocol: Path, goal: str) -> str:
    argv = command_for(
        RUNTIMES["antigravity"],
        "agy",
        protocol,
        goal,
    )
    return argv[2]
```

In `socratic_learn/launcher.py`, move the production import in the same commit
so deleting `hosts.py` never leaves the package broken:

```python
from .runtimes import (
    DetectedRuntime,
    RuntimeName,
    command_for,
    detect_runtimes,
)
```

For this focused naming task only, keep the existing `LaunchOptions.agent`
field and user-facing copy unchanged, but change its annotation to
`RuntimeName | None`, change `_prompt_for_agent` to accept
`Mapping[RuntimeName, DetectedRuntime] -> RuntimeName`, and replace
`detect_hosts(which)` with `detect_runtimes(which)`. Task 3 changes the field
and public wording under its dedicated behavior tests.

- [ ] **Step 4: Run runtime tests and a source-vocabulary search**

Run:

```powershell
python -m unittest tests.test_runtimes tests.test_launcher tests.test_evaluation_antigravity -v
rg "socratic_learn\.hosts|AgentName|HostAdapter|DetectedHost|detect_hosts|ADAPTERS" socratic_learn evaluation tests
```

Expected: runtime, existing launcher behavior, and evaluation parity tests
PASS. The search finds no production or evaluation import of
`socratic_learn.hosts` and no old registry declaration. It may still find the
temporary schema-one `AgentName` declaration in `config.py`; Task 2 removes
that declaration while preserving only the literal migration key
`default_agent`.

- [ ] **Step 5: Commit the focused rename**

```powershell
git add socratic_learn/runtimes.py socratic_learn/launcher.py evaluation/antigravity.py tests/test_runtimes.py tests/test_evaluation_antigravity.py
git add -u socratic_learn/hosts.py tests/test_hosts.py
git commit -m "refactor: name launcher runtimes"
```

---

### Task 2: Schema-2 Runtime Configuration and Safe Schema-1 Migration

**Files:**
- Modify: `socratic_learn/config.py:1-108`
- Modify: `tests/test_config.py:1-98`
- Modify: `socratic_learn/launcher.py`
- Modify: `tests/test_launcher.py`
- Modify: `tests/test_universal_smoke.py`

**Interfaces:**
- Consumes: `RuntimeName` from `socratic_learn.runtimes`
- Produces: `LauncherConfig(default_runtime: RuntimeName | None = None)`
- Produces: `load_config(path: Path) -> LauncherConfig`
- Produces: `save_config(path: Path, config: LauncherConfig) -> None`
- Invariant: `load_config` never migrates on disk; every successful `save_config` writes exact schema 2 atomically.
- Preserves temporarily: `LaunchOptions.agent` and existing selection behavior
  until Task 3, while all launcher configuration access already uses
  `default_runtime`.

- [ ] **Step 1: Replace schema-one expectations with migration and fail-closed tests**

Add these concrete tests while retaining the current permissions, symlink, and failed-publication tests with `default_runtime` names. In the existing launcher and installed universal-smoke tests, keep `LaunchOptions.agent` and `--agent` for this task but replace persisted JSON expectations with schema 2 and `default_runtime` so the complete suite remains runnable between commits:

```python
def test_missing_config_has_no_default_runtime(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        self.assertEqual(LauncherConfig(default_runtime=None), load_config(path))


def test_schema_one_loads_in_memory_without_rewrite(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        original = b'{"schema_version": 1, "default_agent": "pi"}\n'
        path.write_bytes(original)
        self.assertEqual(
            LauncherConfig(default_runtime="pi"),
            load_config(path),
        )
        self.assertEqual(original, path.read_bytes())


def test_next_explicit_write_publishes_exact_schema_two(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        path.write_text(
            '{"schema_version": 1, "default_agent": "claude"}\n',
            encoding="utf-8",
        )
        migrated = load_config(path)
        save_config(path, migrated)
        self.assertEqual(
            {"schema_version": 2, "default_runtime": "claude"},
            json.loads(path.read_text(encoding="utf-8")),
        )


def test_duplicate_keys_are_rejected_without_rewrite(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        original = (
            b'{"schema_version":2,"default_runtime":"pi",'
            b'"default_runtime":"claude"}'
        )
        path.write_bytes(original)
        with self.assertRaisesRegex(IntegrityError, "duplicate"):
            load_config(path)
        self.assertEqual(original, path.read_bytes())
```

Expand the invalid-document table to include schema 0, schema 3, booleans, mixed schema-1/schema-2 keys, unknown keys, missing keys, and invalid runtime names.

- [ ] **Step 2: Run focused tests and verify schema-2 failures**

Run:

```powershell
python -m unittest tests.test_config -v
```

Expected: FAIL because `LauncherConfig` does not accept `default_runtime`, schema 2 is rejected, and duplicate keys are not detected.

- [ ] **Step 3: Implement exact schema dispatch and duplicate-key rejection**

Replace the schema constants, dataclass, validator, and loader with:

```python
from collections.abc import Mapping

from socratic_learn.runtimes import RuntimeName

_RUNTIME_NAMES = ("pi", "claude", "antigravity")
_SCHEMA_ONE_KEYS = {"schema_version", "default_agent"}
_SCHEMA_TWO_KEYS = {"schema_version", "default_runtime"}
_REMEDIATION = "move the file aside and rerun socratic"


@dataclass(frozen=True)
class LauncherConfig:
    default_runtime: RuntimeName | None = None


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate key: {key}")
        document[key] = value
    return document


def _validated_runtime(value: object, path: Path) -> RuntimeName | None:
    if value is None:
        return None
    if type(value) is not str or value not in _RUNTIME_NAMES:
        raise _invalid_config(path, "launcher configuration has an invalid runtime")
    return value


def load_config(path: Path) -> LauncherConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return LauncherConfig()

    try:
        document = json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        message = (
            "launcher configuration contains a duplicate key"
            if isinstance(error, ValueError)
            and not isinstance(error, json.JSONDecodeError)
            else "launcher configuration is not valid JSON"
        )
        raise _invalid_config(path, message) from error

    if not isinstance(document, Mapping):
        raise _invalid_config(path, "launcher configuration must be a JSON object")
    version = document.get("schema_version")
    if type(version) is not int:
        raise _invalid_config(path, "launcher configuration schema is not supported")
    if version == 1 and set(document) == _SCHEMA_ONE_KEYS:
        return LauncherConfig(
            default_runtime=_validated_runtime(document["default_agent"], path)
        )
    if version == 2 and set(document) == _SCHEMA_TWO_KEYS:
        return LauncherConfig(
            default_runtime=_validated_runtime(document["default_runtime"], path)
        )
    if version not in {1, 2}:
        raise _invalid_config(path, "launcher configuration schema is not supported")
    raise _invalid_config(path, "launcher configuration has unexpected keys")
```

- [ ] **Step 4: Change atomic publication to exact schema 2**

Keep the existing `_reject_symlink`, exclusive temporary file, `fsync`, `os.replace`, and cleanup logic. Change only validation and payload construction:

```python
def save_config(path: Path, config: LauncherConfig) -> None:
    default_runtime = _validated_runtime(config.default_runtime, path)
    parent = path.parent
    _reject_symlink(parent, "launcher configuration parent")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _reject_symlink(parent, "launcher configuration parent")
    _reject_symlink(path, "launcher configuration destination")

    payload = json.dumps(
        {"schema_version": 2, "default_runtime": default_runtime},
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
```

In `launcher.py`, make the minimal coupled migration in the same task:

```python
elif config.default_runtime in detected:
    selected = config.default_runtime
else:
    if config.default_runtime is not None:
        output.write(
            f"Saved agent '{config.default_runtime}' is no longer available.\n"
        )
    selected = _prompt_for_agent(
        detected,
        input_fn=input_fn,
        output=output,
    )
    save_config(config_path, LauncherConfig(default_runtime=selected))
```

Do not change public copy, stale-default prompting, or the `agent` option field
in this task; Task 3 changes those behaviors under its dedicated tests.

- [ ] **Step 5: Run focused, launcher, and atomic-write tests**

Run:

```powershell
python -m unittest tests.test_config tests.test_launcher tests.test_universal_smoke -v
```

Expected: all configuration and existing launcher tests PASS; schema-1 bytes
remain unchanged after load, every explicit save contains only
`schema_version` and `default_runtime`, and the intermediate commit does not
leave the launcher calling removed configuration fields.

- [ ] **Step 6: Commit configuration migration**

```powershell
git add socratic_learn/config.py socratic_learn/launcher.py tests/test_config.py tests/test_launcher.py tests/test_universal_smoke.py
git commit -m "feat: migrate launcher config to runtimes"
```

---

### Task 3: Runtime Selection, First-Run Copy, and Launch Boundary

**Files:**
- Modify: `socratic_learn/launcher.py:1-162`
- Modify: `tests/test_launcher.py:1-356`

**Interfaces:**
- Consumes: `RuntimeName`, `DetectedRuntime`, `detect_runtimes`, `command_for`
- Consumes: `LauncherConfig(default_runtime: RuntimeName | None)`
- Produces: `LaunchOptions(goal: str | None, runtime: RuntimeName | None, here: bool, cwd: Path)`
- Produces: `prompt_for_runtime(detected: Mapping[RuntimeName, DetectedRuntime], *, input_fn: Callable[[str], str], output: TextIO) -> RuntimeName`
- Produces: `run_learning(options: LaunchOptions, *, input_fn=input, output=sys.stdout, which=shutil.which, run_process=subprocess.run, environ=None) -> int`
- Invariant: explicit runtime overrides and deprecated aliases are parsed before this layer and never save configuration.
- Invariant: a stale saved runtime is an actionable error; it is not silently replaced.

- [ ] **Step 1: Rewrite launcher tests around runtime behavior**

Change the existing `LaunchOptions` keyword `agent` to `runtime`, change `default_agent` assertions to `default_runtime`, and change launcher host wording to runtime wording. Add:

```python
def test_first_run_lists_detected_runtimes_with_descriptions_and_saves_schema_two(
    self,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output = io.StringIO()
        answers = iter(["probability", "2"])
        result = run_learning(
            LaunchOptions(None, None, False, Path.cwd()),
            input_fn=lambda prompt: next(answers),
            output=output,
            which={
                "agy": "agy",
                "pi": "pi",
                "claude": "claude",
            }.get,
            run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
            environ={"SOCRATIC_LEARN_HOME": temporary},
        )
        self.assertEqual(0, result)
        self.assertIn(
            "Where should Socratic Learn run this session?",
            output.getvalue(),
        )
        self.assertIn(
            "1. Antigravity — full agentic environment",
            output.getvalue(),
        )
        self.assertIn(
            "2. Pi — terminal harness; configure its provider and model separately",
            output.getvalue(),
        )
        self.assertIn(
            "3. Claude Code — Anthropic's agent CLI",
            output.getvalue(),
        )
        self.assertEqual(
            {"schema_version": 2, "default_runtime": "pi"},
            json.loads((Path(temporary) / "config.json").read_text("utf-8")),
        )


def test_stale_saved_runtime_errors_without_prompt_or_config_mutation(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        original = b'{"schema_version":2,"default_runtime":"claude"}\n'
        path.write_bytes(original)
        with self.assertRaisesRegex(UsageError, "socratic runtimes") as raised:
            run_learning(
                LaunchOptions("logic", None, False, Path.cwd()),
                input_fn=lambda prompt: self.fail("stale defaults do not prompt"),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )
        self.assertIn("socratic use RUNTIME", raised.exception.remediation or "")
        self.assertEqual(original, path.read_bytes())


def test_one_shot_override_does_not_create_or_rewrite_config(self) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "config.json"
        original = b'{"schema_version":1,"default_agent":"claude"}\n'
        path.write_bytes(original)
        run_learning(
            LaunchOptions("logic", "pi", False, Path.cwd()),
            output=io.StringIO(),
            which={"pi": "pi", "claude": "claude"}.get,
            run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
            environ={"SOCRATIC_LEARN_HOME": temporary},
        )
        self.assertEqual(original, path.read_bytes())
```

Retain exact argv, one-argument Unicode goal, inherited stdio/environment, child exit status, interrupt, disappeared executable, and all Windows shim tests.

- [ ] **Step 2: Run focused tests and verify old naming failures**

Run:

```powershell
python -m unittest tests.test_launcher -v
```

Expected: FAIL on the old `agent` field/imports, old first-run copy, schema-1 write, and stale-default replacement.

- [ ] **Step 3: Rename launcher types and first-run prompt**

Use these imports, dataclass, and prompt:

```python
from .runtimes import (
    DetectedRuntime,
    RuntimeName,
    command_for,
    detect_runtimes,
)


@dataclass(frozen=True)
class LaunchOptions:
    goal: str | None
    runtime: RuntimeName | None
    here: bool
    cwd: Path


def prompt_for_runtime(
    detected: Mapping[RuntimeName, DetectedRuntime],
    *,
    input_fn: Callable[[str], str],
    output: TextIO,
) -> RuntimeName:
    names = tuple(detected)
    output.write("Where should Socratic Learn run this session?\n\n")
    for number, name in enumerate(names, start=1):
        runtime = detected[name].adapter
        output.write(
            f"{number}. {runtime.display_name} — {runtime.description}\n"
        )

    while True:
        answer = input_fn("Select a runtime by number: ")
        try:
            index = int(answer)
        except ValueError:
            continue
        if 1 <= index <= len(names) and answer.strip() == str(index):
            return names[index - 1]
```

Rename `_safe_windows_host_argv` to `_safe_windows_runtime_argv` and change its error text from “host” to “runtime” without changing its command behavior.

- [ ] **Step 4: Implement saved, stale, first-run, and override selection**

Replace the selection portion of `run_learning` with:

```python
detected = detect_runtimes(which)
if not detected:
    raise UsageError(
        "no supported runtime was found",
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

selected = options.runtime
if selected is not None:
    if selected not in detected:
        raise UsageError(
            f"requested runtime '{selected}' was not detected",
            remediation="run 'socratic runtimes' to inspect detected runtimes",
        )
elif config.default_runtime is not None:
    if config.default_runtime not in detected:
        raise UsageError(
            f"the saved runtime '{config.default_runtime}' is not currently available",
            remediation=(
                "run 'socratic runtimes' to inspect detected runtimes or "
                "'socratic use RUNTIME' to choose another default"
            ),
        )
    selected = config.default_runtime
else:
    selected = prompt_for_runtime(
        detected,
        input_fn=input_fn,
        output=output,
    )
    save_config(config_path, LauncherConfig(default_runtime=selected))

runtime = detected[selected]
argv = command_for(
    runtime.adapter,
    runtime.executable,
    workspace.protocol,
    goal,
)
argv = _safe_windows_runtime_argv(runtime.executable, argv, environ)
```

Keep workspace preparation before command construction and preserve the current `subprocess.run(list(argv), cwd=workspace.root, check=False)` call. Change disappearance errors to `runtime '{selected}' executable disappeared before launch`. Do not inspect stdout/stderr or translate nonzero child statuses.

- [ ] **Step 5: Run launcher and exact command-contract tests**

Run:

```powershell
python -m unittest tests.test_runtimes tests.test_config tests.test_launcher -v
```

Expected: all tests PASS, including exact pre-existing runtime argv and child exit-code propagation.

- [ ] **Step 6: Commit launch behavior**

```powershell
git add socratic_learn/launcher.py tests/test_launcher.py
git commit -m "feat: select and launch runtimes"
```

---

### Task 4: `runtimes`, `use`, `config`, Start Equivalence, and Compatibility Routing

**Files:**
- Create: `socratic_learn/runtime_commands.py`
- Create: `tests/test_runtime_commands.py`
- Modify: `socratic_learn/cli.py:1-132`
- Modify: `tests/test_console_cli.py:1-203`

**Interfaces:**
- Produces: `format_runtime_listing(detected: Mapping[RuntimeName, DetectedRuntime], default: RuntimeName | None) -> str`
- Produces: `list_runtimes(config_path: Path, *, which=shutil.which, output=sys.stdout) -> int`
- Produces: `use_runtime(name: RuntimeName, config_path: Path, *, which=shutil.which, output=sys.stdout) -> int`
- Produces: `configure_runtime(config_path: Path, *, input_fn=input, which=shutil.which, output=sys.stdout) -> int`
- Produces: `cli.main(argv: Sequence[str] | None = None) -> int`
- Preserves: `_run_self_command(arguments: list[str]) -> int`
- Preserves: forwarding of `build`, `export`, and `install` to `administrative_main`

- [ ] **Step 1: Write failing runtime-command tests**

Create `tests/test_runtime_commands.py` with:

```python
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from socratic_learn.errors import UsageError
from socratic_learn.runtime_commands import (
    configure_runtime,
    list_runtimes,
    use_runtime,
)


class RuntimeCommandTests(unittest.TestCase):
    def test_listing_is_deterministic_and_marks_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(
                '{"schema_version":2,"default_runtime":"pi"}\n',
                encoding="utf-8",
            )
            output = io.StringIO()
            self.assertEqual(
                0,
                list_runtimes(
                    path,
                    which={"agy": "C:/agy", "pi": "C:/pi"}.get,
                    output=output,
                ),
            )
            lines = output.getvalue().splitlines()
            self.assertIn("Antigravity", lines[0])
            self.assertIn("detected: C:/agy", lines[0])
            self.assertIn("Pi", lines[1])
            self.assertIn("default", lines[1])
            self.assertIn("Claude Code", lines[2])
            self.assertIn("not detected", lines[2])

    def test_use_requires_detection_and_writes_schema_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            use_runtime(
                "pi",
                path,
                which={"pi": "C:/pi"}.get,
                output=io.StringIO(),
            )
            self.assertEqual(
                {"schema_version": 2, "default_runtime": "pi"},
                json.loads(path.read_text(encoding="utf-8")),
            )
            with self.assertRaisesRegex(UsageError, "not detected"):
                use_runtime(
                    "claude",
                    path,
                    which={"pi": "C:/pi"}.get,
                    output=io.StringIO(),
                )

    def test_config_lists_only_detected_choices_and_saves_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            prompts: list[str] = []
            configure_runtime(
                path,
                input_fn=lambda prompt: prompts.append(prompt) or "1",
                which={"pi": "C:/pi"}.get,
                output=io.StringIO(),
            )
            self.assertEqual(1, len(prompts))
            self.assertEqual(
                "pi",
                json.loads(path.read_text(encoding="utf-8"))["default_runtime"],
            )
```

- [ ] **Step 2: Add failing CLI grammar and compatibility tests**

Add these tests to `tests/test_console_cli.py`:

```python
@mock.patch("socratic_learn.cli.run_learning", return_value=0)
def test_bare_and_explicit_start_are_equivalent(self, run: mock.Mock) -> None:
    self.assertEqual(0, main(["--runtime", "pi", "linear", "algebra"]))
    first = run.call_args
    run.reset_mock()
    self.assertEqual(
        0,
        main(["start", "--runtime", "pi", "linear", "algebra"]),
    )
    self.assertEqual(first, run.call_args)


@mock.patch("socratic_learn.cli.run_learning", return_value=0)
def test_deprecated_agent_warns_and_is_one_shot(self, run: mock.Mock) -> None:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        self.assertEqual(0, main(["--agent", "pi", "logic"]))
    self.assertEqual(
        "warning: --agent is deprecated; use --runtime\n",
        stderr.getvalue(),
    )
    run.assert_called_once_with(
        LaunchOptions("logic", "pi", False, Path.cwd())
    )


@mock.patch("socratic_learn.cli.run_learning", return_value=0)
def test_learn_escapes_every_reserved_command_word(self, run: mock.Mock) -> None:
    for word in (
        "start",
        "runtimes",
        "use",
        "config",
        "doctor",
        "project",
        "update",
        "uninstall",
        "build",
        "export",
        "install",
    ):
        with self.subTest(word=word):
            run.reset_mock()
            self.assertEqual(0, main(["learn", word]))
            run.assert_called_once_with(
                LaunchOptions(word, None, False, Path.cwd())
            )


def test_runtime_and_agent_cannot_be_combined(self) -> None:
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        self.assertEqual(
            2,
            main(["--runtime", "pi", "--agent", "pi", "logic"]),
        )
    self.assertIn("not allowed with argument", stderr.getvalue())
```

Also add mocks proving `runtimes`, `use`, and `config` route to their command functions; update existing update/uninstall/build/export/install tests so they still pass unchanged.

- [ ] **Step 3: Run the new tests and verify missing command failures**

Run:

```powershell
python -m unittest tests.test_runtime_commands tests.test_console_cli -v
```

Expected: FAIL because `runtime_commands.py`, `--runtime`, and the subcommands do not exist.

- [ ] **Step 4: Implement non-launching runtime commands**

Create `socratic_learn/runtime_commands.py`:

```python
"""Read-only runtime listing and explicit launcher preference writes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import shutil
import sys
from typing import TextIO

from .config import LauncherConfig, load_config, save_config
from .errors import UsageError
from .runtimes import (
    RUNTIMES,
    RUNTIME_ORDER,
    DetectedRuntime,
    RuntimeName,
    detect_runtimes,
)


def format_runtime_listing(
    detected: Mapping[RuntimeName, DetectedRuntime],
    default: RuntimeName | None,
) -> str:
    lines: list[str] = []
    for name in RUNTIME_ORDER:
        runtime = RUNTIMES[name]
        status = (
            f"detected: {detected[name].executable}"
            if name in detected
            else "not detected"
        )
        marker = "; default" if name == default else ""
        lines.append(
            f"{runtime.display_name} — {runtime.description} "
            f"({status}{marker})"
        )
    return "\n".join(lines) + "\n"


def list_runtimes(
    config_path: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    output: TextIO = sys.stdout,
) -> int:
    config = load_config(config_path)
    output.write(
        format_runtime_listing(
            detect_runtimes(which),
            config.default_runtime,
        )
    )
    return 0


def use_runtime(
    name: RuntimeName,
    config_path: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    output: TextIO = sys.stdout,
) -> int:
    detected = detect_runtimes(which)
    if name not in detected:
        raise UsageError(
            f"runtime '{name}' was not detected",
            remediation="run 'socratic runtimes' to inspect detected runtimes",
        )
    save_config(config_path, LauncherConfig(default_runtime=name))
    output.write(f"Default runtime set to {RUNTIMES[name].display_name}.\n")
    return 0


def configure_runtime(
    config_path: Path,
    *,
    input_fn: Callable[[str], str] = input,
    which: Callable[[str], str | None] = shutil.which,
    output: TextIO = sys.stdout,
) -> int:
    detected = detect_runtimes(which)
    if not detected:
        raise UsageError(
            "no supported runtime was found",
            remediation="install Pi, Claude Code, or Antigravity and retry",
        )
    output.write(
        "Socratic Learn configuration manages only non-secret launcher "
        "preferences.\n"
    )
    names = tuple(detected)
    for number, name in enumerate(names, start=1):
        runtime = detected[name].adapter
        output.write(
            f"{number}. {runtime.display_name} — {runtime.description}\n"
        )
    while True:
        answer = input_fn("Select the default runtime by number: ")
        try:
            index = int(answer)
        except ValueError:
            continue
        if 1 <= index <= len(names) and answer.strip() == str(index):
            return use_runtime(
                names[index - 1],
                config_path,
                which=which,
                output=output,
            )
```

- [ ] **Step 5: Implement the explicit command tree in `cli.py`**

Define:

```python
_ADMIN_COMMANDS = {"build", "export", "install", "doctor"}
_SELF_COMMANDS = {"update", "uninstall"}
_LAUNCHER_COMMANDS = {"start", "runtimes", "use", "config", "doctor", "project"}
_RUNTIME_CHOICES = ("pi", "claude", "antigravity")


def _build_start_parser(prog: str = "socratic") -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog=prog,
        allow_abbrev=False,
        description="Start a Socratic learning session in a detected runtime.",
        epilog=(
            "Commands:\n"
            "  start [GOAL...]\n"
            "  runtimes\n"
            "  use RUNTIME\n"
            "  config\n"
            "  doctor\n"
            "  project doctor\n"
            "  update\n"
            "  uninstall"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--runtime",
        choices=_RUNTIME_CHOICES,
        help="override the saved runtime for this session",
    )
    selection.add_argument(
        "--agent",
        choices=_RUNTIME_CHOICES,
        help="deprecated alias for --runtime",
    )
    parser.add_argument(
        "--here",
        action="store_true",
        help="prepare learning files in the current directory",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"socratic-learn {__version__}",
    )
    parser.add_argument("goal", nargs="*")
    return parser


def _run_start(arguments: list[str], *, prog: str = "socratic") -> int:
    parsed = _build_start_parser(prog).parse_intermixed_args(arguments)
    if parsed.agent is not None:
        print(
            "warning: --agent is deprecated; use --runtime",
            file=sys.stderr,
        )
    runtime = parsed.runtime if parsed.runtime is not None else parsed.agent
    goal = " ".join(parsed.goal) if parsed.goal else None
    return run_learning(LaunchOptions(goal, runtime, parsed.here, Path.cwd()))
```

In `main`, dispatch in this order:

```python
arguments = list(sys.argv[1:] if argv is None else argv)
try:
    if arguments and arguments[0] == "learn":
        return _run_start(arguments[1:])
    if arguments and arguments[0] == "start":
        return _run_start(arguments[1:], prog="socratic start")
    if arguments and arguments[0] in _SELF_COMMANDS:
        return _run_self_command(arguments)
    if arguments and arguments[0] in _ADMIN_COMMANDS:
        return administrative_main(arguments)
    if arguments and arguments[0] == "runtimes":
        _ArgumentParser(prog="socratic runtimes").parse_args(arguments[1:])
        return list_runtimes(launcher_home() / "config.json")
    if arguments and arguments[0] == "use":
        parser = _ArgumentParser(prog="socratic use", allow_abbrev=False)
        parser.add_argument("runtime", choices=_RUNTIME_CHOICES)
        parsed = parser.parse_args(arguments[1:])
        return use_runtime(parsed.runtime, launcher_home() / "config.json")
    if arguments and arguments[0] == "config":
        _ArgumentParser(prog="socratic config").parse_args(arguments[1:])
        return configure_runtime(launcher_home() / "config.json")
    return _run_start(arguments)
except LearningTutorError as error:
    print(f"error: {error}", file=sys.stderr)
    return error.exit_code
```

Task 4 deliberately leaves the existing `socratic doctor PROJECT` administrative forwarding in place. Task 5 removes `doctor` from `_ADMIN_COMMANDS` only when launcher doctor and the `project doctor` replacement are implemented and tested together.

- [ ] **Step 6: Run command tests and verify compatibility**

Run:

```powershell
python -m unittest tests.test_runtime_commands tests.test_console_cli tests.test_self_manage -v
```

Expected: runtime command and compatibility tests PASS except Task 5 doctor/project-doctor tests, which are not added yet.

- [ ] **Step 7: Commit runtime commands and parser**

```powershell
git add socratic_learn/runtime_commands.py socratic_learn/cli.py tests/test_runtime_commands.py tests/test_console_cli.py
git commit -m "feat: add runtime launcher commands"
```

---

### Task 5: Launcher Doctor and Namespaced Project Doctor

**Files:**
- Create: `socratic_learn/launcher_doctor.py`
- Create: `tests/test_launcher_doctor.py`
- Modify: `socratic_learn/cli.py`
- Modify: `tests/test_console_cli.py`
- Verify unchanged: `socratic_learn/doctor.py`
- Verify unchanged: `socratic_learn/__main__.py`

**Interfaces:**
- Consumes: `Diagnostic` from `socratic_learn.conformance`
- Produces: `RuntimeStatus(name: RuntimeName, display_name: str, description: str, executable: str | None)`
- Produces: `LauncherDoctorReport(version: str, launcher_executable: Path, launcher_on_path: bool, config_state: str, runtimes: tuple[RuntimeStatus, ...], protocol_state: str, workspace_state: str, diagnostics: tuple[Diagnostic, ...])`
- Produces: `diagnose_launcher(home: Path, launcher_executable: Path, *, environ: Mapping[str, str] | None = None, which: Callable[[str], str | None] = shutil.which) -> LauncherDoctorReport`
- Produces: `format_launcher_report(report: LauncherDoctorReport) -> str`
- CLI routing: `socratic doctor` calls launcher diagnostics; `socratic project doctor` calls `administrative_main(["doctor", str(Path.cwd())])`.

- [ ] **Step 1: Write failing doctor boundary tests**

Create `tests/test_launcher_doctor.py` with:

```python
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from socratic_learn.launcher_doctor import (
    diagnose_launcher,
    format_launcher_report,
)


class LauncherDoctorTests(unittest.TestCase):
    def test_healthy_report_names_version_paths_runtimes_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "bin" / "socratic"
            launcher.parent.mkdir()
            launcher.write_text("launcher", encoding="utf-8")
            home = root / "home"
            report = diagnose_launcher(
                home,
                launcher,
                environ={"PATH": str(launcher.parent)},
                which={"agy": "C:/agy", "pi": "C:/pi"}.get,
            )
            text = format_launcher_report(report)
            self.assertIn("Socratic Learn 0.1.0", text)
            self.assertIn(str(launcher), text)
            self.assertIn("Antigravity", text)
            self.assertIn("C:/agy", text)
            self.assertIn("Pi", text)
            self.assertIn("C:/pi", text)
            self.assertIn("Claude Code", text)
            self.assertIn("not detected", text)
            self.assertIn(
                "does not verify authentication, billing, quota, network, or model access",
                text,
            )
            self.assertEqual((), report.diagnostics)

    def test_stale_default_is_actionable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "socratic"
            launcher.write_text("launcher", encoding="utf-8")
            home = root / "home"
            home.mkdir()
            config = home / "config.json"
            original = b'{"schema_version":1,"default_agent":"claude"}\n'
            config.write_bytes(original)
            report = diagnose_launcher(
                home,
                launcher,
                environ={"PATH": str(root)},
                which={"pi": "C:/pi"}.get,
            )
            self.assertIn(
                "saved-runtime-missing",
                [item.code for item in report.diagnostics],
            )
            self.assertEqual(original, config.read_bytes())

    def test_doctor_never_invokes_process_network_or_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / "socratic"
            launcher.write_text("launcher", encoding="utf-8")
            with (
                mock.patch(
                    "subprocess.run",
                    side_effect=AssertionError("must not run a process"),
                ),
                mock.patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError("must not use network"),
                ),
            ):
                diagnose_launcher(
                    root / "home",
                    launcher,
                    environ={"PATH": str(root), "API_KEY": "secret"},
                    which=lambda name: None,
                )
```

Add cases for missing launcher, launcher directory absent from PATH, malformed config, symlinked home/config/workspace, missing packaged protocol, stale default, and deterministic diagnostic ordering.

- [ ] **Step 2: Add failing CLI routing tests**

Add:

```python
@mock.patch("socratic_learn.cli.run_launcher_doctor", return_value=6)
def test_doctor_routes_to_launcher_diagnostics(self, doctor: mock.Mock) -> None:
    self.assertEqual(6, main(["doctor"]))
    doctor.assert_called_once()


@mock.patch("socratic_learn.cli.administrative_main", return_value=7)
def test_project_doctor_routes_to_existing_module_doctor(
    self,
    admin: mock.Mock,
) -> None:
    self.assertEqual(7, main(["project", "doctor"]))
    admin.assert_called_once_with(["doctor", str(Path.cwd())])


@mock.patch("socratic_learn.cli.administrative_main", return_value=8)
def test_existing_admin_forwarding_remains_available(
    self,
    admin: mock.Mock,
) -> None:
    for command in ("build", "export", "install"):
        with self.subTest(command=command):
            admin.reset_mock()
            self.assertEqual(8, main([command]))
            admin.assert_called_once_with([command])
```

- [ ] **Step 3: Run focused tests and verify missing doctor failures**

Run:

```powershell
python -m unittest tests.test_launcher_doctor tests.test_console_cli -v
```

Expected: FAIL because `launcher_doctor.py` and real diagnostic routing do not exist.

- [ ] **Step 4: Implement read-only launcher diagnostics**

Create these public records and diagnostic entry point:

```python
"""Read-only launcher installation and runtime diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
from typing import TextIO

from . import __version__
from .config import load_config
from .conformance import Diagnostic
from .errors import FilesystemError, IntegrityError, LearningTutorError
from .resources import resource_bytes
from .runtimes import RUNTIMES, RUNTIME_ORDER, RuntimeName, detect_runtimes


@dataclass(frozen=True)
class RuntimeStatus:
    name: RuntimeName
    display_name: str
    description: str
    executable: str | None


@dataclass(frozen=True)
class LauncherDoctorReport:
    version: str
    launcher_executable: Path
    launcher_on_path: bool
    config_state: str
    runtimes: tuple[RuntimeStatus, ...]
    protocol_state: str
    workspace_state: str
    diagnostics: tuple[Diagnostic, ...]


def diagnose_launcher(
    home: Path,
    launcher_executable: Path,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> LauncherDoctorReport:
    environment = os.environ if environ is None else environ
    diagnostics: list[Diagnostic] = []
    launcher = Path(os.path.abspath(launcher_executable))
    if launcher.is_symlink() or not launcher.is_file():
        diagnostics.append(
            Diagnostic(
                "launcher-executable-missing",
                str(launcher),
                "the launcher executable is not a regular file",
                "reinstall Socratic Learn through the active installation channel",
            )
        )

    path_entries = tuple(
        Path(os.path.abspath(entry))
        for entry in environment.get("PATH", "").split(os.pathsep)
        if entry
    )
    launcher_on_path = launcher.parent in path_entries
    if not launcher_on_path:
        diagnostics.append(
            Diagnostic(
                "launcher-not-on-path",
                str(launcher.parent),
                "the launcher scripts directory is not reachable through PATH",
                "add the launcher scripts directory to PATH and open a new shell",
            )
        )

    config_state = "not initialized"
    config = None
    if home.exists() or home.is_symlink():
        if home.is_symlink() or not home.is_dir():
            diagnostics.append(
                Diagnostic(
                    "launcher-home-unsafe",
                    str(home),
                    "launcher home is not a regular directory",
                    "replace it with a user-owned regular directory",
                )
            )
            config_state = "unavailable"
        else:
            try:
                config = load_config(home / "config.json")
                config_state = "healthy"
            except LearningTutorError as error:
                diagnostics.append(
                    Diagnostic(
                        "launcher-config-invalid",
                        str(error.path or home / "config.json"),
                        error.message,
                        error.remediation or "move the invalid configuration aside",
                    )
                )
                config_state = "invalid"

    detected = detect_runtimes(which)
    statuses = tuple(
        RuntimeStatus(
            name,
            RUNTIMES[name].display_name,
            RUNTIMES[name].description,
            detected[name].executable if name in detected else None,
        )
        for name in RUNTIME_ORDER
    )
    if (
        config is not None
        and config.default_runtime is not None
        and config.default_runtime not in detected
    ):
        diagnostics.append(
            Diagnostic(
                "saved-runtime-missing",
                str(home / "config.json"),
                f"the saved runtime '{config.default_runtime}' was not detected",
                "run 'socratic runtimes' and then 'socratic use RUNTIME'",
            )
        )

    try:
        resource_bytes("socratic-learn.prompt.md")
        protocol_state = "available"
    except LearningTutorError as error:
        protocol_state = "unavailable"
        diagnostics.append(
            Diagnostic(
                "protocol-resource-unavailable",
                str(error.path or "socratic-learn.prompt.md"),
                error.message,
                error.remediation or "reinstall Socratic Learn",
            )
        )

    workspace = home / "learning"
    if not workspace.exists() and not workspace.is_symlink():
        workspace_state = "not initialized"
    elif workspace.is_symlink() or not workspace.is_dir():
        workspace_state = "unsafe"
        diagnostics.append(
            Diagnostic(
                "personal-workspace-unsafe",
                str(workspace),
                "the personal learner workspace is not a regular directory",
                "move the conflicting path aside before starting a session",
            )
        )
    else:
        managed = workspace / ".socratic-learn"
        protocol = managed / "socratic-learn.prompt.md"
        records = managed / "workspace"
        unsafe = (
            managed.is_symlink()
            or protocol.is_symlink()
            or records.is_symlink()
            or not managed.is_dir()
            or not protocol.is_file()
            or not records.is_dir()
        )
        if unsafe:
            workspace_state = "incomplete or unsafe"
            diagnostics.append(
                Diagnostic(
                    "personal-workspace-unhealthy",
                    str(workspace),
                    "the personal learner workspace is incomplete or unsafe",
                    "preserve learner records, inspect the paths, and retry",
                )
            )
        else:
            workspace_state = "healthy"

    ordered = tuple(sorted(set(diagnostics), key=lambda item: (item.code, item.path)))
    return LauncherDoctorReport(
        __version__,
        launcher,
        launcher_on_path,
        config_state,
        statuses,
        protocol_state,
        workspace_state,
        ordered,
    )
```

```python
def format_launcher_report(report: LauncherDoctorReport) -> str:
    lines = [
        f"Socratic Learn {report.version}",
        f"Launcher: {report.launcher_executable}",
        f"PATH: {'reachable' if report.launcher_on_path else 'not reachable'}",
        f"Configuration: {report.config_state}",
        "Runtimes:",
    ]
    for runtime in report.runtimes:
        location = runtime.executable or "not detected"
        lines.append(
            f"- {runtime.display_name} — {runtime.description}: {location}"
        )
    lines.extend(
        (
            f"Protocol resource: {report.protocol_state}",
            f"Personal workspace: {report.workspace_state}",
        )
    )
    for item in report.diagnostics:
        lines.extend(
            (
                "",
                f"[{item.code}]",
                f"Path: {item.path}",
                f"Message: {item.message}",
                f"Remediation: {item.remediation}",
            )
        )
    lines.extend(
        (
            "",
            "Boundary: executable detection does not verify authentication, "
            "billing, quota, network, or model access.",
        )
    )
    return "\n".join(lines) + "\n"


def run_launcher_doctor(
    home: Path,
    launcher_executable: Path,
    *,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    output: TextIO = sys.stdout,
) -> int:
    report = diagnose_launcher(
        home,
        launcher_executable,
        environ=environ,
        which=which,
    )
    try:
        output.write(format_launcher_report(report))
        output.flush()
    except OSError as error:
        raise FilesystemError(
            "launcher doctor output could not be written",
            path="<stdout>",
            remediation="check standard output and retry",
        ) from error
    return IntegrityError.exit_code if report.diagnostics else 0
```

- [ ] **Step 5: Replace the CLI diagnostic stub with exact routing**

In `cli.py`:

```python
def _run_diagnostic_command(arguments: list[str]) -> int:
    if arguments[0] == "doctor":
        parser = _ArgumentParser(prog="socratic doctor", allow_abbrev=False)
        parser.parse_args(arguments[1:])
        return run_launcher_doctor(
            launcher_home(),
            Path(sys.argv[0]),
        )

    parser = _ArgumentParser(prog="socratic project", allow_abbrev=False)
    commands = parser.add_subparsers(dest="project_command", required=True)
    commands.add_parser("doctor", allow_abbrev=False)
    parser.parse_args(arguments[1:])
    return administrative_main(["doctor", str(Path.cwd())])
```

Do not import `diagnose` from `doctor.py` into the launcher CLI. Routing through `administrative_main` preserves the existing project-doctor output and exit behavior.

At the same time, set `_ADMIN_COMMANDS = {"build", "export", "install"}` and add the `if arguments and arguments[0] in {"doctor", "project"}: return _run_diagnostic_command(arguments)` branch immediately before the default `_run_start(arguments)` branch.

- [ ] **Step 6: Run launcher and project diagnostics**

Run:

```powershell
python -m unittest tests.test_launcher_doctor tests.test_console_cli tests.test_doctor -v
python -m socratic_learn doctor .
```

Expected: all focused tests PASS. The module doctor prints `Installation healthy.` for the repository project installation or its existing actionable diagnostics; its behavior is unchanged.

- [ ] **Step 7: Prove project doctor stayed in place and commit**

Run:

```powershell
git diff --exit-code HEAD -- socratic_learn/doctor.py socratic_learn/__main__.py
```

Expected: no diff.

```powershell
git add socratic_learn/launcher_doctor.py socratic_learn/cli.py tests/test_launcher_doctor.py tests/test_console_cli.py
git commit -m "feat: add bounded launcher diagnostics"
```

---

### Task 6: Runtime Documentation and Atomic Validator Update

**Files:**
- Modify: `README.md`
- Modify: `docs/launcher-adapters.md`
- Modify: `docs/adding-an-adapter.md`
- Modify: `docs/universal-installation.md`
- Create: `docs/runtime-model-protocol.md`
- Create: `docs/runtimes.md`
- Create: `docs/runtimes/pi.md`
- Create: `docs/runtimes/claude-code.md`
- Create: `docs/runtimes/antigravity.md`
- Create: `docs/launcher-configuration.md`
- Create: `docs/troubleshooting.md`
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Produces: public command examples matching the parser exactly.
- Produces: a five-concept boundary: protocol, runtime, model, provider, learner workspace.
- Produces: parallel operational guide headings for all three runtimes.
- Produces: validator failures for missing guides, stale launcher terminology, missing command examples, absent boundary language, and unified model-management claims.
- Preserves: installer publication caveats, security threat model language, project-adapter contracts, and all existing validator behavior.

- [ ] **Step 1: Add failing documentation-contract tests**

Extend `REQUIRED_PATHS` and fixture path sets with every new guide and `socratic_learn/runtimes.py`, `socratic_learn/runtime_commands.py`, and `socratic_learn/launcher_doctor.py`. Add tests:

```python
def test_runtime_guides_share_operational_structure(self) -> None:
    root = Path(__file__).resolve().parents[1]
    headings = (
        "## What this runtime is",
        "## Install and detect",
        "## Authentication",
        "## Model selection",
        "## Protocol delivery",
        "## Permissions, tools, and sessions",
        "## Failures and next actions",
        "## Change the Socratic Learn default",
    )
    for relative in (
        "docs/runtimes/pi.md",
        "docs/runtimes/claude-code.md",
        "docs/runtimes/antigravity.md",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        positions = [text.index(heading) for heading in headings]
        self.assertEqual(sorted(positions), positions)


def test_public_docs_define_runtime_model_protocol_boundary(self) -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/runtime-model-protocol.md").read_text(
        encoding="utf-8"
    ).lower()
    for term in ("protocol", "runtime", "model", "provider", "learner workspace"):
        self.assertIn(term, text)
    self.assertIn("does not manage models across runtimes", text)


def test_pi_guide_covers_required_operations_without_free_tier_promises(
    self,
) -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/runtimes/pi.md").read_text(encoding="utf-8").lower()
    for clause in (
        "terminal harness",
        "`/login`",
        "`/model`",
        "llama.cpp",
        "free tier",
        "quota",
        "429",
        "--append-system-prompt",
        "socratic use",
    ):
        self.assertIn(clause, text)
    self.assertNotIn("unlimited", text)
    self.assertNotIn("guaranteed free", text)


def test_documented_commands_match_runtime_command_surface(self) -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "README.md").read_text(encoding="utf-8")
    for command in (
        "socratic",
        "socratic start",
        "socratic runtimes",
        "socratic use pi",
        "socratic config",
        "socratic doctor",
        "socratic project doctor",
        "socratic update",
        "socratic uninstall",
        "socratic learn doctor",
    ):
        self.assertIn(command, text)
    self.assertNotIn("socratic model", text.lower())
```

Add mutation tests proving `validate(root)` rejects one removed guide, one removed command, one missing doctor boundary, one missing runtime-guide heading, and an inserted `socratic model set` command.

- [ ] **Step 2: Run validator tests and verify missing-doc failures**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: FAIL for missing guide paths and old README/validator contracts.

- [ ] **Step 3: Write the concept, comparison, configuration, and troubleshooting guides**

Use these exact top-level purposes:

```markdown
# Protocol, Runtime, Model, and Provider

Socratic Learn supplies a protocol. A runtime executes the session. A model
performs inference inside that runtime. A provider or local backend makes the
model available. A learner workspace stores the protocol and private learning
records.

Socratic Learn selects a runtime; it does not manage models across runtimes,
store provider credentials, inspect billing, or guarantee model access.
```

`docs/runtimes.md` must compare each runtime's role, executable, Socratic Learn protocol-delivery mechanism, where authentication/model selection belongs, and detection-only support. Use prose and bullets, not a claim that the three products share an architecture.

`docs/launcher-configuration.md` must include exact schema-1 and schema-2 JSON, explain read-only in-memory migration, state that only an explicit write migrates the file, and document every runtime/config/doctor command and `--agent` deprecation.

`docs/troubleshooting.md` must include these exact boundaries:

```text
Socratic Learn can verify launcher files, configuration, runtime executable
detection, protocol resources, and learner-workspace shape.

Executable detection does not prove runtime authentication, provider
availability, billing status, quota, network access, or model access.
```

It must map:

- launcher/config/resource/workspace failures to `socratic doctor`;
- stale defaults to `socratic runtimes` then `socratic use RUNTIME`;
- project installation failures to `socratic project doctor` from the project directory;
- Pi provider/model failures to `/login` and `/model`;
- Claude Code failures to Claude Code's own authentication/model diagnostics;
- Antigravity failures to Antigravity's own account/runtime diagnostics;
- 429 responses to provider quota/rate-limit investigation, never to a Socratic Learn model switch.

- [ ] **Step 4: Write parallel runtime guides with exact operational headings**

Each guide must contain, in order:

```markdown
## What this runtime is
## Install and detect
## Authentication
## Model selection
## Protocol delivery
## Permissions, tools, and sessions
## Failures and next actions
## Change the Socratic Learn default
```

The Pi guide must state:

```markdown
Pi is a terminal harness, not a model. Socratic Learn detects the `pi`
executable and launches it with:

`pi --append-system-prompt PROTOCOL GOAL`

Pi owns provider authentication through `/login` and model selection through
`/model`. Local inference through llama.cpp and cloud-provider free tiers are
Pi/provider capabilities, not Socratic Learn guarantees. Free tiers can change,
have quotas, and return HTTP 429 responses.
```

The Claude Code guide must show:

```markdown
`claude --append-system-prompt-file PROTOCOL GOAL`
```

The Antigravity guide must show:

```markdown
`agy --prompt-interactive BOOTSTRAP`
```

and reproduce the exact bootstrap contract from `runtimes.py`. All three guides must say the runtime inherits its normal permissions, tools, authentication, session behavior, and model selection.

- [ ] **Step 5: Rewrite README and existing launcher docs atomically**

In `README.md`, preserve installation caveats and security sections, but change launcher host/default-agent language to runtime/default-runtime language. The shortest successful path remains:

```text
socratic
```

Then document:

```text
socratic start
socratic runtimes
socratic use pi
socratic config
socratic doctor
socratic project doctor
socratic learn doctor
```

Keep direct goals with the shell-history warning and show `socratic start --runtime pi --here "linear algebra"`. Mention `--agent` only in a deprecation note.

Retitle `docs/launcher-adapters.md` internally as “Launcher Runtime Adapters,” preserve all exact argv, and change “host-owned behavior” to “runtime-owned behavior.” In `docs/adding-an-adapter.md`, preserve project-discovery adapter terminology while changing launcher-host references to launcher-runtime references. In `docs/universal-installation.md`, preserve update/uninstall behavior and distinguish:

```text
socratic doctor
socratic project doctor
python -m socratic_learn doctor PROJECT
```

- [ ] **Step 6: Implement validator requirements in the same change**

Add:

```python
RUNTIME_GUIDES = (
    "docs/runtimes/pi.md",
    "docs/runtimes/claude-code.md",
    "docs/runtimes/antigravity.md",
)
RUNTIME_GUIDE_HEADINGS = (
    "## What this runtime is",
    "## Install and detect",
    "## Authentication",
    "## Model selection",
    "## Protocol delivery",
    "## Permissions, tools, and sessions",
    "## Failures and next actions",
    "## Change the Socratic Learn default",
)
PUBLIC_RUNTIME_COMMANDS = (
    "socratic start",
    "socratic runtimes",
    "socratic use pi",
    "socratic config",
    "socratic doctor",
    "socratic project doctor",
    "socratic learn doctor",
)
FORBIDDEN_MODEL_COMMANDS = (
    "socratic model",
    "socratic provider",
)
```

Normalize README command checks to lowercase before comparing `PUBLIC_RUNTIME_COMMANDS`. Add deterministic guide-heading order validation, required concept terms, troubleshooting-boundary terms, and forbidden model/provider command checks. Preserve existing installer URL, publication caveat, POSIX threat model, link, learner privacy, semantic-run privacy, evaluation report, package-exclusion, canonical-content, generated-distribution, and release-workflow validators.

- [ ] **Step 7: Run docs tests and repository validator**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: all tests PASS and stdout is exactly `Repository validation passed.`.

- [ ] **Step 8: Commit documentation and validators together**

```powershell
git add README.md docs/launcher-adapters.md docs/adding-an-adapter.md docs/universal-installation.md
git add docs/runtime-model-protocol.md docs/runtimes.md docs/runtimes docs/launcher-configuration.md docs/troubleshooting.md
git add tests/validate_repository.py tests/test_validate_repository.py
git commit -m "docs: explain launcher runtimes"
```

---

### Task 7: Installed Package, Native Command, and Compatibility Parity

**Files:**
- Modify: `tests/test_universal_smoke.py`
- Modify: `tests/test_packaging.py`
- Modify: `.github/workflows/native-python.yml`
- Verify unchanged: `pyproject.toml`
- Verify unchanged: `socratic-learn.spec`
- Verify unchanged: `socratic_learn/self_manage.py`
- Verify unchanged: `.github/workflows/release.yml`

**Interfaces:**
- Verifies: wheel-installed and native commands expose the same runtime command grammar.
- Verifies: fake Pi launch receives unchanged protocol and goal argv.
- Verifies: schema-2 default persistence and deprecated `--agent` one-shot compatibility.
- Verifies: module project doctor, console project doctor, update, and uninstall compatibility.
- Verifies: `evaluation/` and `.semantic-runs/` remain excluded from wheels, source distributions, native executables, and public command entry points.

- [ ] **Step 1: Update the installed fake-runtime smoke test**

Change the first-run assertion to:

```python
self.assertEqual(
    {"schema_version": 2, "default_runtime": "pi"},
    json.loads((home / "config.json").read_text(encoding="utf-8")),
)
```

Change the primary explicit launch to:

```python
result = subprocess.run(
    [
        str(console),
        "start",
        "--runtime",
        "pi",
        "learn graph theory",
    ],
    cwd=root,
    env=run_environment,
    check=False,
    capture_output=True,
    text=True,
)
```

Add a second fake-runtime call using `--agent pi legacy goal`; assert the deprecation warning appears exactly once, the child status is preserved, and `config.json` bytes are unchanged.

- [ ] **Step 2: Add wheel-installed command parity**

After installing the wheel in `tests/test_packaging.py`, run:

```python
commands = (
    ([str(console), "--help"], 0, "runtimes", temporary_path),
    ([str(console), "runtimes"], 0, "Pi", temporary_path),
    ([str(console), "doctor"], 0, "Boundary:", temporary_path),
    (
        [str(python), "-m", "socratic_learn", "doctor", str(project)],
        4,
        "installation-not-found",
        temporary_path,
    ),
    (
        [str(console), "project", "doctor"],
        4,
        "installation-not-found",
        project,
    ),
)
for argv, expected_status, expected_text, working_directory in commands:
    result = subprocess.run(
        argv,
        cwd=working_directory,
        env=isolated_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    self.assertEqual(expected_status, result.returncode, result.stderr)
    self.assertIn(expected_text, result.stdout + result.stderr)
```

The test fixture must create a regular fake launcher path on PATH and set `SOCRATIC_LEARN_HOME` to an isolated directory so healthy launcher doctor returns 0.

- [ ] **Step 3: Run package and smoke tests and verify expected failures**

Run:

```powershell
python -m unittest tests.test_packaging tests.test_universal_smoke -v
```

Expected before all fixture updates are complete: FAIL on schema-one expectations or missing new command output. After the test edits and Tasks 1–6 implementation, expected: PASS.

- [ ] **Step 4: Extend normal native CI smoke coverage**

In `.github/workflows/native-python.yml`, extend the installed-wheel smoke Python block after `--version`:

```python
isolated = os.environ.copy()
isolated["SOCRATIC_LEARN_HOME"] = str(temporary / "launcher-home")
isolated["PATH"] = str(scripts)
subprocess.run([str(socratic), "--help"], env=isolated, check=True)
subprocess.run([str(socratic), "runtimes"], env=isolated, check=True)
subprocess.run([str(socratic), "doctor"], env=isolated, check=True)
```

In the project smoke block, after the existing module doctor:

```python
import shutil

socratic = shutil.which("socratic")
if socratic is None:
    raise SystemExit("installed socratic console script was not found")
subprocess.run(
    [socratic, "project", "doctor"],
    cwd=project,
    check=True,
)
```

These checks must not launch Pi, Claude Code, Antigravity, a provider, or a network request.

- [ ] **Step 5: Run compatibility suites and inspect unchanged files**

Run:

```powershell
python -m unittest tests.test_self_manage tests.test_cli tests.test_doctor tests.test_packaging tests.test_universal_smoke -v
git diff --exit-code HEAD -- pyproject.toml socratic-learn.spec socratic_learn/self_manage.py .github/workflows/release.yml
```

Expected: all tests PASS and the unchanged-file diff is empty.

- [ ] **Step 6: Commit parity coverage**

```powershell
git add tests/test_universal_smoke.py tests/test_packaging.py .github/workflows/native-python.yml
git commit -m "test: verify runtime command parity"
```

---

### Task 8: Full Verification, Protocol Byte Gate, and Pedagogy Handoff

**Files:**
- Verify all implementation, test, documentation, and workflow files listed above.
- Verify unchanged: `core/pedagogy.md`
- Verify unchanged: `core/session-protocol.md`
- Verify unchanged: `core/assessment.md`
- Verify unchanged: `core/evidence-policy.md`
- Verify unchanged: `dist/socratic-learn.prompt.md`
- Verify unchanged: `dist/manifest.json`
- Do not create a release, tag, or publication artifact.

**Interfaces:**
- Completion gate: every deterministic repository, package, native, compatibility, documentation, and no-protocol-change check passes.
- Handoff: the tracked baseline report plus runtime UX results become inputs to a separate evidence-derived pedagogy implementation plan.

- [ ] **Step 1: Search for stale source and public terminology**

Run:

```powershell
rg "socratic_learn\.hosts|AgentName|HostAdapter|DetectedHost|detect_hosts|default_agent" socratic_learn evaluation tests
rg "Available agents|compatible agent|saved agent|launcher host" README.md docs socratic_learn
```

Expected: the first search finds only the intentional schema-1 JSON key string `default_agent` and migration tests. It finds no evaluation import of `socratic_learn.hosts`. The second finds no stale launcher terminology; truthful “agent CLI” product descriptions and project-agent documentation are allowed.

- [ ] **Step 2: Run the complete unit suite**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all tests PASS with no network, provider account, credential, quota, or live model dependency.

- [ ] **Step 3: Rebuild and validate without accepting protocol changes**

Run:

```powershell
python -m socratic_learn build
git diff --exit-code -- core dist
python tests/validate_repository.py
git diff --check
```

Expected: build succeeds; `core/` and `dist/` have no diff; validator prints `Repository validation passed.`; whitespace check is silent.

- [ ] **Step 4: Build and smoke-test the wheel**

Run:

```powershell
Remove-Item -Recurse -Force package-dist -ErrorAction SilentlyContinue
python -m build --outdir package-dist
python -m unittest tests.test_packaging tests.test_universal_smoke -v
```

Expected: wheel and sdist build under ignored `package-dist/`; package and installed fake-runtime tests PASS; canonical `dist/` still contains only `manifest.json` and `socratic-learn.prompt.md`.

- [ ] **Step 5: Build and smoke-test the native executable locally**

Run:

```powershell
python -m PyInstaller socratic-learn.spec --noconfirm --distpath dist-native --workpath build-native
.\dist-native\socratic.exe --version
.\dist-native\socratic.exe --help
.\dist-native\socratic.exe runtimes
```

On POSIX, use `./dist-native/socratic`. Expected: version and help succeed; `runtimes` lists all three runtimes and returns 0 without invoking any runtime. Do not run installer, update, uninstall, tag, release, or publication workflows.

- [ ] **Step 6: Recheck the baseline prerequisite and protocol hashes**

Run the exact prerequisite command again:

```powershell
$baseline = "evaluation/reports/2026-11-06-antigravity-baseline.md"
if (-not (git ls-files --error-unmatch $baseline 2>$null)) {
    throw "Missing tracked sanitized baseline report: $baseline"
}
Get-FileHash core\*.md, dist\socratic-learn.prompt.md, dist\manifest.json -Algorithm SHA256 |
    Sort-Object Path |
    Format-Table -AutoSize
```

Expected: the same baseline path and the same six hashes recorded before Task 1.

- [ ] **Step 7: Inspect final scope and commit history**

Run:

```powershell
git status --short
git diff --stat HEAD~7..HEAD
git log --oneline -7
```

Expected: only the planned runtime implementation, tests, docs, validator, and normal native CI files changed; `graphify-out/` and any pre-existing unrelated files remain untouched; seven focused implementation commits are present; no release/tag/publication files changed.

Do not create an additional “verification” commit when no files changed.

## Completion Gate

This subproject is complete only when all of the following are true:

1. `evaluation/reports/2026-11-06-antigravity-baseline.md` is tracked before and after execution.
2. Public launcher code uses `RuntimeName`; old host/agent source types and files are gone.
3. Schema 1 loads without mutation, schema 2 writes atomically, and malformed or unsafe configuration remains fail-closed.
4. Bare start, explicit start, runtime listing/default/configuration, launcher doctor, namespaced project doctor, update, uninstall, admin forwarding, module CLI, direct goals, and `socratic learn ...` all have deterministic tests.
5. `--runtime` and deprecated `--agent` are one-shot overrides and never mutate the saved default.
6. Launcher doctor is read-only and explicitly stops at the executable-detection boundary.
7. Runtime child argv and exit-status propagation remain unchanged; provider output is not parsed.
8. README, conceptual guidance, comparison, all three parallel runtime guides, configuration guide, troubleshooting guide, and validators agree atomically.
9. No unified model/provider management, credential handling, live semantic CI, release, tag, or publication was added.
10. Unit, validator, wheel, fake-runtime, native smoke, and hosted Windows/Ubuntu/macOS normal CI gates pass.
11. `core/*.md`, protocol version, manifest, and generated protocol bytes match the pre-task hashes exactly.

## Handoff to the Evidence-Derived Pedagogy Plan

After this completion gate passes, stop this subproject. Hand `evaluation/reports/2026-11-06-antigravity-baseline.md`, its launcher/documentation finding classifications, the runtime UX commit range, deterministic test results, and hosted cross-platform results to `docs/superpowers/plans/2026-11-06-semantic-protocol-changes.md`, the evidence-derived pedagogy plan produced by the baseline subproject.

Before executing that pedagogy plan, revalidate its assumptions against the completed runtime UX command surface without changing its transcript evidence or research claims. That later plan may propose focused `core/*.md` changes only when each change is linked to observed transcript evidence and the approved research basis. It must add deterministic regression coverage before protocol changes, rebuild the generated protocol artifacts, rerun the same Antigravity scenarios with the same model, compare against the baseline, and record regressions or unresolved limitations. None of that pedagogy or post-change semantic work is folded into this runtime-command UX implementation.
