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
