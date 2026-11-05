# Portable AI Learning Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a vendor-neutral, Markdown-first repository that lets Cursor, Claude Code, Pi, and generic agents conduct evidence-aware mathematics and AI learning sessions.

**Architecture:** Canonical pedagogy lives in `core/`; `AGENTS.md` is the generic entry point, while platform adapters only map local capabilities to the canonical protocol. Versioned templates and example learner state define persistence, real learner data remains under ignored `workspace/`, and a standard-library Python validator enforces repository integrity.

**Tech Stack:** Markdown, Python 3 standard library, Git, Cursor project skills, Claude Code project instructions, Pi skills.

## Global Constraints

- The pedagogy must have one canonical source and must not be duplicated in adapters.
- The first release must work with Cursor, Claude Code, Pi, and generic `AGENTS.md` consumers.
- No application runtime, database, model API, cloud sync, or non-standard Python dependency.
- Mathematics content must state assumptions and classify claims.
- Volatile framework facts must use primary-source verification when web access exists.
- Every optional capability must have a conversational fallback.
- Real learner data must stay outside Git by default.
- Documentation paths must use `/`; Python filesystem code must use `pathlib`.

---

## File Map

- `README.md`: installation, quick start, portability, privacy, and validation.
- `AGENTS.md`: vendor-neutral agent entry point and loading order.
- `.gitignore`: excludes real learner state and Python artifacts.
- `core/pedagogy.md`: canonical learning principles.
- `core/session-protocol.md`: define → diagnose → plan → teach → close workflow.
- `core/assessment.md`: adaptive diagnostic and mastery rules.
- `core/evidence-policy.md`: mathematical and volatile-fact evidence rules.
- `curricula/mathematics/map.md`: initial mathematics dependency map.
- `curricula/ai/map.md`: initial AI dependency map.
- `templates/*.md`: schemas for private learner state.
- `workspace.example/`: fictitious filled example.
- `.cursor/skills/learning-tutor/SKILL.md`: Cursor-discoverable entry.
- `adapters/cursor/README.md`: Cursor capability mapping and installation.
- `adapters/claude-code/CLAUDE.md`: Claude Code entry.
- `adapters/claude-code/README.md`: installation and capability mapping.
- `adapters/pi/skills/learning-tutor/SKILL.md`: installable Pi skill.
- `adapters/pi/README.md`: Pi installation and optional extension mapping.
- `tests/validate_repository.py`: repository validator and command entry point.
- `tests/test_validate_repository.py`: standard-library unit tests.

## Shared Interfaces

The canonical session record uses these headings in this order:

```markdown
# Session: YYYY-MM-DD — Topic
## Outcome
## Diagnostic evidence
## Approved dependency path
## Concepts established
## Application evidence
## Remaining gaps
## Next step
## Sources
```

Curriculum nodes use:

```markdown
### node-id — Human-readable title
- Outcome:
- Prerequisites:
- Concepts:
- Evidence:
- Application:
```

Canonical text that adapters must not copy is wrapped by:

```html
<!-- canonical:start -->
...
<!-- canonical:end -->
```

Adapters link to canonical files and contain only platform-specific loading,
tool mapping, and fallback instructions.

---

### Task 1: Repository Privacy and Validation Harness

**Files:**
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/test_validate_repository.py`
- Create: `tests/validate_repository.py`

**Interfaces:**
- Produces: `validate(root: Path) -> list[str]`
- Produces: `main() -> int`
- Consumes: repository paths, Markdown links, YAML-like skill frontmatter, Git tracked-file output when available.

- [ ] **Step 1: Write failing validator tests**

Create `tests/__init__.py` as an empty file and create
`tests/test_validate_repository.py` with temporary-repository tests:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.validate_repository import validate


class RepositoryValidationTests(unittest.TestCase):
    def make_root(self) -> tuple[TemporaryDirectory, Path]:
        temp = TemporaryDirectory()
        root = Path(temp.name)
        (root / ".gitignore").write_text(
            "workspace/*\n!workspace/.gitkeep\n__pycache__/\n*.py[cod]\n",
            encoding="utf-8",
        )
        for relative in (
            "README.md",
            "AGENTS.md",
            "core/pedagogy.md",
            "core/session-protocol.md",
            "core/assessment.md",
            "core/evidence-policy.md",
            "curricula/mathematics/map.md",
            "curricula/ai/map.md",
            "templates/learner-profile.md",
            "templates/learning-goal.md",
            "templates/session-log.md",
            "templates/progress.md",
            ".cursor/skills/learning-tutor/SKILL.md",
            "adapters/cursor/README.md",
            "adapters/claude-code/CLAUDE.md",
            "adapters/pi/skills/learning-tutor/SKILL.md",
            "workspace/.gitkeep",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# file\n", encoding="utf-8")
        skill = (
            "---\n"
            "name: learning-tutor\n"
            "description: Conducts structured learning sessions.\n"
            "---\n\n# Learning Tutor\n"
        )
        (root / ".cursor/skills/learning-tutor/SKILL.md").write_text(
            skill, encoding="utf-8"
        )
        (root / "adapters/pi/skills/learning-tutor/SKILL.md").write_text(
            skill, encoding="utf-8"
        )
        return temp, root

    def test_minimal_valid_repository_passes(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.assertEqual([], validate(root))

    def test_missing_required_file_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "AGENTS.md").unlink()
        self.assertTrue(any("AGENTS.md" in error for error in validate(root)))

    def test_broken_relative_markdown_link_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("[Missing](missing.md)\n", encoding="utf-8")
        self.assertTrue(any("missing.md" in error for error in validate(root)))

    def test_invalid_skill_frontmatter_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        skill = root / ".cursor/skills/learning-tutor/SKILL.md"
        skill.write_text("---\nname: Learning Tutor\n---\n", encoding="utf-8")
        self.assertTrue(any("frontmatter" in error for error in validate(root)))

    def test_canonical_copy_in_adapter_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        canonical = "A canonical paragraph long enough to identify duplicated guidance."
        (root / "core/pedagogy.md").write_text(
            f"<!-- canonical:start -->\n{canonical}\n<!-- canonical:end -->\n",
            encoding="utf-8",
        )
        (root / "adapters/cursor/README.md").write_text(canonical, encoding="utf-8")
        self.assertTrue(any("duplicates canonical" in error for error in validate(root)))

    def test_private_marker_outside_workspace_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")
        self.assertTrue(any("private learner" in error for error in validate(root)))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: import failure because `tests.validate_repository` does not exist.

- [ ] **Step 3: Implement the validator**

Create `tests/validate_repository.py` with:

```python
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
    ".gitignore",
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
    "templates/learner-profile.md",
    "templates/learning-goal.md",
    "templates/session-log.md",
    "templates/progress.md",
    ".cursor/skills/learning-tutor/SKILL.md",
    "adapters/cursor/README.md",
    "adapters/claude-code/CLAUDE.md",
    "adapters/pi/skills/learning-tutor/SKILL.md",
    "workspace/.gitkeep",
)
SKILL_PATHS = (
    ".cursor/skills/learning-tutor/SKILL.md",
    "adapters/pi/skills/learning-tutor/SKILL.md",
)
ADAPTER_ROOTS = (".cursor", "adapters")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
CANONICAL_RE = re.compile(
    r"<!-- canonical:start -->(.*?)<!-- canonical:end -->",
    re.DOTALL,
)
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def markdown_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.md")
        if ".git" not in path.parts and "workspace" not in path.parts
    ]


def parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def normalize(text: str) -> str:
    return " ".join(text.split())


def tracked_files(root: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return set()
    return {line.replace("\\", "/") for line in result.stdout.splitlines()}


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"Missing required path: {relative}")

    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(
                    f"Broken Markdown link in {path.relative_to(root)}: {target}"
                )
        if "PRIVATE_LEARNER_DATA" in text:
            errors.append(
                f"Found private learner marker outside workspace: {path.relative_to(root)}"
            )

    for relative in SKILL_PATHS:
        path = root / relative
        if not path.exists():
            continue
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        if (
            frontmatter is None
            or not SKILL_NAME_RE.fullmatch(frontmatter.get("name", ""))
            or not frontmatter.get("description")
        ):
            errors.append(f"Invalid skill frontmatter: {relative}")

    canonical_blocks: list[str] = []
    core = root / "core"
    if core.exists():
        for path in core.glob("*.md"):
            canonical_blocks.extend(
                normalize(block)
                for block in CANONICAL_RE.findall(
                    path.read_text(encoding="utf-8")
                )
                if len(normalize(block)) >= 40
            )

    for adapter_root in ADAPTER_ROOTS:
        base = root / adapter_root
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            adapter_text = normalize(path.read_text(encoding="utf-8"))
            for block in canonical_blocks:
                if block in adapter_text:
                    errors.append(
                        f"{path.relative_to(root)} duplicates canonical core text"
                    )
                    break

    gitignore = root / ".gitignore"
    if gitignore.exists():
        rules = gitignore.read_text(encoding="utf-8").splitlines()
        if "workspace/*" not in rules or "!workspace/.gitkeep" not in rules:
            errors.append(".gitignore must ignore workspace except .gitkeep")

    tracked_private = sorted(
        path
        for path in tracked_files(root)
        if path.startswith("workspace/") and path != "workspace/.gitkeep"
    )
    if tracked_private:
        errors.append("Tracked private learner files: " + ", ".join(tracked_private))

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add privacy rules**

Create `.gitignore`:

```gitignore
workspace/*
!workspace/.gitkeep

__pycache__/
*.py[cod]
.pytest_cache/
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: six tests pass.

- [ ] **Step 6: Commit**

```powershell
git add .gitignore tests
git commit -m "test: add repository integrity validator"
```

---

### Task 2: Canonical Pedagogy and Generic Agent Entry

**Files:**
- Create: `core/pedagogy.md`
- Create: `core/session-protocol.md`
- Create: `core/assessment.md`
- Create: `core/evidence-policy.md`
- Create: `AGENTS.md`

**Interfaces:**
- Consumes: learner objective and optional files under `workspace/`.
- Produces: approved dependency path and session record matching the shared heading contract.

- [ ] **Step 1: Add a failing content-contract test**

Append to `RepositoryValidationTests`:

```python
    def test_agents_entry_references_every_core_document(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        required = (
            "core/pedagogy.md",
            "core/session-protocol.md",
            "core/assessment.md",
            "core/evidence-policy.md",
        )
        text = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(all(target in text for target in required))
```

This test intentionally fails against the fixture's initial `# file` content.
After confirming the failure, update `make_root()` so its `AGENTS.md` fixture
links all four files. The real repository content remains covered by running
`tests/validate_repository.py`.

- [ ] **Step 2: Run the targeted test and verify failure**

```powershell
python -m unittest tests.test_validate_repository.RepositoryValidationTests.test_agents_entry_references_every_core_document -v
```

Expected: FAIL because none of the canonical paths are present.

- [ ] **Step 3: Write the four canonical documents**

Use these mandatory sections and canonical markers:

```markdown
# Pedagogy
## Purpose
<!-- canonical:start -->
Understanding means being able to reconstruct and apply an idea from connected
foundations. The tutor builds explicit dependency edges instead of presenting
isolated facts.
<!-- canonical:end -->
## Connected foundations
## Motivated derivation
## Active application
## Learner control
## Anti-patterns
```

```markdown
# Session Protocol
## Inputs
## 1. Define an observable outcome
## 2. Diagnose relevant prerequisites
## 3. Present and approve a dependency path
## 4. Teach one node at a time
## 5. Close and persist
## Capability fallbacks
## Session record contract
```

```markdown
# Assessment
## Purpose
## Diagnostic budget
## Bracketing a knowledge edge
## Question construction
## Feedback after an error
## Escalation after success
## Mastery evidence
```

```markdown
# Evidence Policy
## Mathematical claims
## Volatile technical claims
## Source priority
## Citation placement
## Uncertainty language
## No-web fallback
```

Fill every section with direct operational instructions from the approved
design. Set the default diagnostic budget to six questions, allow the learner
to change it, and never claim mastery from self-report alone.

- [ ] **Step 4: Write `AGENTS.md`**

The entry point must instruct agents to:

1. Read all four canonical documents.
2. Read `workspace/learner-profile.md` and `workspace/progress.md` when present.
3. Ask for an observable outcome before diagnosing.
4. Select only relevant curriculum nodes.
5. Stop for plan approval before teaching.
6. Persist the shared session record when filesystem access exists.
7. Apply documented fallbacks instead of abandoning the session.

Link every referenced file with relative Markdown links.

- [ ] **Step 5: Repair the fixture and run checks**

Update the fixture `AGENTS.md` with links to all core documents, then run:

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: unit tests pass; repository validation still reports only files
scheduled for later tasks as missing.

- [ ] **Step 6: Commit**

```powershell
git add AGENTS.md core tests/test_validate_repository.py
git commit -m "feat: define canonical learning protocol"
```

---

### Task 3: Private Learner-State Templates

**Files:**
- Create: `templates/learner-profile.md`
- Create: `templates/learning-goal.md`
- Create: `templates/session-log.md`
- Create: `templates/progress.md`
- Create: `workspace.example/learner-profile.md`
- Create: `workspace.example/learning-goal.md`
- Create: `workspace.example/progress.md`
- Create: `workspace.example/sessions/2026-01-15-example.md`
- Create: `workspace/.gitkeep`

**Interfaces:**
- Produces: stable headings consumed by generic and platform-specific agents.
- Privacy contract: only `workspace/.gitkeep` may be tracked under `workspace/`.

- [ ] **Step 1: Add failing template-heading tests**

Add a test that checks the session template has every shared session heading
and the progress template contains `Demonstrated`, `Developing`, and `Next
evidence needed`. Use `subTest` so a missing heading reports precisely.

- [ ] **Step 2: Run the new test and verify failure**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: FAIL because template files do not exist.

- [ ] **Step 3: Write templates**

Use exact top-level structures:

```markdown
# Learner Profile
## Current context
## Existing experience
## Preferred interaction
## Accessibility and constraints
## Topics to avoid or defer
```

```markdown
# Learning Goal
## Interest
## Observable outcome
## Motivation
## Available time
## Desired depth
## Completion evidence
```

```markdown
# Session: YYYY-MM-DD — Topic
## Outcome
## Diagnostic evidence
## Approved dependency path
## Concepts established
## Application evidence
## Remaining gaps
## Next step
## Sources
```

```markdown
# Progress
## Demonstrated
## Developing
## Next evidence needed
## Completed applications
## Open misconceptions
```

Each heading gets one HTML comment describing what belongs there. Do not place
real learner information in templates.

- [ ] **Step 4: Write fictitious example state**

Use one fictional learner studying vector dot products as preparation for
attention mechanisms. The example session must show a wrong initial geometric
interpretation, corrected reasoning, one application, and one remaining gap.
Do not include `PRIVATE_LEARNER_DATA` because that marker is reserved for
validator tests.

- [ ] **Step 5: Run tests and validator**

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
git check-ignore workspace/example-secret.md
```

Expected: tests pass; validator still reports later adapter/curriculum files;
`git check-ignore` prints `workspace/example-secret.md`.

- [ ] **Step 6: Commit**

```powershell
git add templates workspace.example workspace/.gitkeep tests/test_validate_repository.py
git commit -m "feat: add private learning-state templates"
```

---

### Task 4: Starter Mathematics and AI Curricula

**Files:**
- Create: `curricula/mathematics/map.md`
- Create: `curricula/ai/map.md`

**Interfaces:**
- Produces: curriculum nodes using the shared node schema.
- Node identifiers: lowercase kebab-case, unique within each map.

- [ ] **Step 1: Add failing curriculum-schema tests**

Add helper tests that parse every `### node-id — Title` block and require all
five fields: Outcome, Prerequisites, Concepts, Evidence, Application. Also fail
if a prerequisite names an unknown node in the same file, except `none`.

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: FAIL because curriculum maps do not exist.

- [ ] **Step 3: Write the mathematics map**

Add these connected nodes:

- `algebraic-reasoning`
- `functions-and-graphs`
- `limits-and-change`
- `derivatives`
- `vectors-and-dot-products`
- `matrices-and-linear-maps`
- `probability-models`
- `random-variables`
- `optimization`
- `math-for-machine-learning`

For every node, provide an observable outcome, valid prerequisites, 2–4 core
concepts, a concrete demonstration, and a small application. State domains and
assumptions where formulas appear.

- [ ] **Step 4: Write the AI map**

Add these connected nodes:

- `supervised-learning`
- `loss-and-generalization`
- `gradient-based-learning`
- `neural-networks`
- `tensor-frameworks`
- `attention`
- `transformers`
- `language-models`
- `evaluation`
- `framework-experimentation`

Connect mathematical prerequisites by explicit cross-links to the mathematics
map, but keep AI-node prerequisites locally valid. Mark framework APIs,
versions, and hardware support as volatile and subject to the evidence policy.

- [ ] **Step 5: Run tests and validator**

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: curriculum tests pass; validator reports only adapters/README still
missing.

- [ ] **Step 6: Commit**

```powershell
git add curricula tests/test_validate_repository.py
git commit -m "feat: add starter mathematics and AI maps"
```

---

### Task 5: Cursor, Claude Code, and Pi Adapters

**Files:**
- Create: `.cursor/skills/learning-tutor/SKILL.md`
- Create: `adapters/cursor/README.md`
- Create: `adapters/claude-code/CLAUDE.md`
- Create: `adapters/claude-code/README.md`
- Create: `adapters/pi/skills/learning-tutor/SKILL.md`
- Create: `adapters/pi/README.md`

**Interfaces:**
- Consumes: canonical core files, curriculum maps, and optional workspace state.
- Produces: platform-specific tool mapping without copied canonical blocks.

- [ ] **Step 1: Add failing adapter-contract tests**

Require both skill files to have:

```yaml
name: learning-tutor
```

Require descriptions to mention mathematics, AI, diagnosis, and learning
sessions. Require every adapter entry to reference `core/session-protocol.md`
and `core/evidence-policy.md` through valid relative links.

- [ ] **Step 2: Run tests and verify failure**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Create the Cursor skill and adapter**

Use this frontmatter:

```yaml
---
name: learning-tutor
description: Conducts diagnostic, evidence-aware mathematics and AI learning sessions. Use when the user wants to study, understand, practice, or build a learning plan for mathematics, machine learning, AI frameworks, neural networks, transformers, or related prerequisites.
---
```

The body must direct Cursor to load `AGENTS.md` and the four canonical files,
map structured questions to the available question UI, use web research for
volatile facts, use Mermaid only when relationships become clearer, and write
state only under `workspace/`. `adapters/cursor/README.md` explains that the
project skill is already installed when the repository is opened.

- [ ] **Step 4: Create the Claude Code adapter**

`CLAUDE.md` must be a short loader: read the canonical files, follow the shared
protocol, ask one conversational question at a time when no structured quiz is
available, use web tools when configured, and keep real state under
`workspace/`. `README.md` explains copying or including the loader in another
project.

- [ ] **Step 5: Create the Pi skill and adapter**

Use the same skill metadata and a Pi-compatible Markdown body. Map optional Pi
extensions:

- `quiz` → graded checks;
- `ask-user-question` → preference and goal decisions;
- researcher subagent → volatile-fact verification;
- Mermaid/SVG makers → structure or geometry only;
- `md-log` → session persistence.

Document conversational fallbacks for every missing extension. Do not copy
content from the canonical markers.

- [ ] **Step 6: Run tests and validator**

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: all unit tests pass; validator reports only `README.md` missing.

- [ ] **Step 7: Commit**

```powershell
git add .cursor adapters tests/test_validate_repository.py
git commit -m "feat: add Cursor Claude and Pi adapters"
```

---

### Task 6: User Documentation and End-to-End Verification

**Files:**
- Create: `README.md`
- Modify: any file identified by validation failures.

**Interfaces:**
- Produces: a complete onboarding path for generic and supported agents.

- [ ] **Step 1: Write a failing README contract test**

Require `README.md` to contain these headings:

```markdown
## What this is
## Quick start
## How a learning session works
## Supported agents
## Private learner state
## Validation
## Limitations
```

Also require commands for copying `workspace.example` to `workspace` on both
PowerShell and POSIX shells.

- [ ] **Step 2: Run the new test and verify failure**

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: FAIL because `README.md` does not exist.

- [ ] **Step 3: Write `README.md`**

Explain:

1. This repository is a portable tutor protocol, not an AI application.
2. Open the repository with a supported agent and ask to start a learning
   session with an observable goal.
3. Generic agents begin at `AGENTS.md`.
4. Cursor discovers the project skill automatically.
5. Claude Code uses the provided `CLAUDE.md` loader.
6. Pi users copy or link the Pi skill and may add optional extensions.
7. Real state lives in ignored `workspace/`; examples are fictitious.
8. Validation runs with:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
```

Include a short example request:

```text
Quero entender self-attention o suficiente para implementá-la com operações
tensoriais. Faça primeiro um diagnóstico curto dos pré-requisitos.
```

- [ ] **Step 4: Run full verification**

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git status --short
git ls-files workspace
```

Expected:

- every unit test passes;
- validator prints `Repository validation passed.`;
- only intended README/test changes are uncommitted before the final commit;
- `git ls-files workspace` prints only `workspace/.gitkeep`.

- [ ] **Step 5: Commit the verified documentation**

```powershell
git add README.md tests/test_validate_repository.py
git commit -m "docs: add portable tutor onboarding"
```

- [ ] **Step 6: Perform a clean-copy smoke test**

```powershell
$temp = Join-Path $env:TEMP "learning-things-smoke"
if (Test-Path $temp) { Remove-Item -Recurse -Force $temp }
git clone . $temp
python (Join-Path $temp "tests/validate_repository.py")
Remove-Item -Recurse -Force $temp
```

Expected: the clone succeeds and validation prints
`Repository validation passed.`.

- [ ] **Step 7: Confirm clean final state**

```powershell
git status --short --branch
git log --oneline -7
```

Expected: clean working tree and a linear sequence of focused implementation
commits after the design and plan commits. If the clean-copy smoke test required
a correction, rerun the full verification, commit the correction separately,
then repeat the smoke test before this final check.

