# Remove README Session Example Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the complete session example so the README introduction leads directly into `Why it is different`.

**Architecture:** Keep this as a documentation-only behavior change guarded by the existing README contract test. Remove only the approved section and preserve every other README section.

**Tech Stack:** Markdown, Python 3.11+, pytest

## Global Constraints

- Do not add replacement copy for the removed example.
- Keep `## Why it is different` after the opening installation link and badges.
- Do not modify or commit unrelated IOI study files.

---

### Task 1: Remove the session example

**Files:**
- Modify: `tests/test_readme_hero.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the root README as UTF-8 text.
- Produces: a README introduction without the session example or its dialogue markers.

- [ ] **Step 1: Write the failing test**

Add this contract to `tests/test_readme_hero.py`:

```python
def test_readme_opens_without_session_example():
    readme = README.read_text(encoding="utf-8")

    assert "## See a session" not in readme
    assert "Learner  >" not in readme
    assert "Tutor    >" not in readme
    assert "Evidence >" not in readme
    assert readme.index("[Install Socratic Learn](#quick-start)") < readme.index(
        "## Why it is different"
    )
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
python -m pytest tests/test_readme_hero.py::test_readme_opens_without_session_example -v
```

Expected: FAIL because `## See a session` is still present.

- [ ] **Step 3: Remove the approved README section**

Delete everything from `## See a session` through the paragraph ending with
`try a different case.` Do not add replacement copy.

- [ ] **Step 4: Run focused and repository verification**

Run:

```powershell
python -m pytest tests/test_readme_hero.py -v
python tests/validate_repository.py
git diff --check
```

Expected: all tests and validation pass, and `git diff --check` produces no
output.

- [ ] **Step 5: Commit**

```powershell
git add -- README.md tests/test_readme_hero.py
git commit -m "docs: remove README session example"
```
