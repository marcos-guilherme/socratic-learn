# Learner-First README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the long technical-first README with the approved learner-first B2 design while preserving installation, safety, research, and product-claim contracts.

**Architecture:** The README becomes a short entry point that leads with the learner experience and links to detailed documents. Repository tests will protect the new section order, natural writing rules, safety caveats, and onboarding commands without coupling the terminal banner to README presentation.

**Tech Stack:** Markdown, Python 3.11 `unittest`, repository validation script.

## Global Constraints

- Keep the README between 250 and 300 lines.
- Use ordinary English, active voice, and connected paragraphs.
- Do not use em dash or en dash characters.
- Do not promote test counts, build mechanics, or protocol version numbers in the hero.
- Keep the exact versioned installer URLs and publication caveats.
- Keep source reading commands, privacy boundaries, and the POSIX same-user threat model summary.
- Keep universal subject positioning, the personal project narrative, and the compact protocol flow.
- Do not claim that Socratic Learn guarantees mastery or is validated as a complete product.

---

### Task 1: Define the learner-first README contract

**Files:**
- Modify: `tests/test_banner.py`
- Modify: `tests/test_validate_repository.py`
- Modify: `tests/validate_repository.py`

**Interfaces:**
- Consumes: the approved heading order and hero copy in the design specification.
- Produces: stable README contract constants and tests used by repository validation.

- [ ] **Step 1: Replace the banner presentation coupling**

Change `tests/test_banner.py` so the banner is tested as a CLI artifact:

```python
def test_banner_keeps_product_identity_and_learning_flow(self) -> None:
    self.assertIn("L E A R N", BANNER)
    self.assertIn(
        "objective → prerequisites → guided route → application → evidence",
        BANNER,
    )
```

Remove `test_banner_matches_first_readme_text_block`. Keep every stream,
encoding, flush, and fallback test unchanged.

- [ ] **Step 2: Express the new README order**

Set the README heading contract in `tests/test_validate_repository.py` to:

```python
README_HEADINGS = (
    "## See a session",
    "## Why it is different",
    "## Quick start",
    "## Choose an AI host",
    "## Learn from an article",
    "## How the method works",
    "## Research and limitations",
    "## Technical documentation",
    "## License",
)
README_TAGLINE = (
    "Turn any AI agent into a tutor that checks whether you actually learned."
)
README_OPENING_PROMISE = "learn any subject"
```

Update the complete onboarding test to require these hero signals:

```python
for signal in (
    "Any subject",
    "Your AI host",
    "Progress through application",
    'socratic "I want to learn',
):
    self.assertIn(signal.lower(), opening.lower())
self.assertNotIn("tests", opening.lower())
self.assertNotIn("███████╗", text)
```

Replace compact-example extraction with the `## See a session` section and
keep the route-setting, redirection, and learner-application assertions.

- [ ] **Step 3: Align repository validation**

Set `README_TAGLINE` in `tests/validate_repository.py` to the new promise.
Keep `README_OPENING_PROMISE`, dash rejection, unsupported effectiveness claim
patterns, installer URLs, onboarding order, source reading requirements, and
POSIX threat model terms unchanged.

- [ ] **Step 4: Run the contract tests and confirm RED**

Run:

```powershell
python -m unittest tests.test_banner.BannerTests.test_banner_keeps_product_identity_and_learning_flow tests.test_validate_repository.RepositoryValidationTests.test_readme_provides_complete_onboarding_contract -v
```

Expected: the banner test passes and the README contract test fails because
the old README has the old tagline, heading order, and ASCII presentation.

- [ ] **Step 5: Commit the test contract**

```powershell
git add tests/test_banner.py tests/test_validate_repository.py tests/validate_repository.py
git commit -m "test: define learner-first readme"
```

### Task 2: Rewrite the README around the learner journey

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the heading, copy, onboarding, safety, and evidence contracts from Task 1.
- Produces: the public learner-first README and all links used by repository validation.

- [ ] **Step 1: Replace the hero**

Use this opening:

```markdown
# Socratic Learn

**Turn any AI agent into a tutor that checks whether you actually learned.**

Socratic Learn helps you learn any subject through a guided conversation that
ends in application. Use it for physics, programming, writing, research, or a
skill you want to practice.

**Any subject** | **Your AI host** | **Progress through application**

```text
socratic "I want to learn how attention works"
```

[Install Socratic Learn](#quick-start)
```

Keep the Python version and license links as quiet metadata after the
installation link. Remove the ASCII block and safety-matrix promotion from the
hero.

- [ ] **Step 2: Write the learner-facing sections**

Use the approved order. The session example must show:

```text
Learner  > I want to understand why attention scales by sqrt(d_k).
Tutor    > What should you be able to derive or predict by the end?
Learner  > I want to derive the scaling and predict what changes without it.
Tutor    > Start with one term in the dot product. What variance would you
           expect if its two factors are independent and standardized?
...
Evidence > The learner derives the variance growth and applies it to a changed
           dimension without receiving the final answer first.
```

The next section explains adaptive representation, support based on observed
attempts, active retrieval on return, time-aware scope, and progress through
application. It states plainly that a preferred format is useful context and
does not prove mastery or define a fixed learning style.

- [ ] **Step 3: Keep quick start accurate**

Preserve the exact Windows and POSIX versioned installer URLs, review-before-run
steps, unsigned binary warning, conditional release wording, and conditional
pipx wording. Keep this command order:

```text
Windows installer URL
POSIX installer URL
pipx install socratic-learn
socratic
socratic "I want to learn linear algebra"
socratic --agent pi
socratic --here
```

- [ ] **Step 4: Condense hosts, article reading, method, and research**

Explain that Socratic Learn provides the learning protocol, while Pi,
Antigravity, and Claude provide the interactive host, model access,
authentication, terminal behavior, and quotas. State that Cursor is a project
integration.

Keep these reading examples:

```text
socratic read https://example.org/article
socratic read paper.pdf evaluate the main claim and its evidence
socratic read --agent pi tests/fixtures/sources/minimal-text.pdf explain its evidence
```

Keep the private source path, accepted HTML/XHTML/PDF formats, all ingestion
limits, no OCR, no JavaScript rendering, source-bounded default, explicit
external verification gate, prompt-injection caution, and troubleshooting
keywords required by validation.

Keep the compact flow:

```text
objective → prerequisites → guided route → application → evidence
```

Retain the six named research references and baseline caveat in a compressed
paragraph and short list. Link the full learner-preference catalog.

- [ ] **Step 5: Move deep details behind links**

The final technical section links to:

```markdown
- [Installation and lifecycle](docs/universal-installation.md)
- [Launcher host contract](docs/launcher-adapters.md)
- [Adding an adapter](docs/adding-an-adapter.md)
- [Manifest reference](docs/manifest-reference.md)
- [Learner preference research](docs/research/learner-preference-patterns.md)
- [Semantic evaluation baseline](evaluation/reports/2026-11-06-antigravity-baseline.md)
```

Keep the short private-workspace rule, source-development commands, project
adapter table, migration command, lifecycle commands, and POSIX threat-model
phrases required by the repository contract.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run:

```powershell
python -m unittest tests.test_banner tests.test_validate_repository.RepositoryValidationTests.test_readme_provides_complete_onboarding_contract tests.test_validate_repository.RepositoryValidationTests.test_readme_provides_public_launcher_onboarding tests.test_validate_repository.RepositoryValidationTests.test_readme_orders_onboarding_and_scopes_channel_availability -v
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit the README**

```powershell
git add README.md
git commit -m "docs: redesign readme for learners"
```

### Task 3: Validate claims, links, and natural writing

**Files:**
- Modify if needed: `README.md`
- Modify if a contract bug appears: `tests/test_validate_repository.py`
- Modify if a contract bug appears: `tests/validate_repository.py`

**Interfaces:**
- Consumes: the completed README and repository contracts.
- Produces: verified Markdown with no synthetic writing patterns or broken repository guarantees.

- [ ] **Step 1: Run automated prose and structure checks**

Run:

```powershell
rg -n "[—–]" README.md
rg -n "(not .{0,40}, but|is not just|powerful|seamless|revolutionary|cutting-edge)" README.md
python -c "from pathlib import Path; p=Path('README.md'); print(len(p.read_text(encoding='utf-8').splitlines()))"
```

Expected: both searches return no matches and the line count is between 250
and 300.

- [ ] **Step 2: Perform the human-style review**

Read from the first heading through License. Revise any paragraph that:

1. repeats the shape of the previous paragraph;
2. uses several short fragments instead of a connected explanation;
3. changes topic without explaining why;
4. stacks slogans or vague adjectives;
5. compresses a safety caveat until it becomes misleading;
6. presents preference, engagement, or confidence as learning evidence.

- [ ] **Step 3: Run full verification**

Run:

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
```

Expected: distribution rebuild succeeds, all tests pass, repository validation
passes, and the diff check has no output.

- [ ] **Step 4: Commit review fixes**

If the review changed files:

```powershell
git add README.md tests/test_validate_repository.py tests/validate_repository.py
git commit -m "docs: refine readme language"
```

If no files changed, record the verified state without creating an empty commit.
