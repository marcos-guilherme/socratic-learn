# Socratic Learn Rename and Public Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Socratic Learn the canonical public and technical identity, preserve safe migration from Learning Tutor, and publish a documented public GitHub repository.

**Architecture:** Move the implementation into `socratic_learn`, retain `learning_tutor` as a two-file deprecation shim, and make the manifest, receipt, installer, doctor, adapters, and generated artifacts use explicit canonical identifiers. Legacy installation migration is an update mode authorized only by the existing receipt and hashes; publication remains receipt-last and no-replace. Repository publication happens only after a reviewed merge and complete local verification.

**Tech Stack:** Python 3.11 standard library, `unittest`, Markdown, GitHub Actions, Git, and GitHub CLI.

## Global Constraints

- Public product name is `Socratic Learn`; repository name is `socratic-learn`.
- Canonical Python package is `socratic_learn`; `learning_tutor` is a deprecated forwarding shim only.
- Canonical managed root is `.socratic-learn/`; canonical skill identifier is `socratic-learn`.
- Canonical generated prompt is `dist/socratic-learn.prompt.md`.
- New public documentation is English.
- Python 3.11 is the minimum version; runtime dependencies remain standard-library only.
- There is no `--force`.
- Never knowingly overwrite modified or unowned files; preserve detected ambiguity and report recovery paths.
- The documented filesystem threat model remains unchanged.
- Existing exit codes, `TARGETS`, Claude root-loader behavior, receipt-last publication, and `safe_fs` semantics remain compatible.
- Public repository visibility is public and the license is MIT.

---

## File Structure

### Canonical implementation

- Create `socratic_learn/` by moving the current implementation and package templates from `learning_tutor/`.
- Keep only `learning_tutor/__init__.py` and `learning_tutor/__main__.py` as the legacy forwarding package.
- Keep `socratic_learn/safe_fs.py` behavior unchanged except import/package paths.

### Canonical distribution and adapters

- Replace `dist/learning-tutor.prompt.md` with `dist/socratic-learn.prompt.md`.
- Replace `.cursor/skills/learning-tutor/` with `.cursor/skills/socratic-learn/`.
- Replace `adapters/pi/skills/learning-tutor/` with `adapters/pi/skills/socratic-learn/`.
- Keep adapter READMEs responsible only for host-specific discovery and installation.

### Migration boundary

- `socratic_learn/install.py` owns canonical and legacy receipt parsing, install planning, and transactional migration.
- `socratic_learn/doctor.py` remains read-only and reports canonical health, legacy migration availability, and root collisions.
- `socratic_learn/manifest.py` owns the closed canonical manifest contract.

### Public onboarding

- `README.md` owns first-use onboarding.
- `docs/universal-installation.md` owns command and migration details.
- `docs/manifest-reference.md` owns artifact schema details.
- `docs/adding-an-adapter.md` owns extension contracts.
- `LICENSE` contains the MIT license.

---

### Task 1: Canonical Python Package and Legacy CLI Shim

**Files:**
- Create: `socratic_learn/__init__.py`
- Create: `socratic_learn/__main__.py`
- Move: `learning_tutor/{build.py,conformance.py,doctor.py,errors.py,export.py,install.py,manifest.py,safe_fs.py,templates/}` to `socratic_learn/`
- Modify: `learning_tutor/__init__.py`
- Modify: `learning_tutor/__main__.py`
- Modify: `tests/test_cli.py`
- Modify: imports and patch targets in `tests/test_*.py`
- Modify: imports in `tests/validate_repository.py`

**Interfaces:**
- Produces: `socratic_learn.__main__.main(argv: Sequence[str] | None = None) -> int`
- Produces: canonical command `python -m socratic_learn`
- Preserves: `python -m learning_tutor`, with one deprecation warning on stderr
- Preserves: `LearningTutorError` as an import-compatible alias during the compatibility window
- Preserves: exit codes `1`, `2`, `3`, `4`, and `5`

- [ ] **Step 1: Write failing canonical-command and shim tests**

Add focused tests:

```python
def test_parser_uses_canonical_program_name() -> None:
    parser = socratic_main._build_parser()
    assert parser.prog == "socratic-learn"


def test_legacy_module_warns_once_and_forwards() -> None:
    repository = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "-m", "learning_tutor", "--help"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "deprecated" in completed.stderr.lower()
    assert completed.stderr.count("\n") == 1
    assert "socratic-learn" in completed.stdout
```

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_cli -v
```

Expected: import or assertion failures because `socratic_learn` and the canonical program name do not exist.

- [ ] **Step 3: Move the implementation package**

Use tracked moves:

```powershell
git mv learning_tutor socratic_learn
New-Item -ItemType Directory learning_tutor
```

Restore only the compatibility package files in `learning_tutor/`.

- [ ] **Step 4: Implement the canonical CLI and forwarding shim**

Canonical CLI changes:

```python
parser = _ArgumentParser(prog="socratic-learn", allow_abbrev=False)
```

Use canonical import names in unavailable-command checks:

```python
if error.name != "socratic_learn.build":
    raise
```

Legacy package:

```python
# learning_tutor/__init__.py
from socratic_learn import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION, TARGETS
from socratic_learn.errors import LearningTutorError

__all__ = [
    "LearningTutorError",
    "MANIFEST_SCHEMA_VERSION",
    "PROTOCOL_VERSION",
    "TARGETS",
]
```

```python
# learning_tutor/__main__.py
from __future__ import annotations

import sys

from socratic_learn.__main__ import main


if __name__ == "__main__":
    sys.stderr.write(
        "warning: 'python -m learning_tutor' is deprecated; "
        "use 'python -m socratic_learn'\n"
    )
    raise SystemExit(main())
```

- [ ] **Step 5: Retarget imports and mocks**

Replace implementation imports and mock targets with `socratic_learn`.
Do not preserve import compatibility for `learning_tutor.install`,
`learning_tutor.build`, or other implementation submodules.

- [ ] **Step 6: Run focused package and CLI tests**

Run:

```powershell
python -m unittest tests.test_cli tests.test_safe_fs -v
python -m socratic_learn --help
python -m learning_tutor --help
```

Expected: all tests pass; canonical help uses `socratic-learn`; legacy help matches and emits exactly one warning.

- [ ] **Step 7: Commit**

```powershell
git add -A
git commit -m "refactor: make socratic_learn canonical package"
```

---

### Task 2: Canonical Manifest, Build, and Export Artifacts

**Files:**
- Modify: `socratic_learn/__init__.py`
- Modify: `socratic_learn/manifest.py`
- Modify: `socratic_learn/build.py`
- Modify: `socratic_learn/export.py`
- Delete: `dist/learning-tutor.prompt.md`
- Create: `dist/socratic-learn.prompt.md`
- Modify: `dist/manifest.json`
- Modify: `tests/test_manifest.py`
- Modify: `tests/test_build.py`
- Modify: `tests/test_conformance.py`

**Interfaces:**
- Produces: `PRODUCT_ID = "socratic-learn"`
- Produces: `MANIFEST_SCHEMA_VERSION = 2`
- Produces: manifest key `"product": "socratic-learn"`
- Produces: `bundle.path == "socratic-learn.prompt.md"`
- Produces: bundle heading `# Socratic Learn`
- Preserves: `PROTOCOL_VERSION = "1.0.0"` and deterministic serialization

- [ ] **Step 1: Write failing closed-schema and artifact tests**

```python
def test_manifest_identifies_socratic_learn() -> None:
    manifest = build_manifest()
    assert manifest["product"] == "socratic-learn"
    assert manifest["bundle"]["path"] == "socratic-learn.prompt.md"


def test_legacy_bundle_name_is_rejected() -> None:
    manifest = build_manifest()
    manifest["bundle"]["path"] = "learning-tutor.prompt.md"
    with self.assertRaises(IntegrityError):
        validate_manifest(manifest)


def test_bundle_uses_product_heading() -> None:
    repository = Path(__file__).resolve().parents[1]
    distribution = build_distribution(repository)
    self.assertTrue(distribution.bundle.startswith(b"# Socratic Learn\n"))
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m unittest tests.test_manifest tests.test_build tests.test_conformance -v
```

Expected: failures for the missing product field, old path, and old heading.

- [ ] **Step 3: Extend the closed manifest**

Define:

```python
PRODUCT_ID = "socratic-learn"
MANIFEST_SCHEMA_VERSION = 2
```

Add `"product"` to `_TOP_LEVEL_KEYS`, require exact string equality with
`PRODUCT_ID`, and change remediation to:

```python
_REMEDIATION = "regenerate the manifest with 'socratic-learn build'"
```

Construct the manifest with:

```python
"product": PRODUCT_ID,
"bundle": {
    "path": "socratic-learn.prompt.md",
    "sha256": sha256_bytes(bundle),
},
```

- [ ] **Step 4: Rename all build-owned artifact references**

Change the bundle heading and exact owned-tree set:

```python
BUNDLE_NAME = "socratic-learn.prompt.md"
EXPECTED_DIST_ENTRIES = {"manifest.json", BUNDLE_NAME}
```

Use `BUNDLE_NAME` for staging, conformance paths, and cleanup validation.
`export_prompt` must continue deriving its source path from the manifest.

- [ ] **Step 5: Rebuild deterministic artifacts**

Run twice:

```powershell
python -m socratic_learn build
git diff -- dist
python -m socratic_learn build
git diff --check
```

Expected: the first run replaces the prompt and manifest; the second run produces no additional diff.

- [ ] **Step 6: Run focused tests and validator inputs**

```powershell
python -m unittest tests.test_manifest tests.test_build tests.test_conformance -v
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn dist tests
git commit -m "feat: generate Socratic Learn distribution"
```

---

### Task 3: Canonical Installer, Receipt Schema, and Templates

**Files:**
- Modify: `socratic_learn/install.py`
- Modify: `socratic_learn/templates/generic-loader.md`
- Modify: `socratic_learn/templates/cursor-skill.md`
- Modify: `socratic_learn/templates/claude-loader.md`
- Modify: `socratic_learn/templates/pi-skill.md`
- Modify: `tests/test_install.py`

**Interfaces:**
- Produces: `INSTALL_ROOT = ".socratic-learn"`
- Produces: `RECEIPT_PATH = ".socratic-learn/install.json"`
- Produces: schema-2 canonical receipts with `"product": "socratic-learn"`
- Consumes: schema-1 legacy receipts through a separate exact parser
- Produces: `InstallReceipt.product: str`
- Produces: installed bundle path from `manifest["bundle"]["path"]`
- Preserves: target set and Claude snippet behavior

- [ ] **Step 1: Write failing clean-install and receipt tests**

```python
def test_new_install_uses_only_canonical_paths(self) -> None:
    install("cursor", self.project, source_root=self.source)
    self.assertTrue(
        (self.project / ".socratic-learn/install.json").is_file()
    )
    self.assertTrue(
        (self.project / ".cursor/skills/socratic-learn/SKILL.md").is_file()
    )
    self.assertFalse((self.project / ".learning-tutor").exists())


def test_canonical_receipt_has_closed_product_identity(self) -> None:
    receipt = json.loads(
        (self.project / ".socratic-learn/install.json").read_text("utf-8")
    )
    self.assertEqual(receipt["schema_version"], 2)
    self.assertEqual(receipt["product"], "socratic-learn")
    self.assertEqual(
        set(receipt),
        {
            "schema_version",
            "product",
            "protocol_version",
            "target",
            "owned_paths",
            "hashes",
        },
    )
```

- [ ] **Step 2: Run failing installer tests**

```powershell
python -m unittest tests.test_install -v
```

Expected: canonical paths and schema-2 assertions fail.

- [ ] **Step 3: Add explicit receipt versions**

Use exact key sets:

```python
_LEGACY_RECEIPT_KEYS = {
    "schema_version",
    "protocol_version",
    "target",
    "owned_paths",
    "hashes",
}
_CANONICAL_RECEIPT_KEYS = _LEGACY_RECEIPT_KEYS | {"product"}
LEGACY_INSTALL_ROOT = ".learning-tutor"
LEGACY_RECEIPT_PATH = f"{LEGACY_INSTALL_ROOT}/install.json"
```

Extend the dataclass:

```python
@dataclass(frozen=True)
class InstallReceipt:
    schema_version: int
    product: str
    protocol_version: str
    target: str
    owned_paths: tuple[str, ...]
    hashes: tuple[tuple[str, str], ...]
```

Canonical `as_dict()` includes `product`; legacy parsing sets
`product="learning-tutor"` only after exact schema-1 validation.

- [ ] **Step 4: Rename canonical install paths**

Define:

```python
INSTALL_ROOT = ".socratic-learn"
RECEIPT_PATH = f"{INSTALL_ROOT}/install.json"
_NATIVE_SKILL_PATHS = {
    "cursor": ".cursor/skills/socratic-learn/SKILL.md",
    "pi": ".pi/skills/socratic-learn/SKILL.md",
}
```

Use `.socratic-learn-stage-` and `.socratic-learn-backup-` prefixes.
Derive the installed prompt path from `manifest["bundle"]["path"]`; do not
hardcode a second filename.

- [ ] **Step 5: Update templates**

Set skill frontmatter to:

```yaml
---
name: socratic-learn
description: Conduct evidence-aware Socratic mathematics and AI learning sessions.
---
```

All template links use `.socratic-learn/socratic-learn.prompt.md` and
`.socratic-learn/workspace/`.

- [ ] **Step 6: Run focused install tests**

```powershell
python -m unittest tests.test_install -v
```

Expected: clean installs and same-root canonical updates pass for all four targets; collision and race tests remain green.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn tests/test_install.py
git commit -m "feat: install canonical Socratic Learn layout"
```

---

### Task 4: Transactional Legacy Migration and Doctor Support

**Files:**
- Modify: `socratic_learn/install.py`
- Modify: `socratic_learn/doctor.py`
- Create: `tests/legacy_install_fixture.py`
- Modify: `tests/test_install.py`
- Modify: `tests/test_doctor.py`
- Modify: `tests/test_universal_smoke.py`

**Interfaces:**
- Produces: `InstallPlan.migrate_legacy: bool`
- Produces: `InstallPlan.legacy_receipt: InstallReceipt | None`
- Produces: doctor code `legacy-installation`
- Produces: doctor code `installation-root-collision`
- Consumes: schema-1 receipt at `.learning-tutor/install.json`
- Migration entry point remains `install TARGET PROJECT --update`

- [ ] **Step 1: Write failing migration authorization tests**

Create a reusable fixture builder whose file hashes are derived from the
bytes it writes:

```python
# tests/legacy_install_fixture.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def create_valid_legacy_install(project: Path, *, target: str) -> None:
    root = project / ".learning-tutor"
    root.mkdir()
    files = {
        ".learning-tutor/manifest.json": b'{"schema_version":1}\n',
        ".learning-tutor/learning-tutor.prompt.md": (
            b"# Universal Learning Tutor\n"
        ),
        ".learning-tutor/loader.md": (
            b"Load .learning-tutor/learning-tutor.prompt.md\n"
        ),
        ".learning-tutor/.gitignore": b"workspace/*\n!workspace/.gitkeep\n",
        ".learning-tutor/workspace/.gitkeep": b"",
    }
    native = {
        "cursor": ".cursor/skills/learning-tutor/SKILL.md",
        "pi": ".pi/skills/learning-tutor/SKILL.md",
    }.get(target)
    if native is not None:
        files[native] = b"---\nname: learning-tutor\n---\n"
    for relative, content in files.items():
        path = project.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    owned = sorted((*files, ".learning-tutor/install.json"))
    receipt = {
        "schema_version": 1,
        "protocol_version": "1.0.0",
        "target": target,
        "owned_paths": owned,
        "hashes": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in sorted(files.items())
        },
    }
    (root / "install.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def snapshot_tree(project: Path) -> tuple[tuple[str, str, bytes], ...]:
    entries: list[tuple[str, str, bytes]] = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        if path.is_symlink():
            entries.append((relative, "symlink", path.readlink().as_posix().encode()))
        elif path.is_file():
            entries.append((relative, "file", path.read_bytes()))
        else:
            entries.append((relative, "directory", b""))
    return tuple(entries)
```

The fixture deliberately models only the closed legacy receipt contract used
to authorize migration; migration must not pass its minimal legacy manifest
to the canonical manifest validator.

Then add:

```python
def test_update_migrates_owned_legacy_installation(self) -> None:
    create_valid_legacy_install(self.project, target="generic")
    private = self.project / ".learning-tutor/workspace/notes.md"
    private.write_text("private\n", encoding="utf-8")

    install(
        "generic",
        self.project,
        update=True,
        source_root=self.source,
    )

    self.assertFalse((self.project / ".learning-tutor").exists())
    self.assertEqual(
        (self.project / ".socratic-learn/workspace/notes.md").read_text(
            encoding="utf-8"
        ),
        "private\n",
    )


def test_migration_refuses_modified_legacy_owned_file(self) -> None:
    create_valid_legacy_install(self.project, target="generic")
    path = self.project / ".learning-tutor/loader.md"
    path.write_text("user change\n", encoding="utf-8")

    with self.assertRaises(IntegrityError):
        install(
            "generic",
            self.project,
            update=True,
            source_root=self.source,
        )

    self.assertEqual(path.read_text(encoding="utf-8"), "user change\n")
    self.assertFalse((self.project / ".socratic-learn").exists())
```

Also add tests for both roots existing, unowned canonical native skill,
symlinked workspace, and migration publication failure preserving recovery.

- [ ] **Step 2: Write failing doctor tests**

```python
def test_doctor_reports_legacy_migration_without_mutation(self) -> None:
    create_valid_legacy_install(self.project, target="cursor")
    before = snapshot_tree(self.project)
    diagnostics = diagnose(self.project)
    self.assertIn("legacy-installation", {item.code for item in diagnostics})
    self.assertEqual(snapshot_tree(self.project), before)


def test_doctor_reports_both_roots_as_collision(self) -> None:
    create_valid_legacy_install(self.project, target="generic")
    apply_install(plan_install(self.source, self.project, "generic", False))
    diagnostics = diagnose(self.project)
    self.assertIn(
        "installation-root-collision",
        {item.code for item in diagnostics},
    )
```

- [ ] **Step 3: Run tests and verify failures**

```powershell
python -m unittest tests.test_install tests.test_doctor -v
```

Expected: migration planning and legacy diagnostics are missing.

- [ ] **Step 4: Add explicit migration planning**

Extend the plan:

```python
@dataclass(frozen=True)
class InstallPlan:
    source_root: Path
    project: Path
    target: str
    update: bool
    files: tuple[PlannedFile, ...]
    previous_receipt: InstallReceipt | None = None
    expected_existing: tuple[tuple[str, str], ...] = ()
    emitted_snippet: str | None = None
    migrate_legacy: bool = False
    legacy_receipt: InstallReceipt | None = None
```

When `--update` is requested:

1. Prefer a valid canonical receipt.
2. If canonical is absent and legacy is valid, construct a migration plan.
3. If both roots exist, refuse without mutation.
4. Require the requested target to match the receipt target.
5. Verify every hashed legacy owned path before staging.
6. Reject unowned canonical destinations and native adapter paths.

- [ ] **Step 5: Implement receipt-last migration**

Create `_apply_migration(plan, stage, staged_install, stage_directory)`.
It must:

1. Stage the complete canonical installation.
2. Bind and back up only receipt-owned legacy files.
3. Move a regular, non-symlink legacy workspace as one identity-checked unit.
4. Publish canonical non-receipt paths with no-replace operations.
5. Publish `.socratic-learn/install.json` last.
6. Remove legacy files only while their recorded identities still match.
7. Preserve both roots and private recovery artifacts on any detected ambiguity.

Do not infer migration from path strings inside `_apply_update`; dispatch on
`plan.migrate_legacy`.

- [ ] **Step 6: Implement read-only legacy doctor diagnostics**

If no canonical receipt exists, inspect the exact legacy receipt and return:

```python
Diagnostic(
    code="legacy-installation",
    path=".learning-tutor/install.json",
    message="a managed Learning Tutor installation can be migrated",
    remediation=(
        "run 'python -m socratic_learn install "
        f"{receipt.target} PROJECT --update'"
    ),
)
```

If both roots exist, report `installation-root-collision` and do not validate
either as healthy. Never run the canonical manifest validator against a legacy
installed manifest.

- [ ] **Step 7: Run migration, doctor, and smoke tests**

```powershell
python -m unittest tests.test_install tests.test_doctor tests.test_universal_smoke -v
```

Expected: owned migration succeeds, modified/unowned paths are preserved and rejected, doctor remains read-only, and canonical smoke tests pass.

- [ ] **Step 8: Commit**

```powershell
git add socratic_learn/install.py socratic_learn/doctor.py tests
git commit -m "feat: migrate managed Learning Tutor installs"
```

---

### Task 5: Repository Adapter and Skill Rename

**Files:**
- Move: `.cursor/skills/learning-tutor/` to `.cursor/skills/socratic-learn/`
- Move: `adapters/pi/skills/learning-tutor/` to `adapters/pi/skills/socratic-learn/`
- Modify: `adapters/cursor/README.md`
- Modify: `adapters/pi/README.md`
- Modify: `adapters/claude-code/README.md`
- Modify: `adapters/claude-code/CLAUDE.md`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Produces: skill frontmatter `name: socratic-learn`
- Produces: Cursor discovery path `.cursor/skills/socratic-learn/SKILL.md`
- Produces: Pi discovery path `.pi/skills/socratic-learn/SKILL.md`
- Preserves: Claude loader marker ownership behavior

- [ ] **Step 1: Write failing path and metadata tests**

```python
def test_socratic_learn_skills_match_parent_directory(self) -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        ".cursor/skills/socratic-learn/SKILL.md",
        "adapters/pi/skills/socratic-learn/SKILL.md",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?m)^name:\s*(\S+)\s*$", text)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), "socratic-learn")
        self.assertEqual(path.parent.name, "socratic-learn")
```

- [ ] **Step 2: Run the focused validator tests**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: new paths are missing.

- [ ] **Step 3: Move skills and update adapter links**

Use:

```powershell
git mv .cursor/skills/learning-tutor .cursor/skills/socratic-learn
git mv adapters/pi/skills/learning-tutor adapters/pi/skills/socratic-learn
```

Set `name: socratic-learn`, canonical package paths, and canonical Python
commands in all adapter documents. Keep the Claude root-loader comment markers
unchanged if they are part of ownership detection.

- [ ] **Step 4: Run adapter and install discovery tests**

```powershell
python -m unittest tests.test_install tests.test_doctor tests.test_validate_repository -v
```

Expected: all adapter paths agree between templates, installer, doctor, and repository validation.

- [ ] **Step 5: Commit**

```powershell
git add -A
git commit -m "docs: rename agent adapters to Socratic Learn"
```

---

### Task 6: Public README, Documentation, and MIT License

**Files:**
- Modify: `README.md`
- Modify: `docs/universal-installation.md`
- Modify: `docs/manifest-reference.md`
- Modify: `docs/adding-an-adapter.md`
- Modify: historical files under `docs/superpowers/specs/` and `docs/superpowers/plans/` with rename pointers only
- Create: `LICENSE`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Produces: README tagline `A portable Socratic learning protocol for mathematics and AI.`
- Produces: documented canonical commands and migration procedure
- Produces: MIT license
- Preserves: precise limitations and POSIX threat-model scope

- [ ] **Step 1: Write failing README and license contract tests**

Require these headings:

```python
README_HEADINGS = (
    "# Socratic Learn",
    "## What Socratic Learn provides",
    "## Quick start",
    "## How a learning session works",
    "## Install for your agent",
    "## Commands",
    "## Private learner state",
    "## Security and recovery",
    "## Migrating from Learning Tutor",
    "## Development",
    "## Limitations",
    "## License",
)
```

Add assertions that README links resolve, canonical commands appear, the old
module appears only in migration context, and `LICENSE` starts with
`MIT License`.

- [ ] **Step 2: Run failing documentation tests**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: title, headings, links, and license assertions fail.

- [ ] **Step 3: Rewrite README in the approved order**

Use the approved tagline, Python 3.11 and native-CI badges, a safe temporary
project quick start, the four agent choices, all five commands, private-state
rules, scoped security language, migration guidance, validation commands,
limitations, and MIT link.

The quick start must use:

```powershell
python -m socratic_learn build
python -m socratic_learn install generic C:/path/to/empty/project
python -m socratic_learn doctor C:/path/to/empty/project
```

- [ ] **Step 4: Update detailed documentation**

`docs/universal-installation.md` documents clean install, canonical update,
legacy migration, doctor, recovery, and no-force behavior.
`docs/manifest-reference.md` documents `product` and the canonical bundle.
`docs/adding-an-adapter.md` uses canonical paths and names.
Historical specs and plans receive one note linking to the approved rename
design; do not rewrite their historical decisions.

- [ ] **Step 5: Add the MIT license**

Create the standard MIT text with:

```text
Copyright (c) 2026 Marcos Guilherme
```

- [ ] **Step 6: Run documentation validation**

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: headings, links, license, naming, private-state rules, and scoped security wording pass.

- [ ] **Step 7: Commit**

```powershell
git add README.md LICENSE docs tests/test_validate_repository.py
git commit -m "docs: publish Socratic Learn onboarding"
```

---

### Task 7: Validator, CI Matrix, and End-to-End Verification

**Files:**
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`
- Modify: `tests/test_universal_smoke.py`
- Modify: `tests/test_cli.py`
- Modify: `.github/workflows/native-python.yml`
- Modify: any remaining canonical-name test fixtures

**Interfaces:**
- Validator requires canonical package, artifact, adapters, README, and license
- Validator permits only the two-file legacy shim
- CI invokes `python -m socratic_learn`
- CI exercises clean install, canonical update, doctor, and legacy migration

- [ ] **Step 1: Write failing validator and smoke requirements**

Add required paths:

```python
UNIVERSAL_REQUIRED_PATHS = (
    "socratic_learn/__init__.py",
    "socratic_learn/__main__.py",
    "socratic_learn/install.py",
    "socratic_learn/doctor.py",
    "learning_tutor/__init__.py",
    "learning_tutor/__main__.py",
    "dist/socratic-learn.prompt.md",
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "LICENSE",
)
```

Add a failure when any implementation file other than `__init__.py` or
`__main__.py` remains under `learning_tutor/`.

- [ ] **Step 2: Run validator tests and observe failures**

```powershell
python -m unittest tests.test_validate_repository tests.test_universal_smoke -v
```

Expected: old allowlists, commands, or fixture names fail.

- [ ] **Step 3: Update validator contracts**

Check the canonical bundle heading, manifest product, skill frontmatter,
README headings, MIT license, canonical package files, deterministic dist,
private workspace exclusion, and the updated threat-model phrase
`cooperating Socratic Learn processes`.

Permit `learning_tutor/__init__.py` and `learning_tutor/__main__.py` only.

- [ ] **Step 4: Update native CI**

Use canonical commands and add a legacy migration smoke:

```yaml
- name: Build deterministic distribution
  run: python -m socratic_learn build
- name: Run full unit suite
  run: python -m unittest discover -s tests -p "test_*.py" -v
- name: Validate repository
  run: python tests/validate_repository.py
```

The Python smoke script creates isolated temporary projects for generic
install/update/doctor and for a generated valid legacy fixture migrated with
`--update`. It must finish with `git diff --exit-code` and a clean porcelain
status.

- [ ] **Step 5: Run the complete local verification**

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
git status --short --branch
```

Expected: build succeeds, all non-platform-skipped tests pass, validator
passes, diff check is clean, and only intentional tracked changes are shown.

- [ ] **Step 6: Verify deterministic rebuild**

```powershell
git diff -- dist
python -m socratic_learn build
git diff -- dist
```

Expected: both diffs are identical.

- [ ] **Step 7: Run clean-clone smoke**

Clone the current branch to a temporary directory, then run:

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
git status --porcelain --untracked-files=all
```

Expected: every command succeeds and final status is empty.

- [ ] **Step 8: Commit**

```powershell
git add -A
git commit -m "test: validate Socratic Learn release"
```

---

### Task 8: Whole-Branch Review, Merge, and GitHub Publication

**Files:**
- No implementation files unless review finds a defect
- External: GitHub repository `marcos-guilherme/socratic-learn`

**Interfaces:**
- Produces: public URL `https://github.com/marcos-guilherme/socratic-learn`
- Produces: `origin` pointing to that repository
- Produces: public `master` with observed native CI checks

- [ ] **Step 1: Review the complete branch**

Review the merge-base-to-head diff against the approved design and this plan.
Check package compatibility, migration safety, deterministic artifacts,
README truthfulness, private-data exclusion, adapter discovery, and CI.
Fix all Critical and Important findings, then rerun the complete verification.

- [ ] **Step 2: Inspect public contents before publication**

Run:

```powershell
git status --short --branch
git ls-files workspace
git ls-files | Select-String -Pattern '(^|/)\.env|credential|secret|private'
git remote -v
```

Expected: clean branch; only `workspace/.gitkeep` is tracked under
`workspace`; no credential or private learner files; no existing remote.
If a remote exists, stop and use it rather than creating a second repository.

- [ ] **Step 3: Merge into master and verify again**

After user selects local merge:

```powershell
git checkout master
git merge --no-ff feat/socratic-learn
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
```

Expected: merge and all verification succeed.

- [ ] **Step 4: Create the public GitHub repository**

Run:

```powershell
gh repo create marcos-guilherme/socratic-learn `
  --public `
  --description "A portable Socratic learning protocol for mathematics and AI." `
  --source . `
  --remote origin `
  --push
```

Expected: repository creation succeeds, `origin` is added, and `master` is
pushed.

- [ ] **Step 5: Apply topics**

```powershell
gh repo edit marcos-guilherme/socratic-learn `
  --add-topic socratic-method `
  --add-topic ai-education `
  --add-topic mathematics `
  --add-topic llm `
  --add-topic cursor `
  --add-topic claude-code `
  --add-topic python
```

- [ ] **Step 6: Verify public metadata and CI**

```powershell
gh repo view marcos-guilherme/socratic-learn --json name,url,visibility,description
gh run list --repo marcos-guilherme/socratic-learn --limit 5
gh run watch --repo marcos-guilherme/socratic-learn --exit-status
```

Expected: name is `socratic-learn`, URL is the expected public URL,
visibility is `PUBLIC`, description matches the tagline, and the Windows,
Ubuntu, and macOS workflow completes successfully.

- [ ] **Step 7: Remove the merged feature branch**

Only after merge and post-merge tests pass:

```powershell
git branch -d feat/socratic-learn
git status --short --branch
```

Expected: branch is deleted and `master` is clean and synchronized with
`origin/master`.
