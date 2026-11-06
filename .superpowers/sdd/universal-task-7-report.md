# Universal Distribution — Task 7 Report

## Status

Implemented repository validation, complete English onboarding documentation,
and an end-to-end tracked-copy smoke test. The validator builds in memory and
compares exact bytes with checked-in `dist/` without writing artifacts.

## TDD evidence

Repository contract tests first failed because universal package files,
templates, generated artifacts, and documentation were not required; stale
artifacts, invalid generated headers, and absolute manifest paths were not
detected. The standalone validator regression then reproduced its import
failure before the repository-root path fix.

The initial committed-clone smoke exposed a Windows checkout issue: Git
converted generated artifacts to CRLF, and the LF-only build left `dist/`
dirty. A failing regression required `dist/* text eol=lf`; `.gitattributes`
and validator enforcement made the repeated clone smoke clean.

## Documentation

- `README.md` defines the supported meaning and limits of universal, requires
  Python 3.11, gives five primary commands, documents all four targets,
  ownership safety, private state, recovery behavior, and detailed links.
- `docs/universal-installation.md` covers Generic, Cursor, Claude Code, and Pi
  installation, collisions, schema-1 ownership, update refusal, doctor
  interpretation, and private workspace ignore behavior.
- `docs/manifest-reference.md` documents every schema field, version policy,
  source normalization, bundle hashing, conformance, session headings, and
  schema-1 receipt semantics.
- `docs/adding-an-adapter.md` defines template boundaries, ownership paths,
  loader links, required collision/recovery tests, and the prohibition on
  canonical prose duplication.
- Documentation does not claim all models are certified. It states that
  failed publication preserves partial paths, staging directories, and
  backups for manual recovery.

## End-to-end smoke

`tests/test_universal_smoke.py` copies only `git ls-files` and executes the
copied repository's CLI with `sys.executable`, `cwd` set to the copy, and
`PYTHONPATH` removed. It compares two CLI builds, installs Generic, Cursor,
Claude Code, and Pi separately, requires healthy CLI doctor results, verifies
nested private-file ignore behavior in temporary Git repositories, performs
unchanged CLI updates, and confirms a tampered managed file causes refusal
without any additional mutation. A separate regression removes the copied
`learning_tutor/install.py` and proves installation fails instead of falling
back to the valid live checkout.

After commits `4c14680` and `56d3062`, a unique clean clone ran build, the full
suite, and the validator. Rebuilding left `dist/` byte-identical and
`git status --porcelain` empty.

## Verification

```text
python -m learning_tutor build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
```

Results:

- Build exited 0 with the checked-in bundle and manifest hashes.
- Full suite: 196 tests passed, 5 skipped.
- Validator: `Repository validation passed.`
- Diff check exited 0.
- Post-commit clone: 196 tests passed, 5 skipped; validator passed; generated
  artifact diff was empty; clone status was clean.

The five skips are existing Windows symlink-privilege cases. Non-privileged
path-identity and recovery coverage passed.

## Commits

- `4c14680 docs: publish universal tutor workflow`
- `56d3062 fix: preserve generated LF checkouts`
- `8e46305 docs: record universal task 7 verification`
- `838d946 fix: isolate universal validation smoke`

## Concerns

No blocking concerns. Git EOL enforcement is intentionally scoped to `dist/*`;
the deterministic builder normalizes canonical source line endings in memory.

## Review fixes

The Task 7 review identified four issues; all were corrected:

- The tracked-copy smoke no longer imports live `learning_tutor` modules or
  uses live functions/templates after copying. Copied CLI subprocesses cover
  build, all four installs, doctor, unchanged update, and tamper refusal
  without recursively invoking the smoke suite.
- Required repository artifacts are checked with `Path.is_file()`. A directory
  masquerading as `dist/manifest.json` now receives a clear non-file
  diagnostic, distinct from a missing path.
- Every Python subprocess launched by tests uses `sys.executable`; a full
  `tests/**/*.py` search found no hardcoded `"python"` executable argument.
- Installation documentation now distinguishes receipt-owned and hashed
  managed files from operation-created parent, staging, backup, and recovery
  directories. It documents normal temporary cleanup and conservative
  preservation after uncertain or post-publication failure.

Focused smoke tests passed twice consecutively with identical successful
results. The corrected full suite passed 196 tests with 5 existing Windows
symlink-privilege skips. Repository validation and `git diff --check` passed.
After commit `838d946`, a unique clean clone rebuilt byte-identical `dist/`,
passed all 196 tests and the validator, and remained clean.
