# Universal Learning Positioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition Socratic Learn as an evidence-aware protocol for learning any subject or skill while retaining mathematics and AI as starter curricula and examples.

**Architecture:** Keep the runtime, manifest, installer, and protocol interfaces unchanged. Update the public copy and discovery metadata, add repository-level contract checks that reject narrow mathematics-and-AI-only positioning, then rebuild only the deterministic prompt artifact affected by canonical pedagogy wording.

**Tech Stack:** English Markdown, Python 3.11 standard library, `unittest`, repository validator, GitHub CLI, GitHub Actions.

## Global Constraints

- Canonical tagline: `A portable, evidence-aware Socratic protocol for learning anything.`
- The primary product promise is learning any subject or skill.
- Mathematics and AI remain the first bundled starter curricula and rigorous examples, not the product boundary.
- Do not add new curricula in this change.
- Do not change package names, commands, installation paths, receipts, migration behavior, manifest schema, supported adapters, or security guarantees.
- Historical specifications and implementation plans remain unchanged.
- Python runtime code remains standard-library-only and compatible with Python 3.11 or newer.
- All behavior and metadata changes use test-first red-green cycles.

---

### Task 1: Universal README Contract

**Files:**
- Modify: `tests/test_validate_repository.py:285-312`
- Modify: `tests/validate_repository.py:71-90,249-340`
- Modify: `README.md:1-13,69-75,211-222`

**Interfaces:**
- Consumes: `validate(root: Path) -> list[str]` from `tests/validate_repository.py`.
- Produces: a validator-enforced README contract containing the canonical tagline, `any subject or skill`, and `starter curricula`.

- [ ] **Step 1: Strengthen the README onboarding test**

Replace the old tagline assertion in
`test_readme_provides_complete_onboarding_contract` and add the universal
scope assertions:

```python
self.assertIn(
    "A portable, evidence-aware Socratic protocol for learning anything.",
    text,
)
self.assertIn("any subject or skill", text.lower())
self.assertIn("starter curricula", text.lower())
```

- [ ] **Step 2: Add a failing validator regression test**

Add this test to `RepositoryValidationTests`:

```python
def test_validator_rejects_narrow_readme_positioning(self) -> None:
    temp, root = self.make_root()
    self.addCleanup(temp.cleanup)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = text.replace(
        "A portable, evidence-aware Socratic protocol for learning anything.",
        "A portable Socratic learning protocol for mathematics and AI.",
    ).replace("any subject or skill", "mathematics and AI")
    readme.write_text(text, encoding="utf-8")

    self.assertIn(
        "Narrow product positioning in README.md",
        validate(root),
    )
```

- [ ] **Step 3: Run the focused tests and verify the expected failures**

Run:

```powershell
python -m unittest `
  tests.test_validate_repository.RepositoryValidationTests.test_readme_provides_complete_onboarding_contract `
  tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_narrow_readme_positioning -v
```

Expected: the onboarding test fails on the old tagline and the validator
regression fails because no positioning diagnostic exists.

- [ ] **Step 4: Add the README positioning validator**

Add this constant near `SKILL_PATHS` in `tests/validate_repository.py`:

```python
README_POSITIONING_REQUIREMENTS = (
    "A portable, evidence-aware Socratic protocol for learning anything.",
    "any subject or skill",
    "starter curricula",
)
```

Add this check inside `validate` after required-file validation:

```python
readme = root / "README.md"
if readme.is_file():
    readme_text = readme.read_text(encoding="utf-8")
    if not all(
        phrase.lower() in readme_text.lower()
        for phrase in README_POSITIONING_REQUIREMENTS
    ):
        errors.append("Narrow product positioning in README.md")
```

- [ ] **Step 5: Rewrite the README opening**

Use this tagline and lead:

```markdown
**A portable, evidence-aware Socratic protocol for learning anything.**

Socratic Learn gives compatible AI agents one structured method for helping
people learn any subject or skill—from conceptual domains to practical
abilities. It turns goals into observable outcomes, diagnoses only relevant
prerequisites, and adapts instruction from the learner's demonstrated
understanding.

Mathematics and AI are included as starter curricula and rigorous examples,
not as limits on what the protocol can teach. Socratic Learn is a protocol and
distribution toolkit—not an AI model or a separate chat application.
```

- [ ] **Step 6: Add varied learning examples and precise limitations**

Keep the self-attention example, but precede it with a non-technical example:

```text
I want to learn to write a persuasive policy brief well enough to produce and
revise one for a real audience. First diagnose only the prerequisites needed
for that outcome.
```

Rewrite the curriculum limitation to state:

```markdown
The bundled mathematics and AI maps are starter curricula, not the boundary
of the protocol and not exhaustive courses. For another subject or skill, the
agent constructs the smallest relevant dependency path from the learner's
goal and available evidence.

Universal protocol scope does not mean universal host knowledge. Reliability
still depends on the selected model, available sources and tools, and the
quality of evidence produced during the session. Socratic Learn does not
guarantee mastery.
```

- [ ] **Step 7: Run README and validator tests**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: both commands exit `0`.

- [ ] **Step 8: Commit the README contract**

```powershell
git add README.md tests/test_validate_repository.py tests/validate_repository.py
git commit -m "docs: position Socratic Learn for any subject"
```

---

### Task 2: Universal Agent Discovery Metadata

**Files:**
- Modify: `tests/test_validate_repository.py:60-72,203-214,333-342`
- Modify: `tests/validate_repository.py:71-75,316-328`
- Modify: `.cursor/skills/socratic-learn/SKILL.md:1-8`
- Modify: `adapters/pi/skills/socratic-learn/SKILL.md:1-16`
- Modify: `adapters/pi/skills/socratic-learn/SKILL.project.md.template:1-9`
- Modify: `socratic_learn/templates/cursor-skill.md:1-6`
- Modify: `socratic_learn/templates/pi-skill.md:1-6`
- Modify: `adapters/cursor/README.md:1-6`
- Modify: `adapters/claude-code/README.md:1-20`
- Modify: `adapters/pi/README.md:57-75`
- Test: `tests/test_install.py`

**Interfaces:**
- Consumes: Markdown/YAML skill frontmatter parsed by
  `parse_frontmatter(text: str) -> dict[str, str] | None`.
- Produces: every discoverable skill describes learning `any subject or skill`;
  mathematics and AI links remain optional starter references.

- [ ] **Step 1: Update the metadata contract test**

Rename
`test_adapter_skills_have_specific_learning_tutor_metadata` to
`test_adapter_skills_advertise_universal_learning` and use:

```python
for term in (
    "any subject or skill",
    "diagnostic",
    "evidence-aware",
    "learning sessions",
):
    self.assertIn(term, frontmatter)
self.assertNotIn("mathematics and ai learning sessions", frontmatter)
```

Extend `ADAPTER_SKILLS` to include the project template and both generated
skill templates:

```python
ADAPTER_SKILLS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.project.md.template",
    "socratic_learn/templates/cursor-skill.md",
    "socratic_learn/templates/pi-skill.md",
)
```

In `make_root`, write the fixture description to every path in
`ADAPTER_SKILLS`:

```python
skill = (
    "---\n"
    "name: socratic-learn\n"
    "description: Conducts diagnostic, evidence-aware learning sessions "
    "for any subject or skill.\n"
    "---\n\n# Socratic Learn\n"
)
for relative in ADAPTER_SKILLS:
    (root / relative).write_text(skill, encoding="utf-8")
```

- [ ] **Step 2: Add a failing validator test for narrow skill metadata**

```python
def test_validator_rejects_narrow_skill_positioning(self) -> None:
    temp, root = self.make_root()
    self.addCleanup(temp.cleanup)
    path = root / ".cursor/skills/socratic-learn/SKILL.md"
    text = path.read_text(encoding="utf-8").replace(
        "for any subject or skill",
        "for mathematics and AI",
    )
    path.write_text(text, encoding="utf-8")

    self.assertIn(
        "Narrow product positioning in "
        ".cursor/skills/socratic-learn/SKILL.md",
        validate(root),
    )
```

- [ ] **Step 3: Run the metadata tests and verify they fail**

Run:

```powershell
python -m unittest `
  tests.test_validate_repository.RepositoryValidationTests.test_adapter_skills_advertise_universal_learning `
  tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_narrow_skill_positioning -v
```

Expected: FAIL because current skills advertise mathematics and AI or omit the
required universal phrase.

- [ ] **Step 4: Extend repository validation to discovery metadata**

Keep `SKILL_PATHS` unchanged because it also validates that a repository skill
directory matches the frontmatter name. Add a separate positioning tuple:

```python
POSITIONING_SKILL_PATHS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.project.md.template",
    "socratic_learn/templates/cursor-skill.md",
    "socratic_learn/templates/pi-skill.md",
)
```

After the existing frontmatter shape loop, add:

```python
for relative in POSITIONING_SKILL_PATHS:
    path = root / relative
    if not path.is_file():
        continue
    frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
    if (
        frontmatter is None
        or "any subject or skill"
        not in frontmatter.get("description", "").lower()
    ):
        errors.append(f"Narrow product positioning in {relative}")
```

- [ ] **Step 5: Apply canonical universal descriptions**

Use this description in repository and Pi adapter skills:

```yaml
description: Conducts diagnostic, evidence-aware learning sessions for any subject or skill. Use when the user wants to study, understand, practice, or build a learning plan. Mathematics and AI are included starter curricula, not limits.
```

Use this shorter installed-template description in
`socratic_learn/templates/cursor-skill.md` and
`socratic_learn/templates/pi-skill.md`:

```yaml
description: Run diagnostic, evidence-aware learning sessions for any subject or skill.
```

- [ ] **Step 6: Clarify optional curricula and adapter scope**

In both repository skills, state that the universal protocol applies to any
subject or skill and that the mathematics and AI maps are consulted only when
relevant.

Add one sentence to each adapter README:

```markdown
The adapter exposes the same subject-neutral protocol; mathematics and AI are
included starter curricula rather than adapter limits.
```

Keep all installation commands, links, capability mappings, and security
language unchanged.

- [ ] **Step 7: Run metadata and installation tests**

Run:

```powershell
python -m unittest tests.test_validate_repository tests.test_install -v
python tests/validate_repository.py
```

Expected: all tests pass and repository validation exits `0`.

- [ ] **Step 8: Commit discovery metadata**

```powershell
git add .cursor/skills/socratic-learn adapters socratic_learn/templates `
  tests/test_validate_repository.py tests/validate_repository.py
git commit -m "docs: make agent discovery subject-neutral"
```

---

### Task 3: Subject-Neutral Canonical Pedagogy

**Files:**
- Modify: `tests/test_validate_repository.py:510-570`
- Modify: `core/pedagogy.md:22-72`
- Modify: `docs/manifest-reference.md:30-42`
- Modify: `dist/socratic-learn.prompt.md`
- Modify: `dist/manifest.json`

**Interfaces:**
- Consumes: canonical Markdown source list from `socratic_learn.build`.
- Produces: a deterministic bundle whose general Socratic probes apply across
  subjects and skills while mathematical evidence rules remain conditional.

- [ ] **Step 1: Add a failing pedagogy scope assertion**

Inside `test_pedagogy_defines_responsive_socratic_dialogue`, add:

```python
self.assertIn("across subjects and skills", section)
self.assertNotIn("for mathematics and ai, useful probes", section)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m unittest `
  tests.test_validate_repository.RepositoryValidationTests.test_pedagogy_defines_responsive_socratic_dialogue -v
```

Expected: FAIL because the current probe paragraph begins with
`For mathematics and AI`.

- [ ] **Step 3: Generalize the canonical probe paragraph**

Replace the domain-limited opening with:

```markdown
Across subjects and skills, useful probes include: Why does this work? Which
assumption is necessary? What evidence would refute the claim? What changes
when this condition varies? How does another approach compare? Apply any
domain-specific evidence rules, including the mathematical classification and
hypothesis rules, when they are relevant.
```

Keep the existing conditional mathematics rule in `## Motivated derivation`.

- [ ] **Step 4: Clarify the manifest reference**

Replace wording that implies mathematics and AI are the entire curriculum
scope with:

```markdown
The current source list includes the mathematics and AI starter curriculum
maps. They are bundled examples and dependency guides, not a restriction on
the subjects or skills the protocol can support.
```

- [ ] **Step 5: Rebuild the deterministic distribution**

Run twice:

```powershell
python -m socratic_learn build
python -m socratic_learn build
```

Expected: both runs print identical hashes for
`dist/socratic-learn.prompt.md` and `dist/manifest.json`.

- [ ] **Step 6: Run canonical-content and distribution checks**

Run:

```powershell
python -m unittest `
  tests.test_validate_repository `
  tests.test_build `
  tests.test_conformance `
  tests.test_manifest -v
python tests/validate_repository.py
git diff --check
```

Expected: all tests pass, repository validation passes, and `git diff --check`
prints no errors.

- [ ] **Step 7: Commit canonical pedagogy and artifacts**

```powershell
git add core/pedagogy.md docs/manifest-reference.md dist `
  tests/test_validate_repository.py
git commit -m "docs: generalize Socratic pedagogy across domains"
```

---

### Task 4: Public Metadata and Release Verification

**Files:**
- Verify: `README.md`
- Verify: `.github/workflows/native-python.yml`
- Verify: all files changed in Tasks 1-3
- External update: `marcos-guilherme/socratic-learn` GitHub metadata

**Interfaces:**
- Consumes: committed `master` branch and authenticated GitHub CLI.
- Produces: synchronized public description, discovery topics, and a passing
  Windows/Ubuntu/macOS safety matrix.

- [ ] **Step 1: Run the complete local release gate**

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
git status --short --branch
```

Expected: 251 or more tests pass with only documented platform skips,
repository validation passes, no diff errors exist, and the working tree is
clean.

- [ ] **Step 2: Review current-scope wording**

Run:

```powershell
rg "learning protocol for mathematics and AI|mathematics and AI learning sessions" `
  README.md .cursor adapters socratic_learn core docs `
  --glob "!docs/superpowers/**"
```

Expected: no matches. Historical specifications and plans are excluded.

- [ ] **Step 3: Push the committed release**

```powershell
git push origin master
```

Expected: GitHub reports `master -> master`.

- [ ] **Step 4: Update the GitHub description**

```powershell
gh repo edit marcos-guilherme/socratic-learn `
  --description "A portable, evidence-aware Socratic protocol for learning anything." `
  --add-topic learning `
  --add-topic education `
  --add-topic tutoring
```

Keep the existing mathematics, AI, Socratic method, agent, and Python topics;
they remain valid examples and discovery routes.

- [ ] **Step 5: Monitor the hosted matrix**

```powershell
$RunId = gh run list --repo marcos-guilherme/socratic-learn `
  --branch master --limit 1 --json databaseId --jq ".[0].databaseId"
gh run watch $RunId --repo marcos-guilherme/socratic-learn --exit-status
```

Expected: Windows, Ubuntu, and macOS jobs all complete with `success`.

- [ ] **Step 6: Verify final public metadata and local synchronization**

```powershell
gh repo view marcos-guilherme/socratic-learn `
  --json description,repositoryTopics,url,visibility,defaultBranchRef
git status --short --branch
```

Expected:

- description equals the canonical tagline without Markdown formatting;
- topics include `learning`, `education`, `tutoring`, `socratic-method`,
  `mathematics`, and `ai-education`;
- visibility is `PUBLIC`;
- default branch is `master`;
- local `master` tracks `origin/master` with a clean working tree.
