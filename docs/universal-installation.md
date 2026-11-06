# Universal Installation

## Requirements and scope

Use Python 3.11 or newer from the repository root. The distribution supports
exactly four project-local targets: `generic`, `cursor`, `claude-code`, and
`pi`. “Universal” means that one deterministic tutor protocol can be
distributed through these adapters. It does not certify every model, agent
version, or host capability.

Transactional build and update moves require an atomic native no-replace
rename: `renameat2(RENAME_NOREPLACE)` on Linux, `renameatx_np(RENAME_EXCL)` on
macOS 10.12 or newer, or the existing handle-bound operation on Windows. The
Linux C library must expose `renameat2`, and the active filesystem must support
the flag. If the API, kernel, or filesystem support is unavailable, the command
does not fall back to an overwrite-prone rename. It fails with recovery
guidance, preserves managed content, and cleans pre-publication update staging
when its identity remains provable.

These controls protect against ordinary collisions, accidental concurrent
changes, and cooperating Learning Tutor processes. Atomic no-replace moves,
parent-directory file descriptors, identity rechecks, exact-topology cleanup,
recovery artifacts, and Windows handle-bound operations remain mandatory. On
POSIX, malicious or noncooperating processes running as the same OS principal
are out of scope: `rename`, `unlink`, and `rmdir` cannot condition a leaf-entry
mutation on an already-open inode, so an irreducible leaf-entry TOCTOU window
remains. A detected ambiguity is preserved and reported; this limitation does
not disable normal Linux or macOS build, install, update, or cleanup.

Build the checked-in distribution before installing:

```powershell
python -m learning_tutor build
```

`export prompt --output PATH` is also no-force: every parent is created through
identity-bound operations, an existing output is rejected, and publication is
an atomic native no-replace move. If another process wins the final output
race, its file is preserved. The error reports the private temporary artifact
for recovery; it is never blindly unlinked after an identity ambiguity.

## Generic

```powershell
python -m learning_tutor install generic C:/path/to/project
```

The installer creates `.learning-tutor/loader.md`. Point an agent that accepts
project instructions to that loader. It links to the installed canonical
prompt rather than copying the pedagogy.

## Cursor

```powershell
python -m learning_tutor install cursor C:/path/to/project
```

Cursor receives `.cursor/skills/learning-tutor/SKILL.md`. The skill is a thin
loader for `.learning-tutor/learning-tutor.prompt.md`.

## Claude Code

```powershell
python -m learning_tutor install claude-code C:/path/to/project
```

If root `CLAUDE.md` does not exist, the installer creates and owns a thin
loader. If it already exists as a regular file, the installer preserves it and
prints the exact snippet to append manually. It never merges or overwrites a
user-owned `CLAUDE.md`.

## Pi

```powershell
python -m learning_tutor install pi C:/path/to/project
```

Pi receives `.pi/skills/learning-tutor/SKILL.md`, which links to the same
project-local prompt and private workspace as the other targets.

## Collisions and ownership

Every install records schema-1 ownership in
`.learning-tutor/install.json`. A clean install refuses an existing
`.learning-tutor/` path or native adapter destination. There is no `--force`
option. The receipt lists managed files and hashes every managed file except
the receipt itself. The installer also creates parent directories needed to
publish those files, but parent directories, staging directories, backup
directories, and recovery directories are not managed-file receipt entries
and are not receipt-hashed. The installer does not automatically merge,
replace, or delete pre-existing agent files.

After a successful install or update, private staging and backup directories
are removed; required installation and adapter parent directories remain as
containers for managed files. Before publication, failed operations clean up
operation-created temporary paths only when the exact recorded topology, entry
types, and per-entry identities still match. An inserted, replaced, missing,
or unknown child preserves the complete remaining recovery tree and produces
an actionable error.

Build applies the same rule to the previous `dist/` backup. It removes that
backup only when the old distribution has exactly the deterministic manifest
and bundle topology, their hashes validate, and every entry remains
identity-bound through the swap. Unknown or changed content is preserved in
the reported backup path.

Publication is deliberately conservative. If a failure occurs after a path
may have been published, or if identity-safe restoration or cleanup cannot be
proved, the operation preserves partial published paths, staging directories,
backups, and any other reported recovery paths for manual recovery. Those
preserved paths are recovery evidence, not newly adopted managed-file receipt
entries. The error lists their locations. Do not rerun installation or delete
them blindly: inspect the listed paths, establish identity and ownership,
recover manually, and then run doctor.

## Updating

Update only an intact installation with the same target:

```powershell
python -m learning_tutor install cursor C:/path/to/project --update
```

Before changing anything, update validates the receipt and every managed
file. An unchanged update is safe. If a managed file was edited, is missing,
or no longer matches its recorded identity, update refuses before replacing
other files. Preserve user changes and restore or reinstall only after review.

## Private learner state

Private records belong under `.learning-tutor/workspace/`. The nested
`.learning-tutor/.gitignore` ignores workspace content while retaining
`workspace/.gitkeep`. Confirm repository behavior with:

```powershell
git check-ignore C:/path/to/project/.learning-tutor/workspace/private.md
```

## Doctor

```powershell
python -m learning_tutor doctor C:/path/to/project
```

`Installation healthy.` with exit code 0 means the receipt, managed hashes,
manifest, bundle, loader discovery path, and private ignore rules passed the
read-only checks. Diagnostic blocks use a stable code, path, message, and
remediation and exit with code 4. Doctor does not repair or delete files.

For `missing-receipt` or any recovery-state diagnostic, preserve all partial
and temporary paths and complete manual recovery first. For
`owned-file-changed`, restore the file from a trusted installation or keep the
change and perform a reviewed clean reinstall. For `tracked-private-file`,
remove the private path from the Git index without deleting the local file.

## Native CI

`.github/workflows/native-python.yml` defines a Python 3.11 matrix for native
Windows, Ubuntu, and macOS. Each job builds, runs the full test suite and
validator, performs install/update/doctor smoke checks, and requires clean
diff/status output. The workflow is structurally checked by repository tests.
Only Windows was executed locally for this change; native Linux and macOS
results remain pending until the hosted jobs run.
