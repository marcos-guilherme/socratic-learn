# Universal Installation

## Requirements and scope

Use Python 3.11 or newer from the repository root. The distribution supports
exactly four project-local targets: `generic`, `cursor`, `claude-code`, and
`pi`. “Universal” means that one deterministic tutor protocol can be
distributed through these adapters. It does not certify every model, agent
version, or host capability.

Build the checked-in distribution before installing:

```powershell
python -m learning_tutor build
```

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
operation-created temporary paths when their identity is known and cleanup is
safe.

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
