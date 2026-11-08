# Windows Validation Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current release candidate pass its complete Windows validation without weakening runtime or repository safety.

**Architecture:** Keep the full Unicode banner when the output stream can encode it and select a fixed ASCII representation before writing when it cannot. Keep production semantic-path and symlink validation unchanged; make their tests supply native paths and skip only explicit OS capability denial.

**Tech Stack:** Python 3.11, `unittest`, `pathlib`, `subprocess`.

## Global Constraints

- Follow red-green TDD and preserve the observed failing commands as RED evidence.
- Do not weaken production semantic-report or symlink validation.
- Keep the full Unicode banner on compatible streams and terminals.
- Skip symlink tests only for explicit unsupported or permission-denied OS errors.
- Finish with the complete 697-test suite, repository validator, deterministic build, and `git diff --check`.

---

### Task 1: Encoding-Safe Banner

**Files:**
- Modify: `socratic_learn/banner.py`
- Modify: `tests/test_banner.py`
- Verify: `tests/test_universal_smoke.py`

**Interfaces:**
- Preserves: `BANNER: str`
- Produces: `ASCII_BANNER: str`
- Preserves: `write_banner(output: TextIO, environ: Mapping[str, str]) -> None`

- [ ] **Step 1: Change the CP1252 test to require a readable ASCII fallback**

Replace the existing complete-UTF-8-on-CP1252 assertion with:

```python
from socratic_learn.banner import ASCII_BANNER, BANNER, write_banner

def test_cp1252_stream_writes_readable_ascii_fallback(self) -> None:
    binary_output = io.BytesIO()
    output = io.TextIOWrapper(binary_output, encoding="cp1252")

    write_banner(output, {})

    self.assertEqual(
        f"{ASCII_BANNER}\n".encode("cp1252"),
        binary_output.getvalue(),
    )
```

Keep the flush test, but assert against the same CP1252 bytes.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_banner tests.test_universal_smoke.UniversalSmokeTests.test_installed_wheel_launches_fake_pi_end_to_end -v
```

Expected: the CP1252 test fails because the current fallback writes UTF-8 bytes; the installed-wheel test errors while decoding those bytes as CP1252.

- [ ] **Step 3: Implement pre-write encoding selection**

Add a fixed fallback containing only ASCII:

```python
ASCII_BANNER = """SOCRATIC LEARN

  objective -> prerequisites -> guided route -> application -> evidence"""
```

Before `output.write`, select text using the stream's advertised encoding:

```python
encoding = getattr(output, "encoding", None)
if encoding is not None:
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        text = f"{ASCII_BANNER}\n"

output.write(text)
output.flush()
```

Remove the binary UTF-8 fallback. Do not catch write failures unrelated to
encoding.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command.

Expected: banner and installed-wheel tests pass without reader-thread decoding errors.

- [ ] **Step 5: Commit**

```powershell
git add socratic_learn/banner.py tests/test_banner.py
git commit -m "fix: keep redirected banner encoding consistent"
```

---

### Task 2: Platform-Native Semantic Report Fixture

**Files:**
- Modify: `tests/test_evaluation_report.py`

**Interfaces:**
- Production runtime-context parsing remains unchanged.
- Test fixture `runtime_root` becomes a native absolute path outside its temporary repository.

- [ ] **Step 1: Preserve and document the focused RED**

Run:

```powershell
python -m unittest tests.test_evaluation_report.EvaluationReportTests.test_private_cli_scores_renders_and_validates_report -v
```

Expected on Windows: FAIL with report command exit code `2`; diagnostic instrumentation identifies `runtime context has an invalid runtime root`.

- [ ] **Step 2: Use the temporary directory's native resolved path**

Inside the test, after `repository = Path(directory)`, add:

```python
runtime_root = (repository.parent / "fictitious-semantic-runtime").resolve()
```

Then write:

```python
"runtime_root": str(runtime_root),
```

instead of the POSIX-only `/tmp/fictitious-semantic-runtime`.

- [ ] **Step 3: Run report tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_evaluation_report -v
```

Expected: all report tests pass.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_evaluation_report.py
git commit -m "test: use native semantic runtime path"
```

---

### Task 3: Capability-Aware Symlink Tests

**Files:**
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Produces test helper:
  `RepositoryValidationTests.require_symlink(link: Path, target: Path, *, target_is_directory: bool) -> None`
- Production `tests/validate_repository.py` remains unchanged.

- [ ] **Step 1: Preserve the six setup errors as RED evidence**

Run:

```powershell
python -m unittest tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_symlinked_semantic_runs_root tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_symlinked_semantic_run_directory tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_guarded_tracked_asset_symlinks_without_reading tests.test_validate_repository.RepositoryValidationTests.test_validator_rejects_guarded_asset_symlinked_ancestors_without_reading -v
```

Expected on Windows without symlink privilege: six `WinError 1314` setup errors.

- [ ] **Step 2: Add a narrow test-only helper**

Import `errno` and add to `RepositoryValidationTests`:

```python
def require_symlink(
    self,
    link: Path,
    target: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except OSError as error:
        if (
            getattr(error, "winerror", None) == 1314
            or error.errno in {errno.EACCES, errno.EPERM, errno.ENOSYS}
        ):
            self.skipTest(f"symbolic links are unavailable: {error}")
        raise
```

Replace only the six unguarded calls with `self.require_symlink(...)`.

- [ ] **Step 3: Run focused tests and verify GREEN or explicit SKIP**

Run the Step 1 command.

Expected: the tests pass where symlinks are available or skip where the OS explicitly denies the capability; no setup errors.

- [ ] **Step 4: Run the entire repository-validator test module**

Run:

```powershell
python -m unittest tests.test_validate_repository -v
```

Expected: all runnable tests pass, with capability skips allowed.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_validate_repository.py
git commit -m "test: skip unavailable Windows symlinks"
```

---

### Task 4: Full Verification

**Files:**
- Verify only; no planned code changes.

**Interfaces:**
- Confirms the release candidate remains deterministic and repository-safe.

- [ ] **Step 1: Rebuild deterministic artifacts**

Run:

```powershell
python -m socratic_learn build
```

Expected: command exits `0` and leaves tracked distribution files unchanged.

- [ ] **Step 2: Run the complete suite**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all 697 tests pass or explicitly skip only unavailable platform capabilities; no failures or errors.

- [ ] **Step 3: Run repository validation and diff gates**

Run:

```powershell
python tests/validate_repository.py
git diff --check
git status --short
```

Expected: repository validation passes, diff check is clean, and status shows no uncommitted files.

- [ ] **Step 4: Compare with hosted CI failure signatures**

Confirm the output contains neither:

```text
UnicodeDecodeError: 'charmap' codec
runtime context has an invalid runtime root
```

and that the formerly unguarded symlink tests no longer error during setup.

- [ ] **Step 5: Record final branch state**

```powershell
git log --oneline --decorate -5
```

Expected: the three focused fix commits follow the approved design and plan commits.
