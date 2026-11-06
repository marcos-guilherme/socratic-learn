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

## Final P1 fix — parent-chain-bound publication

### RED evidence

The parent-race command initially failed all 3 tests because neither
publication-boundary hook nor parent-chain verification existed:

```text
python -m unittest tests.test_install.InstallTests.test_parent_replacement_before_link_preserves_external_tree tests.test_install.InstallTests.test_parent_replacement_after_link_preserves_external_tree tests.test_install.InstallTests.test_parent_symlink_swap_preserves_external_directory -v
```

Result: exit code 1 with 3 expected missing-hook errors.

### Parent-chain safety

- Every publication captures the complete existing directory chain from the
  project root through the destination parent.
- Each chain entry must be a real directory, not a symlink or Windows reparse
  point, and records its stable device/inode identity.
- The complete chain is verified immediately before and immediately after
  every hard-link publication.
- Where Python exposes directory-descriptor operations, the destination parent
  is opened with no-follow semantics, its identity is verified, and link,
  stat, and cleanup operations are bound to that descriptor.
- Windows and other fallback platforms use the same complete before/after
  identity checks. A post-link parent mismatch permits path-based cleanup only
  when the full chain still matches and the destination is the exact staged
  inode.
- Linked-file rollback also validates its recorded complete parent chain
  before unlinking. Directory-descriptor cleanup verifies the exact linked
  inode in the bound original parent.
- When the original parent was replaced or renamed, external paths are
  preserved. Recovery errors report the destination, original parent
  device/inode, and inspection action; an operation-created link is removed
  only when its original parent and inode can be proven.

### Race coverage

Narrow pre-link and post-link hooks on real temporary filesystems verify parent
replacement immediately before and after publication. A symlink-to-external
directory case verifies no pre-existing external bytes are removed when
symlink privilege is available.

### Final verification

Focused command:

```text
python -m unittest tests.test_install -v
```

Result: exit code 0; 43 tests ran successfully with 1 Windows symlink skip.

Complete-suite command:

```text
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: exit code 0; 158 tests ran successfully with 3 Windows
symlink-privilege skips. `python -m compileall -q learning_tutor tests` and
`git diff --check` completed with exit code 0.

Two consecutive CLI builds retained the deterministic hashes recorded above.
No blocking concerns remain; the additional skip is the privileged
parent-symlink race case.

## Approved conservative recovery policy

This section supersedes earlier automatic rollback and published-path cleanup
language in this report.

### RED evidence

Four new policy tests initially produced 3 failures:

```text
python -m unittest tests.test_install.InstallTests.test_hard_link_identity_race_preserves_external_replacement tests.test_install.InstallTests.test_failure_after_publication_preserves_partial_paths_and_stage tests.test_install.InstallTests.test_update_failure_preserves_partial_paths_backups_and_stage tests.test_install.InstallTests.test_successful_installs_leave_no_private_transaction_artifacts -v
```

The old recovery path deleted partial publication or restored old state instead
of preserving recovery artifacts.

### Implementation and coverage

- Pre-publication failures still clean private staging.
- Native and Claude destinations are attempted before package publication, so
  collision races that publish nothing retain normal cleanup.
- After any file or directory publication, failures never unlink, remove, or
  rename published destinations. Errors list partial paths and retained staging
  or backups and state that no external data was deleted.
- Update restoration uses atomic no-overwrite hard links only. Competing
  destinations and private backups are preserved and reported.
- The receipt is published last. Interrupted installs remain intentionally
  unhealthy for later `doctor` diagnosis.
- Race tests replace published files and directories before the former cleanup
  boundary and prove that external bytes survive. Additional tests cover
  partial initial/update publication, retained backups, pre-publication
  cleanup, and artifact-free success.

The design transaction section and Task 4/5 plan text now specify this approved
policy instead of automatic deletion.

### Final verification

- Focused: 46 tests passed with 1 Windows parent-symlink privilege skip.
- Full: 161 tests passed with 3 Windows symlink-privilege skips.
- `python -m compileall -q learning_tutor tests` and `git diff --check` passed.
- Two consecutive builds retained the deterministic hashes recorded above.

No blocking concerns remain. Recovery after a post-publication failure is
deliberately manual because cross-platform atomic conditional deletion is not
available.

## Final P1 fix — conservative backup bookkeeping

### RED evidence

The two new narrow fault-injection tests initially failed because the backup
tree was removed after `os.replace` succeeded but identity capture or backup
reading failed:

```text
python -m unittest tests.test_install.InstallTests.test_update_identity_failure_after_backup_move_preserves_only_copy tests.test_install.InstallTests.test_update_read_failure_after_backup_move_preserves_only_copy -v
```

Result: exit code 1 with 2 expected failures; neither test found the backup
tree containing the moved file.

### Fix and coverage

- The backup tree is marked as potentially containing unrecorded user data
  immediately before each `os.replace`.
- The mark is cleared only after destination identity capture, backup read,
  and receipt-hash verification all succeed.
- Any move, identity, read, or hash failure while marked preserves the complete
  backup and staging trees and reports the original and backup paths. No
  automatic restore or cleanup runs while certainty is lost.
- Ambiguous move failure may retain an empty backup by design. Successful
  updates still remove all private transaction artifacts.
- Existing hash-mismatch and restore-collision tests now enforce the same
  conservative boundary without weakening no-overwrite restore coverage.

### Final verification

- Focused: 48 tests passed with 1 Windows parent-symlink privilege skip.
- Full: 163 tests passed with 3 Windows symlink-privilege skips.
- Compilation and repository validation passed.
- Two consecutive builds retained the deterministic hashes recorded above.

No blocking concerns remain. A bookkeeping failure after a backup move now
requires manual recovery from the reported private backup, intentionally
favoring preservation over automatic cleanup.
