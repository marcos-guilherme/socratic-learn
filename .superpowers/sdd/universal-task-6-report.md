# Universal Distribution — Task 6 Report

## Status

Implemented read-only doctor diagnostics and CLI reporting for complete,
partial, invalid, and no-receipt installations. Diagnostics are stable,
actionable, and sorted by code and path; the doctor never repairs or removes
installation or recovery state.

## RED evidence

Initial focused command:

```text
python -m unittest tests.test_doctor -v
```

Result: exit code 1 with the expected import failure because
`learning_tutor.doctor` did not exist.

## Implementation and coverage

- Reuses the installer receipt parser, project-path guard, directory resolver,
  and template renderer plus the shared manifest validator and SHA-256 helper.
- Diagnoses missing and invalid receipts, changed and missing owned files,
  invalid manifests, bundle/manifest hash mismatch, protocol mismatch, broken
  loader references, wrong native discovery paths, and missing nested private
  ignore rules.
- Preserves partial published paths and private recovery artifacts when a
  receipt is absent; diagnosis performs no cleanup.
- Covers Generic, Cursor, Claude Code, and Pi discovery paths.
- Distinguishes an installer-owned Claude `CLAUDE.md` from a pre-existing
  user-owned Claude file that received only the emitted manual snippet.
- Detects tracked private workspace files with
  `git -C PROJECT ls-files -- .learning-tutor/workspace`.
- Reports Git execution failure explicitly when a repository marker is
  detected.
- The CLI prints `Installation healthy.` and exits 0 for a healthy install.
  Actionable diagnostic blocks exit 4.

## Verification

Focused:

```text
python -m unittest tests.test_doctor -v
```

Result: exit code 0; 14 tests passed.

Complete suite:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 177 tests passed with 3 Windows symlink-privilege skips.
The skipped tests require symlink creation and received Windows error 1314.

Additional checks:

```text
python -m compileall -q learning_tutor tests
git diff --check
```

Both completed with exit code 0.

## Determinism

The deterministic ordering and formatting test was run twice consecutively:

```text
python -m unittest tests.test_doctor.DoctorTests.test_diagnostics_and_formatting_are_deterministic -v
```

Both runs completed with exit code 0 and identical sorted diagnostic output.

## Concerns

No blocking concerns. The 3 full-suite skips are limited to Windows
symlink-creation privilege and are unrelated to doctor behavior.

## Review fixes — integration, path safety, and output

### RED evidence

The expanded focused suite initially failed with 2 assertion failures and 10
errors. It reproduced all four review findings: receipts lacked a Claude
manual-integration state, missing manual snippets were incorrectly healthy,
managed paths were read before reparse checks, wrong candidate reads leaked
`PermissionError`, Generic and owned Claude moves were not discovered, and
doctor stdout write/flush failures were not wrapped.

### Fixes and coverage

- Receipts now record `loader_mode` as either `owned` or `manual-snippet` and
  validate that mode against target and ownership.
- Manual Claude mode compares the exact emitted snippet after line-ending
  normalization. Absence produces deterministic
  `manual-integration-required` output without claiming or modifying the user
  file.
- Every receipt, owned file, manifest, bundle, loader candidate, and nested
  ignore read goes through lexical validation, component-by-component
  no-follow stat checks, reparse/symlink rejection, resolution, and project
  containment validation.
- A real external-symlink test runs when Windows privilege permits. A mocked
  reparse test always verifies rejection before the first content read.
- Generic, Cursor, owned Claude, and Pi loaders are checked at their exact
  discovery locations. Known wrong locations and unreadable candidates return
  actionable diagnostics instead of raw exceptions.
- Doctor writes and flushes stdout inside an `OSError` boundary that raises a
  `FilesystemError` for `<stdout>` and exit 5. Non-I/O programmer errors remain
  unmasked.

### Final verification

- Focused doctor suite: 22 tests passed with 1 Windows symlink-privilege skip.
- Installer regression suite: 48 tests passed with 1 Windows
  symlink-privilege skip.
- Full suite: 185 tests passed with 4 Windows symlink-privilege skips.
- `python -m compileall -q learning_tutor tests` and `git diff --check` passed.
- The deterministic diagnostic test passed in two consecutive runs.

No blocking concerns. One additional skip is the new real external-symlink
doctor test; its lexical mocked-reparse fallback passed on this machine.
