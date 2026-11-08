# Windows Validation Fix Design

## Goal

Make the current `master` release candidate pass its Windows validation paths
without weakening the launcher banner, semantic-report validation, or symlink
safety checks.

## Confirmed root causes

1. When redirected `sys.stdout` uses CP1252, the banner catches its encoding
   error and writes UTF-8 bytes directly to the underlying buffer. A parent
   process using the advertised CP1252 encoding then cannot decode that output.
2. The private report CLI test records `/tmp/fictitious-semantic-runtime`.
   `pathlib` does not consider that path absolute on Windows, so the runtime
   context is correctly rejected before report rendering.
3. Six validator tests create symlinks without handling Windows error 1314.
   Machines without Developer Mode or elevated symlink privilege error during
   test setup rather than skipping an unsupported capability.

## Design

### Banner encoding

Keep the existing full banner for streams that can encode it. When the stream's
declared encoding cannot represent the banner, write a fixed ASCII banner
through the text stream instead of bypassing the stream with differently
encoded bytes. The fallback remains readable and preserves the learning route.

Tests will cover both an in-memory CP1252 stream and an installed-console
subprocess captured with the platform-default text decoder.

### Report fixture

Build the fictitious runtime root from the test's temporary directory and
resolve it. This supplies a native absolute path outside the temporary
repository on every platform while preserving the production validation.

### Symlink capability

Add a test-only helper that attempts symlink creation and skips the calling test
only for the platform's explicit unsupported/permission-denied result. Other
errors continue to fail. Apply it to the six currently unguarded symlink tests;
do not change production symlink validation.

## Verification

Follow red-green TDD for each failure:

1. preserve the current Windows failures as RED evidence;
2. add focused regression assertions;
3. make the minimum implementation or fixture change;
4. run banner, universal-smoke, report, and repository-validator suites;
5. run the complete test suite, repository validator, deterministic build, and
   `git diff --check`.

Success means the complete suite passes, with symlink tests skipped only where
the OS denies the required capability, and GitHub's Windows job no longer has
the two confirmed blockers.
