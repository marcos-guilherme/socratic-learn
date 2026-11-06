# Universal Distribution — Task 3 Report

## Status

Implemented behavioral conformance validation for the 11 required tutor
contracts. Checks use normalized, source-scoped semantic marker alternatives
and explicit phase ordering rather than complete-prompt snapshots. Build now
fails before manifest creation with deterministic, actionable `IntegrityError`
diagnostics, and the closed manifest records conformance version 1 and the
required diagnostic codes.

## RED evidence

Initial focused command:

```text
python -m unittest tests.test_conformance -v
```

Result: exit code 1 with the expected `ModuleNotFoundError` for
`learning_tutor.conformance`.

After the first implementation pass, the focused conformance suite ran 15
tests with 2 expected failures. Those failures showed that two mutation tests
had not removed their wrapped semantic markers; correcting the fixtures made
the tests exercise the intended missing behaviors.

The first integrated focused run exposed the existing build test repositories
as nonconforming skeletal fixtures. They were updated with minimum valid
behavioral contracts while preserving each original build test's purpose.

## GREEN evidence

Focused command:

```text
python -m unittest tests.test_conformance tests.test_build -v
```

Result: exit code 0; 42 tests ran successfully with 2 Windows symlink skips.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 109 tests ran successfully with the same 2 Windows
symlink skips.

The skips occur because this Windows account lacks symlink-creation privilege
(error 1314); each test attempted creation before skipping.

## Determinism

Two consecutive distribution regenerations produced byte-identical artifacts:

```text
dist/learning-tutor.prompt.md 47f1deb384bcacbcea7ec31c500169111378a5ff04ec7e3efd65e28b33cb67e6
dist/manifest.json 0913134e7c8f58753e8cb0c1bac2f96fd2c3e7a28d353a1ecf9468238ec75571
```

The prompt hash is unchanged from Task 2; only the manifest changed to record
the conformance contract.

## Self-review

- Every required behavior has a focused mutation test and stable diagnostic
  code.
- Diagnostics are sorted by `(code, path)` and build failures preserve that
  order in both details and remediation.
- Plan approval checks require approval semantics and compare normalized
  approval/teaching section indexes.
- Manifest validation remains closed and rejects conformance version, code
  sequence, type, and unknown-property drift.
- `git diff --check` passed; changes are limited to Task 3 implementation,
  related fixtures/tests, generated manifest, and this report.

## Concerns

No blocking concerns. Conformance is intentionally marker-based rather than
natural-language inference, so future canonical wording changes must retain an
accepted semantic alternative or deliberately version the contract. The two
platform symlink tests remain skipped as described above.

## Review fixes — fallback completeness and approval ordering

### RED evidence

Expanded conformance command:

```text
python -m unittest tests.test_conformance -v
```

Result: exit code 1; 21 tests ran with 3 expected failures. Removing the
subagent/parallelism, diagram/rendering, or cross-session-memory family was not
detected. The already-covered structured-quiz, web, and filesystem removal
tests passed with the existing stable `capability-fallbacks` code.

The approval test was split into two contracts. One removes only the explicit
gate while preserving section order. The other keeps the approval sentence and
both headings, moves only the gate after the teaching block, and expects
`plan-approval-before-teaching`.

That repaired ordering test initially failed because the implementation
compared only approval-section and teaching-section indexes while checking gate
presence independently. It now requires:

```text
approval section < explicit approval gate < teaching section
```

The first integrated focused run remained RED because Task 2's minimum valid
build fixture lacked the three newly enforced fallback families.

### GREEN evidence

Focused command:

```text
python -m unittest tests.test_conformance tests.test_build -v
```

Result: exit code 0; 48 tests ran successfully with 2 Windows symlink skips.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 115 tests ran successfully with the same 2 Windows
symlink skips.

All six optional capability families are now independent marker groups under
the unchanged `capability-fallbacks` diagnostic code, so manifest contract
version 1 and its required-code sequence remain stable.

### Determinism and concerns

Two consecutive regenerations were byte-identical:

```text
dist/learning-tutor.prompt.md 47f1deb384bcacbcea7ec31c500169111378a5ff04ec7e3efd65e28b33cb67e6
dist/manifest.json 0913134e7c8f58753e8cb0c1bac2f96fd2c3e7a28d353a1ecf9468238ec75571
```

No new blocking concerns. The existing marker-versioning consideration and
two Windows privilege-based symlink skips remain.
