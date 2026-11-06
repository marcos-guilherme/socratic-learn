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
