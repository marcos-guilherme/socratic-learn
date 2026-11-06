# Adding an Adapter

An adapter is a thin discovery loader around the canonical generated prompt.
It maps host capabilities and paths; it must not restate pedagogy, assessment,
session, evidence, or curriculum prose.

## Template boundary

Keep adapter templates under `learning_tutor/templates/`. A template may:

- identify the installed prompt and private workspace with relative POSIX
  paths;
- provide minimal host-specific discovery metadata;
- map optional host capabilities to the manifest fallback contract.

It may not duplicate canonical prose from `core/` or curricula. Behavioral
changes belong in canonical sources and flow through the deterministic build.

## Registration and ownership

Adding a target requires an intentional protocol change. Update the exact
target sequence in `learning_tutor/__init__.py`, manifest validation, installer
planning, doctor discovery mapping, CLI choices, documentation, and tests.

All installed files must be project-local. Add every managed path to the
schema-1 receipt and hash every owned file except
`.learning-tutor/install.json`. Never claim ownership of a pre-existing host
file. If integration requires editing a user-owned file, preserve it and emit
an exact manual snippet, as the Claude Code adapter does.

## Loader links

Resolve links from the loader's installed directory, not from the repository
root. A native loader must link to
`.learning-tutor/learning-tutor.prompt.md` and, when it records state, to
`.learning-tutor/workspace/`. Use `/` in templates and documentation. Doctor
must verify the exact native discovery path and reject a loader moved to a
different known path.

## Collision and recovery tests

Tests for a new adapter must cover:

1. clean installation and exact receipt ownership;
2. collision at the install root, native destination directory, final loader,
   and every blocking parent;
3. no merge, overwrite, delete, or `--force` behavior;
4. unchanged update and refusal after one managed file is modified;
5. loader-link resolution from the final installed location;
6. healthy doctor output plus missing, moved, changed, and unreadable loader
   diagnostics;
7. publication races and conservative recovery.

When publication may have occurred, tests must require preservation of partial
published paths, private staging directories, and backups. Recovery errors
must list those paths for manual inspection; cleanup must never delete data
whose identity or ownership is uncertain.

## Repository checks

Extend repository validation to require the template and documentation. Keep
the validator standard-library-only and side-effect-free: it builds in memory
and compares exact bytes with checked-in `dist/` without writing either.
Run the complete suite, validator, and `git diff --check`, then repeat them in
a clean clone after committing.
