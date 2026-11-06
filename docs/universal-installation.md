# Socratic Learn Installation

## Normal installation

Normal users install once and run `socratic`; they do not clone or build this
repository. Native installers are intended for published x86-64 Windows,
Linux, and macOS artifacts:

```powershell
$script = irm https://raw.githubusercontent.com/marcos-guilherme/socratic-learn/main/scripts/install.ps1; & ([scriptblock]::Create($script))
```

```sh
sh -c 'tmp=$(mktemp) || exit; curl -fsSL https://raw.githubusercontent.com/marcos-guilherme/socratic-learn/main/scripts/install.sh -o "$tmp" && sh "$tmp"; status=$?; rm -f "$tmp"; exit $status'
```

This documentation does not claim that a public release or tag already exists.
The first native binaries are unsigned. The installers warn that Windows
SmartScreen or macOS Gatekeeper may intervene and require confirmation before
download. SHA-256 verification proves that downloaded bytes match release
metadata; it does not replace platform signing or notarization.

Native installers reject unsupported architectures and honestly offer:

```text
pipx install socratic-learn
```

The pipx fallback requires Python 3.11 or newer and is also suitable when a
Python-managed environment is preferred.

## Native channel behavior

The installer places `socratic` in a user-owned binary directory and records
non-secret native channel metadata at `~/.socratic-learn/channel.json`. The
metadata contains the schema version, the `native` channel name, the absolute
executable path, and the canonical release-manifest URL. It contains no
provider credentials.

The Windows installer selects one exact `windows`/`x86_64` manifest artifact,
then verifies its declared size and SHA-256 digest. The POSIX installer selects
`socratic-linux-x86_64` or `socratic-macos-x86_64` and verifies the unique
matching entry in `SHA256SUMS`. Redirects remain inside each installer's
documented trusted boundary.

`socratic update` downloads and verifies a replacement before publication.
On POSIX it atomically replaces the executable; on Windows a detached helper
waits for the running process to exit before replacement. Download or
verification failure removes staging and preserves the previous executable:
this is the update rollback guarantee.

`socratic uninstall` removes the native executable and channel metadata but
preserves learner data by default. `socratic uninstall --delete-data` requires
interactive confirmation; `--yes` is accepted only with `--delete-data`.

## Pipx channel behavior

An installation with no native channel metadata is treated as Python/pipx
managed. Socratic Learn never rewrites or removes that environment. Instead:

- `socratic update` prints `pipx upgrade socratic-learn`;
- `socratic uninstall` prints `pipx uninstall socratic-learn`.

Pipx itself owns package update and removal. Learner profiles, progress, and
sessions under `~/.socratic-learn/learning/` remain separate, so package
removal preserves learner data.

## Source and project-adapter requirements

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
changes, and cooperating Socratic Learn processes. Atomic no-replace moves,
parent-directory file descriptors, identity rechecks, exact-topology cleanup,
recovery artifacts, and Windows handle-bound operations remain mandatory. On
POSIX, malicious or noncooperating processes running as the same OS principal
are out of scope: `rename`, `unlink`, and `rmdir` cannot condition a leaf-entry
mutation on an already-open inode, so an irreducible leaf-entry TOCTOU window
remains. A detected ambiguity is preserved and reported; this limitation does
not disable normal Linux or macOS build, install, update, or cleanup.

Build the checked-in distribution before installing:

```powershell
python -m socratic_learn build
```

`export prompt --output PATH` is also no-force: every parent is created through
identity-bound operations, an existing output is rejected, and publication is
an atomic native no-replace move. If another process wins the final output
race, its file is preserved. The error reports the private temporary artifact
for recovery; it is never blindly unlinked after an identity ambiguity.

## Generic

```powershell
python -m socratic_learn install generic C:/path/to/project
```

The installer creates `.socratic-learn/loader.md`. Point an agent that accepts
project instructions to that loader. It links to the installed canonical
prompt rather than copying the pedagogy.

## Cursor

```powershell
python -m socratic_learn install cursor C:/path/to/project
```

Cursor receives `.cursor/skills/socratic-learn/SKILL.md`. The skill is a thin
loader for `.socratic-learn/socratic-learn.prompt.md`.

## Claude Code

```powershell
python -m socratic_learn install claude-code C:/path/to/project
```

If root `CLAUDE.md` does not exist, the installer creates and owns a thin
loader. If it already exists as a regular file, the installer preserves it and
prints the exact snippet to append manually. It never merges or overwrites a
user-owned `CLAUDE.md`.

## Pi

```powershell
python -m socratic_learn install pi C:/path/to/project
```

Pi receives `.pi/skills/socratic-learn/SKILL.md`, which links to the same
project-local prompt and private workspace as the other targets.

## Collisions and ownership

Every install records schema-2 ownership with product identifier
`socratic-learn` in
`.socratic-learn/install.json`. A clean install refuses an existing
`.socratic-learn/` path or native adapter destination. There is no `--force`
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
python -m socratic_learn install cursor C:/path/to/project --update
```

Before changing anything, update validates the receipt and every managed
file. An unchanged update is safe. If a managed file was edited, is missing,
or no longer matches its recorded identity, update refuses before replacing
other files. Preserve user changes and restore or reinstall only after review.

## Migrating from Learning Tutor

An intact schema-1 installation under `.learning-tutor/` can be migrated by
running the canonical update command with the target recorded in its receipt:

```powershell
python -m socratic_learn install TARGET C:/path/to/project --update
```

Migration verifies every legacy managed hash before mutation, refuses when
both old and new roots exist, and rejects unowned paths outside the private
workspace. It renames the managed root and owned native skill without
overwriting a destination, preserves private workspace content, replaces
managed files, and publishes the schema-2 receipt last. Modified or ambiguous
legacy installations remain untouched or are preserved with explicit recovery
paths.

## Private learner state

Private records belong under `.socratic-learn/workspace/`. The nested
`.socratic-learn/.gitignore` ignores workspace content while retaining
`workspace/.gitkeep`. Confirm repository behavior with:

```powershell
git check-ignore C:/path/to/project/.socratic-learn/workspace/private.md
```

## Doctor

```powershell
python -m socratic_learn doctor C:/path/to/project
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
