# Universal Distribution — Task 5 Report

## Status

Implemented Cursor, Claude Code, and Pi target planning and templates. Cursor
and Pi install namespaced native skills; Claude owns a new root `CLAUDE.md`
only when absent and otherwise preserves the existing file byte-for-byte while
emitting the exact manual snippet.

## RED evidence

Initial focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 1; 27 tests ran with 12 expected errors because
`cursor`, `claude-code`, and `pi` were still rejected by `plan_install()`.

## GREEN evidence

Focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 0; 30 tests ran successfully.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 145 tests ran successfully with 2 Windows symlink skips.
Both skips are caused by missing symlink-creation privilege (Windows error
1314), after the tests attempted to create their links.

## Target and safety coverage

- Cursor owns `.cursor/skills/learning-tutor/SKILL.md`.
- Pi owns `.pi/skills/learning-tutor/SKILL.md`.
- Claude owns `CLAUDE.md` only when the root file was absent.
- An existing Claude root file remains byte-identical, is excluded from the
  receipt, and produces the manual snippet from the same template renderer as
  an installed Claude loader.
- Empty native destination directories, destination files, and blocking
  ancestor files abort during planning without creating `.learning-tutor/`.
- Target mismatches on update are rejected before mutation.
- Native files participate in receipt hashing, staging, backup, rollback, and
  operation-created parent cleanup.
- Clean installs, updates, private-state preservation, relative link
  resolution, ownership, and native commit rollback are covered.
- Target loaders contain only discovery, private-state, and capability
  mapping instructions; canonical pedagogy remains solely in the universal
  prompt.

## Determinism

Two consecutive CLI builds produced identical reports and artifact hashes:

```text
dist/learning-tutor.prompt.md 47f1deb384bcacbcea7ec31c500169111378a5ff04ec7e3efd65e28b33cb67e6
dist/manifest.json 0913134e7c8f58753e8cb0c1bac2f96fd2c3e7a28d353a1ecf9468238ec75571
```

## Concerns

No blocking concerns. The 2 full-suite skips are limited to symlink checks
that this Windows account cannot execute without symlink privilege.

## Review fixes — commit races and capability mappings

### RED evidence

The focused review command initially ran 4 test methods and reported 7
subtest failures plus 1 error:

```text
python -m unittest tests.test_install.InstallTests.test_commit_time_destination_races_preserve_external_bytes tests.test_install.InstallTests.test_generic_package_race_during_staging_preserves_external_tree tests.test_install.InstallTests.test_update_revalidates_owned_hash_immediately_before_backup tests.test_install.InstallTests.test_target_templates_map_capabilities_without_copying_pedagogy -v
```

Cursor, Pi, and absent-root Claude races overwrote the injected external
files; the generic package race surfaced as a filesystem error instead of a
collision; update backup accepted a post-staging modification; and all three
templates lacked the required target capability semantics.

### Transaction fixes

- Clean installs atomically reserve `.learning-tutor/` with exclusive
  directory creation and every absent external file with Python's
  cross-platform exclusive `xb` create before replacing reservations with
  staged bytes.
- Only successfully created reservations and parent directories enter
  rollback tracking. A failed reservation preserves the race winner and
  removes package state, staging state, and removable operation-created
  parents.
- Updates reserve newly introduced unowned destinations before backup.
- Every update-owned file is hash-checked again immediately before its
  individual backup move. A mismatch aborts and restores any earlier backup
  moves through the existing rollback path.
- Race-injection tests cover Cursor and Pi files and empty native
  directories, absent-root Claude, and the generic package root during the
  staging/commit window.

### Thin capability mappings

- Cursor maps structured question UI with conversation fallback, web
  primary-source verification, Mermaid/text visuals, and filesystem state.
- Pi maps optional quiz versus preference questions, research/web, visual
  makers, and md-log/filesystem with conversational fallbacks.
- Claude maps configured web and filesystem tools with conversation
  fallbacks.
- Semantic tests enforce discovery paths, Cursor/Pi frontmatter, required
  mapping terms, and absence of copied canonical pedagogy.

### Final verification

Focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 0; 35 tests ran successfully.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 150 tests ran successfully with the same 2 Windows
symlink-privilege skips. `python -m compileall -q learning_tutor tests` also
completed with exit code 0.

Two consecutive CLI builds retained the deterministic hashes recorded above.
No blocking concerns were introduced.

## Re-review fixes — inode-safe publication and restore

### RED evidence

The new TOCTOU regression command initially failed all 4 tests with 3
assertion failures and 1 missing-implementation error:

```text
python -m unittest tests.test_install.InstallTests.test_hard_link_identity_race_preserves_external_replacement tests.test_install.InstallTests.test_initial_rollback_unlinks_only_matching_installer_identity tests.test_install.InstallTests.test_update_hashes_bytes_after_atomic_backup_move tests.test_install.InstallTests.test_update_restore_preserves_external_destination_and_backup -v
```

The placeholder implementation never used `os.link`, rollback could unlink a
replacement by path alone, update accepted bytes mutated during the
precheck-to-backup window, and restore could overwrite a new destination.

### Transaction redesign

- Removed absent-file placeholders completely.
- Every absent file is published directly from adjacent staging with
  `os.link`, which atomically fails rather than replacing a path that appeared.
- Each linked destination records its stable device/inode identity and is
  verified with `os.path.samefile` plus a fresh stat identity.
- Initial and update rollback unlink only paths that still match the recorded
  installer-created identity. Replaced files are preserved and reported as
  recovery conflicts.
- Every installer-created directory records the same stable identity.
  Rollback removes it only while that identity still matches and the directory
  remains empty; replacements or external contents are preserved and reported.
- Updates atomically move each current owned file into the private adjacent
  backup before hashing. The hash is computed from backup bytes, so mutation
  immediately before the move is detected.
- Backup restore uses the same no-overwrite hard-link primitive. If an
  external destination appears, both it and the private backup are preserved,
  and the error identifies both paths and the required inspection action.
- Existing commit, backup, cleanup, and rollback fault-injection tests were
  migrated from replace-based assumptions to the hard-link transaction model.

### Race coverage

Real temporary filesystems and narrow operation hooks now verify:

- replacement after hard-link creation but before identity verification;
- replacement of an installed file immediately before rollback;
- replacement of an installer-created native directory before cleanup;
- mutation during the precheck-to-backup move window;
- external destination creation during backup restore;
- preservation and reporting of external bytes and private backups.

### Final verification

Focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 0; 40 tests ran successfully.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 155 tests ran successfully with the same 2 Windows
symlink-privilege skips. `python -m compileall -q learning_tutor tests`
completed with exit code 0.

Two consecutive CLI builds again produced the deterministic hashes recorded
above. No blocking concerns remain.
