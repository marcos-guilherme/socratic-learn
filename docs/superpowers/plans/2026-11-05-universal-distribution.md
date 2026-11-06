# Universal Learning Tutor Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic English prompt bundle and a Python 3.11 standard-library CLI that safely installs, updates, and diagnoses the Learning Tutor for generic agents, Cursor, Claude Code, and Pi.

**Architecture:** Existing canonical Markdown remains the only pedagogical source. A focused `learning_tutor` package compiles deterministic artifacts, validates a machine-readable manifest, plans collision-safe project-local installations, writes owned files transactionally, and diagnoses installed copies. Thin target templates refer to a namespaced `.learning-tutor/` package; behavioral conformance tests validate contracts rather than arbitrary prose.

**Tech Stack:** Python 3.11 standard library, Markdown, JSON, `unittest`, `pathlib`, SHA-256.

## Global Constraints

- All implementation, generated content, CLI messages, and documentation are English.
- Python 3.11 or newer; no third-party dependency.
- Canonical pedagogy remains in the existing `core/` files.
- Protocol version is exactly `1.0.0`; manifest schema version is integer `1`.
- Build output is UTF-8, LF-only, deterministic, and has exactly one trailing newline.
- Initial targets are exactly `generic`, `cursor`, `claude-code`, and `pi`.
- Installation is project-local under `.learning-tutor/`.
- No existing agent file or directory is merged or overwritten automatically.
- There is no `--force` option.
- Private state lives under `.learning-tutor/workspace/` and is ignored by a nested `.gitignore`.
- Filesystem code uses `pathlib`; documented paths use `/`.
- Generated target loaders are thin and do not duplicate canonical pedagogy.

---

## File and Interface Map

```text
learning_tutor/
├── __init__.py
├── __main__.py
├── build.py
├── conformance.py
├── manifest.py
├── install.py
├── doctor.py
├── errors.py
└── templates/
    ├── generic-loader.md
    ├── cursor-skill.md
    ├── claude-loader.md
    └── pi-skill.md
dist/
├── learning-tutor.prompt.md
└── manifest.json
tests/
├── test_cli.py
├── test_build.py
├── test_manifest.py
├── test_conformance.py
├── test_install.py
├── test_doctor.py
└── test_universal_smoke.py
docs/
├── universal-installation.md
├── manifest-reference.md
└── adding-an-adapter.md
```

Shared Python interfaces:

```python
PROTOCOL_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = 1
TARGETS = ("generic", "cursor", "claude-code", "pi")

@dataclass(frozen=True)
class BuildResult:
    bundle: bytes
    manifest: dict[str, object]

@dataclass(frozen=True)
class PlannedFile:
    relative_path: str
    content: bytes
    owner: str

@dataclass(frozen=True)
class InstallPlan:
    project: Path
    target: str
    update: bool
    files: tuple[PlannedFile, ...]
    emitted_snippet: str | None

@dataclass(frozen=True)
class Diagnostic:
    code: str
    path: str
    message: str
    remediation: str
```

Stable exit codes:

```python
SUCCESS = 0
USAGE_ERROR = 2
COLLISION_ERROR = 3
INTEGRITY_ERROR = 4
FILESYSTEM_ERROR = 5
```

---

### Task 1: Package Skeleton, Errors, and CLI Parsing

**Files:**
- Create: `learning_tutor/__init__.py`
- Create: `learning_tutor/__main__.py`
- Create: `learning_tutor/errors.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Produces: version constants, error hierarchy, `main(argv: Sequence[str] | None = None) -> int`.
- Defers command execution to functions imported lazily from later modules.

- [ ] **Step 1: Write failing CLI and error tests**

Create tests for:

```python
class CliContractTests(unittest.TestCase):
    def test_no_command_returns_usage_error(self) -> None:
        self.assertEqual(2, main([]))

    def test_unknown_command_returns_usage_error(self) -> None:
        self.assertEqual(2, main(["unknown"]))

    def test_install_rejects_unknown_target(self) -> None:
        self.assertEqual(2, main(["install", "unknown", "."]))

    def test_force_option_does_not_exist(self) -> None:
        self.assertEqual(
            2, main(["install", "generic", ".", "--force"])
        )

    def test_error_classes_have_stable_exit_codes(self) -> None:
        self.assertEqual(3, CollisionError("x").exit_code)
        self.assertEqual(4, IntegrityError("x").exit_code)
        self.assertEqual(5, FilesystemError("x").exit_code)
```

Capture stderr and assert usage failures contain the command and a safe next
action, not a traceback.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m unittest tests.test_cli -v
```

Expected: import failure for `learning_tutor`.

- [ ] **Step 3: Implement constants and errors**

`learning_tutor/__init__.py`:

```python
PROTOCOL_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = 1
TARGETS = ("generic", "cursor", "claude-code", "pi")
```

`learning_tutor/errors.py` defines `LearningTutorError`, `UsageError`,
`CollisionError`, `IntegrityError`, and `FilesystemError`. Every error has
`exit_code`, `path`, and `remediation`; `__str__` includes all supplied fields.

- [ ] **Step 4: Implement CLI parsing**

Use `argparse` without terminating the interpreter: subclass
`ArgumentParser.error()` to raise `UsageError`. Define:

```text
build
export prompt [--output FILE]
install TARGET PROJECT [--update]
doctor PROJECT
```

`main()` catches only `LearningTutorError`, prints one actionable line to
stderr, and returns its code. Unexpected exceptions are not swallowed. Until
later tasks exist, command dispatch functions may raise an `IntegrityError`
stating that the implementation is unavailable; CLI parsing tests mock those
dispatch functions.

- [ ] **Step 5: Run tests and commit**

```powershell
python -m unittest tests.test_cli -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor tests/test_cli.py
git commit -m "feat: add universal tutor CLI contract"
```

---

### Task 2: Deterministic Manifest and Build Pipeline

**Files:**
- Create: `learning_tutor/manifest.py`
- Create: `learning_tutor/build.py`
- Create: `tests/test_manifest.py`
- Create: `tests/test_build.py`
- Create: `dist/learning-tutor.prompt.md`
- Create: `dist/manifest.json`

**Interfaces:**
- Produces: `sha256_bytes(data: bytes) -> str`
- Produces: `serialize_json(value: object) -> bytes`
- Produces: `validate_manifest(manifest: Mapping[str, object]) -> None`
- Produces: `build_distribution(root: Path) -> BuildResult`
- Produces: `write_distribution(root: Path, result: BuildResult) -> tuple[Path, Path]`

- [ ] **Step 1: Write failing manifest tests**

Cover sorted deterministic JSON, final newline, lowercase 64-character hashes,
schema/protocol/language validation, exact target set, source-path uniqueness,
bundle hash format, capability fallback presence, and exact session heading
sequence.

Use one valid fixture factory so each invalid test mutates one field.

- [ ] **Step 2: Write failing build tests**

Use a temporary minimal repository fixture. Assert:

- identical builds return identical bytes;
- CRLF sources normalize to LF;
- missing source fails with its relative path;
- invalid UTF-8 fails;
- absolute local paths are rejected;
- output header contains protocol version and relative sources;
- one and only one trailing newline;
- adapter-specific loader instructions do not enter the bundle;
- manifest source and bundle hashes match bytes.

- [ ] **Step 3: Run tests and confirm RED**

```powershell
python -m unittest tests.test_manifest tests.test_build -v
```

- [ ] **Step 4: Implement manifest primitives**

`serialize_json()` uses:

```python
json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
```

encoded as UTF-8. `validate_manifest()` rejects unknown schema versions,
malformed hashes, missing required capabilities/fallbacks, target drift,
absolute paths, duplicate source paths, and a bundle path other than
`learning-tutor.prompt.md`.

- [ ] **Step 5: Implement deterministic build**

Define explicit source order:

```python
CANONICAL_SOURCES = (
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
)
```

Read UTF-8 strictly, normalize line endings, strip only outer blank lines, and
compose fixed section markers. Build a compact curriculum index from node
headings rather than embedding both full maps twice. Include capability and
session contracts in the manifest. Validate before returning.

- [ ] **Step 6: Connect CLI build/export**

`build` writes `dist/` atomically within the repository and prints relative
paths plus hashes. `export prompt` validates existing `dist/manifest.json` and
bundle hash, then writes exact bundle bytes to stdout or `--output`.

- [ ] **Step 7: Generate checked-in artifacts, test, and commit**

```powershell
python -m learning_tutor build
python -m unittest tests.test_manifest tests.test_build tests.test_cli -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor dist tests
git commit -m "feat: build deterministic tutor distribution"
```

Run `python -m learning_tutor build` twice and verify `git diff --exit-code
-- dist` after the second build.

---

### Task 3: Behavioral Conformance Validation

**Files:**
- Create: `learning_tutor/conformance.py`
- Create: `tests/test_conformance.py`
- Modify: `learning_tutor/build.py`
- Modify: `dist/learning-tutor.prompt.md`
- Modify: `dist/manifest.json`

**Interfaces:**
- Produces: `check_conformance(bundle: str) -> list[Diagnostic]`
- Build fails with `IntegrityError` when diagnostics are non-empty.

- [ ] **Step 1: Write failing conformance tests**

Create one minimal passing bundle fixture and one focused test for each
behavior:

```text
observable outcome
bounded diagnosis
plan approval before teaching
responsive Socratic follow-up
exposition fallback
active return after exposition
mathematical assumptions/classification
primary-source verification for volatile claims
capability fallbacks
private state
evidence-based closure
```

Each test removes or mutates one semantic marker and asserts a stable diagnostic
code. Do not compare the complete prompt or require decorative wording.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m unittest tests.test_conformance -v
```

- [ ] **Step 3: Implement contract checks**

Use small, explicit marker groups with alternatives and section-scoped checks.
For ordering contracts, locate normalized section markers and compare indexes.
Return all diagnostics in deterministic code/path order.

- [ ] **Step 4: Integrate build and regenerate**

Call conformance after composing the bundle and before creating the manifest.
Represent the conformance contract version and required diagnostic codes in
the manifest without copying prose.

- [ ] **Step 5: Verify and commit**

```powershell
python -m learning_tutor build
python -m unittest tests.test_conformance tests.test_build -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor dist tests/test_conformance.py
git commit -m "test: enforce tutor behavior conformance"
```

---

### Task 4: Generic Installation, Receipts, and Safe Updates

**Files:**
- Create: `learning_tutor/install.py`
- Create: `learning_tutor/templates/generic-loader.md`
- Create: `tests/test_install.py`
- Modify: `learning_tutor/__main__.py`

**Interfaces:**
- Produces: `plan_install(source_root: Path, project: Path, target: str, update: bool) -> InstallPlan`
- Produces: `apply_install(plan: InstallPlan) -> None`
- Produces: `load_receipt(project: Path) -> dict[str, object]`

- [ ] **Step 1: Write failing planning tests**

Cover nonexistent project, non-directory project, clean generic install,
`.learning-tutor` collision, workspace layout, nested ignore rules, loader
content, receipt ownership, unsupported target, and no mutation during
planning.

- [ ] **Step 2: Write failing update tests**

Cover:

- unchanged owned files update successfully;
- modified owned file aborts;
- missing owned file aborts;
- invalid/missing receipt aborts;
- receipt path escape (`../`) aborts;
- unowned target path collision aborts;
- no `--force` escape exists.

- [ ] **Step 3: Run tests and confirm RED**

```powershell
python -m unittest tests.test_install -v
```

- [ ] **Step 4: Implement planning and receipt validation**

`PlannedFile`, `InstallPlan`, and receipt dataclasses are frozen. All receipt
paths are normalized POSIX relative paths and rejected if absolute or if any
part is `..`.

Generic installation owns:

```text
.learning-tutor/manifest.json
.learning-tutor/learning-tutor.prompt.md
.learning-tutor/install.json
.learning-tutor/loader.md
.learning-tutor/.gitignore
.learning-tutor/workspace/.gitkeep
```

`install.json` is an owned path but is excluded from its own hash map. The
receipt records hashes for every other owned file; tests must assert that the
self path is listed as owned without a recursive self-hash. Receipt schema,
protocol, paths, and referenced hashes remain mandatory.

The nested ignore file contains:

```gitignore
workspace/*
!workspace/.gitkeep
```

- [ ] **Step 5: Implement transactional application**

Stage all content under a unique directory adjacent to `.learning-tutor`.
Validate staged hashes, create only previously absent parent directories, and
publish files with atomic no-overwrite operations. Clean private staging after
a pre-publication failure using recorded topology and identity checks. Once any
path is published, recovery must not intentionally remove, rename, or unlink
published destinations; preserve identifiable partial paths and private
recovery artifacts and report detected ambiguity in an actionable
`FilesystemError`.

For update, atomically move each owned file to a same-filesystem private backup
and verify the backup hash. Restore only by atomic no-overwrite publication
into an absent destination; preserve both paths on a collision. Publish the
receipt last so interrupted installs remain diagnosably unhealthy.

Acceptance uses the following threat model: the controls protect against
ordinary collisions, accidental concurrent changes, and cooperating Learning
Tutor processes. Updates must not knowingly overwrite modified or unowned
files, and detected ambiguity must be preserved. Malicious or noncooperating
processes running as the same OS principal are out of scope on POSIX because
`rename`, `unlink`, and `rmdir` retain an irreducible leaf-entry TOCTOU syscall
gap; no absolute guarantee extends across that gap. Normal Linux and macOS
build, install, update, and cleanup remain enabled.

- [ ] **Step 6: Connect generic CLI and test**

`install generic PROJECT` prints the loader after success. `--update` prints
the protocol transition and does not rewrite unchanged private state.

```powershell
python -m unittest tests.test_install tests.test_cli -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor tests/test_install.py
git commit -m "feat: add safe generic tutor installation"
```

---

### Task 5: Cursor, Claude Code, and Pi Targets

**Files:**
- Create: `learning_tutor/templates/cursor-skill.md`
- Create: `learning_tutor/templates/claude-loader.md`
- Create: `learning_tutor/templates/pi-skill.md`
- Modify: `learning_tutor/install.py`
- Modify: `tests/test_install.py`

**Interfaces:**
- Extends `plan_install()` for all target-specific owned paths.
- Claude may return `emitted_snippet` without owning root `CLAUDE.md`.

- [ ] **Step 1: Write failing target installation tests**

Cursor tests:

- clean skill installation;
- pre-existing skill directory collision, including empty directory;
- loader links resolve to namespaced bundle/state.

Claude Code tests:

- absent root `CLAUDE.md` becomes an owned thin loader;
- existing root `CLAUDE.md` remains byte-identical and returns exact manual
  snippet;
- update never claims an unowned existing loader.

Pi tests:

- clean skill installation;
- pre-existing skill directory collision, including empty directory;
- loader links resolve to namespaced bundle/state.

All target templates must be absent from the generated universal prompt.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m unittest tests.test_install -v
```

- [ ] **Step 3: Implement thin templates**

Each loader:

- identifies the universal prompt path;
- requires reading it before a learning session;
- identifies `.learning-tutor/workspace/` as private state;
- maps only target discovery/capability details;
- contains no copied canonical sections.

Claude's manual snippet and installed loader are generated from one template
function with a path-base parameter.

- [ ] **Step 4: Implement target plans**

Owned native paths:

```text
cursor: .cursor/skills/learning-tutor/SKILL.md
claude-code: CLAUDE.md only when absent
pi: .pi/skills/learning-tutor/SKILL.md
```

Check complete destination directories before any mutation. A collision aborts
the whole plan. Existing Claude loader is the sole exception: it is preserved,
not owned, and produces a snippet.

Publish absent native and Claude files by an adjacent hard link with complete
parent-chain verification before and after publication. Publish target files
before package state and the receipt last. Before the first publication,
failures clean private staging; afterward, preserve all partial published
paths and recovery artifacts without deleting or renaming them, and report the
manual recovery state. Update backup restoration is no-overwrite only.

- [ ] **Step 5: Test and commit**

```powershell
python -m unittest tests.test_install -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor tests/test_install.py
git commit -m "feat: add universal agent target installers"
```

---

### Task 6: Doctor and Integrity Diagnostics

**Files:**
- Create: `learning_tutor/doctor.py`
- Create: `tests/test_doctor.py`
- Modify: `learning_tutor/__main__.py`

**Interfaces:**
- Produces: `diagnose(project: Path) -> list[Diagnostic]`
- Produces: `format_diagnostics(diagnostics: Sequence[Diagnostic]) -> str`

- [ ] **Step 1: Write failing doctor tests**

Create a valid installed-project fixture using the installer, then mutate one
condition per test:

- missing receipt;
- invalid receipt schema;
- changed owned file;
- missing owned file;
- bundle/manifest hash mismatch;
- protocol mismatch;
- broken loader link;
- wrong native discovery path;
- missing nested ignore rule;
- tracked private file when project is a Git repository;
- valid installation has no diagnostics.

Assert deterministic diagnostic ordering, stable codes, path, message, and
remediation.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m unittest tests.test_doctor -v
```

- [ ] **Step 3: Implement read-only diagnosis**

Doctor never repairs. Reuse manifest/receipt/hash/link helpers from existing
modules rather than copying validation logic. Git checks use
`git -C PROJECT ls-files -- .learning-tutor/workspace` when Git is available;
a Git execution failure in a detected repository is an integrity diagnostic,
not silently ignored.

- [ ] **Step 4: Connect CLI**

`doctor` prints `Installation healthy.` and exits `0` when empty. Any
diagnostic prints one actionable block and exits `4`. Invalid project path
returns the appropriate filesystem or usage code.

- [ ] **Step 5: Test and commit**

```powershell
python -m unittest tests.test_doctor tests.test_cli -v
python -m unittest discover -s tests -p "test_*.py" -v
git add learning_tutor tests/test_doctor.py
git commit -m "feat: diagnose universal tutor installations"
```

---

### Task 7: Repository Validation, Documentation, and End-to-End Smoke

**Files:**
- Create: `tests/test_universal_smoke.py`
- Create: `docs/universal-installation.md`
- Create: `docs/manifest-reference.md`
- Create: `docs/adding-an-adapter.md`
- Modify: `README.md`
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Extends repository validation to universal source and generated artifacts.
- Produces a user-complete English onboarding path.

- [ ] **Step 1: Write failing repository-contract tests**

Require package modules, templates, generated artifacts, and three
documentation files. Validate checked-in manifest and bundle hashes against
current canonical sources. Ensure generated files have the expected header and
no absolute paths.

- [ ] **Step 2: Write failing smoke test**

In temporary directories:

1. copy only tracked repository files;
2. build twice and compare bundle/manifest bytes;
3. install all four targets separately;
4. run `diagnose()` and require no findings;
5. create a private state file and verify nested ignore behavior in a temporary
   Git repository;
6. run unchanged `--update`;
7. mutate one managed file and confirm update aborts without changing any
   other file.

- [ ] **Step 3: Write documentation**

Root README gains:

- definition and limits of universal;
- Python 3.11 requirement;
- five command examples;
- target support;
- safety/ownership behavior;
- private-state location;
- link to detailed docs.

`docs/universal-installation.md` contains generic and per-target walkthroughs,
collision behavior, update flow, and doctor interpretation.

`docs/manifest-reference.md` documents every schema field, version policy, and
hash semantics using the checked-in manifest as the concrete example.

`docs/adding-an-adapter.md` defines template boundaries, ownership paths,
required collision tests, loader-link rules, and the prohibition on canonical
prose duplication.

- [ ] **Step 4: Extend repository validator**

Invoke build in memory and compare it byte-for-byte with checked-in `dist/`.
Require all new files and docs. Continue using only standard library. Report
stale generated artifacts with the command:

```text
python -m learning_tutor build
```

- [ ] **Step 5: Run complete verification**

```powershell
python -m learning_tutor build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
git status --short
```

Expected: all tests pass, validator prints success, and only intended Task 7
files are uncommitted.

- [ ] **Step 6: Commit and run clean-copy smoke**

```powershell
git add README.md docs learning_tutor dist tests
git commit -m "docs: publish universal tutor workflow"
```

Clone the committed branch into a unique temporary directory, run:

```powershell
python -m learning_tutor build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
```

Expected: all commands exit `0`; rebuilding leaves `dist/` byte-identical and
the clone clean.

- [ ] **Step 7: Final state**

```powershell
git status --short --branch
git log --oneline -10
```

Expected: clean feature branch with focused commits and no tracked private
learner state.

