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

`tests/test_universal_smoke.py` copies only `git ls-files`, compares two
in-memory builds and checked-in artifacts, installs Generic, Cursor, Claude
Code, and Pi separately, requires healthy doctor results, verifies nested
private-file ignore behavior in temporary Git repositories, performs unchanged
updates, and confirms a tampered managed file causes refusal without any
additional mutation.

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
- Full suite: 193 tests passed, 5 skipped.
- Validator: `Repository validation passed.`
- Diff check exited 0.
- Post-commit clone: 193 tests passed, 5 skipped; validator passed; generated
  artifact diff was empty; clone status was clean.

The five skips are existing Windows symlink-privilege cases. Non-privileged
path-identity and recovery coverage passed.

## Commits

- `4c14680 docs: publish universal tutor workflow`
- `56d3062 fix: preserve generated LF checkouts`

## Concerns

No blocking concerns. Git EOL enforcement is intentionally scoped to `dist/*`;
the deterministic builder normalizes canonical source line endings in memory.
