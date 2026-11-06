# Universal Distribution — Task 4 Report

## Status

Implemented the generic project-local installer, immutable plans and receipt
model, generic loader, transactional application, safe updates, and CLI
reporting. Planning performs no writes. The receipt owns all six managed paths,
lists `install.json` as owned, and hashes every other managed file without
self-hashing.

## RED evidence

Initial focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 1 with the expected `ModuleNotFoundError` for
`learning_tutor.install`.

## GREEN evidence

Focused command:

```text
python -m unittest tests.test_install tests.test_cli -v
```

Result: exit code 0; 29 tests ran successfully.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 130 tests ran successfully with 2 Windows symlink skips.
The skips occur because this Windows account lacks symlink-creation privilege
(error 1314); both tests attempted symlink creation before skipping.

## Failure and safety coverage

- Planning rejects missing or non-directory projects, initial collisions, and
  unsupported targets without mutation.
- Updates validate the receipt and all old hashes before staging, backup, or
  commit mutation.
- Receipt paths reject absolute, non-POSIX, control-bearing, and `..` paths;
  resolved paths and symbolic-link components cannot escape the project.
- Modified, missing, and unowned target paths abort before mutation.
- Injected staging, initial commit, backup, update commit, and rollback
  failures verify cleanup, complete restoration, or preservation of the
  recovery backup with actionable remediation.
- Initial commit atomically claims a previously absent installation directory;
  rollback removes only that operation-created tree.
- Update backups are same-filesystem temporary directories adjacent to the
  installation and private workspace content is preserved.

## Determinism

Two consecutive CLI builds produced matching output and artifacts:

```text
dist/learning-tutor.prompt.md 47f1deb384bcacbcea7ec31c500169111378a5ff04ec7e3efd65e28b33cb67e6
dist/manifest.json 0913134e7c8f58753e8cb0c1bac2f96fd2c3e7a28d353a1ecf9468238ec75571
```

## Self-review

- `PlannedFile`, `InstallPlan`, and `InstallReceipt` are frozen dataclasses.
- The generic plan uses validated checked-in distribution bytes and a thin,
  normalized loader template.
- Update apply revalidates the planning snapshot before creating temporary
  state, closing the ordinary plan/apply modification window.
- No `--force` path exists, and existing CLI parsing already connected the
  generic implementation without requiring parser changes.
- `git diff --check` passed; no plan or specification file was edited.

## Concerns

No blocking concerns. Two pre-existing symlink tests remain skipped because of
Windows privilege error 1314. If rollback itself fails, the installer
intentionally retains its adjacent backup and reports that recovery path
instead of deleting the last intact copy.

## Review fixes — transaction cleanup and rollback

### RED evidence

The expanded installer suite initially ran 19 tests with 1 failure and 3
errors:

- staged hash mismatch left its actual staging tree behind;
- commit-time `IntegrityError` escaped without rollback after an earlier move;
- no explicit cleanup seam existed for locked-path and dual-failure tests.

A separate update-parent test then failed because rollback left a newly
created `workspace/` directory after a failed commit.

### GREEN evidence

Focused command:

```text
python -m unittest tests.test_install tests.test_cli -v
```

Result: exit code 0; 34 tests ran successfully.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 135 tests ran successfully with the same 2 Windows
symlink-privilege skips.

### Safety changes

- Commit and rollback boundaries now handle operational
  `LearningTutorError` subclasses, including path-race `IntegrityError`, as
  well as `OSError`.
- Every operation-created staging, backup, install-root, and update-parent
  path is explicitly tracked. Cleanup no longer uses `ignore_errors=True`.
- Cleanup failures report the original failure, locked recovery path, and a
  specific manual recovery action.
- A failed rollback preserves its same-filesystem backup and reports the
  absolute backup path.
- Staging cleans up after write, read, and hash-validation failures. Dual
  staging and cleanup failures preserve and identify the recoverable stage.
- Update rollback removes only parent directories created by that operation;
  pre-existing paths are never added to the cleanup set.

### Determinism and concerns

Two consecutive CLI builds remained byte-identical:

```text
dist/learning-tutor.prompt.md 47f1deb384bcacbcea7ec31c500169111378a5ff04ec7e3efd65e28b33cb67e6
dist/manifest.json 0913134e7c8f58753e8cb0c1bac2f96fd2c3e7a28d353a1ecf9468238ec75571
```

No blocking concerns. The same 2 symlink tests remain skipped because this
Windows account lacks symlink-creation privilege (error 1314).
