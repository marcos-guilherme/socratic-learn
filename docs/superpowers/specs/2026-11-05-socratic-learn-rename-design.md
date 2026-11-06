# Socratic Learn Rename and Public Release Design

## Goal

Rename the portable learning environment to **Socratic Learn**, make the new
name canonical throughout the public and technical experience, preserve a
safe migration path for existing Learning Tutor installations, and publish a
well-documented public GitHub repository.

Success means that a new user can understand the project from the README,
install it through any supported adapter, and use only Socratic Learn names.
An existing user can invoke the legacy package or update a managed legacy
installation without losing private learner data or overwriting unowned
files.

## Public identity

- Product name: `Socratic Learn`
- Repository name: `socratic-learn`
- Repository owner: `marcos-guilherme`
- Visibility: public
- License: MIT
- Tagline: `A portable Socratic learning protocol for mathematics and AI.`
- Canonical Python package and module command: `socratic_learn` and
  `python -m socratic_learn`
- Canonical managed directory: `.socratic-learn/`
- Canonical skill and adapter identifier: `socratic-learn`
- Canonical generated prompt: `dist/socratic-learn.prompt.md`
- Canonical protocol identifier in generated metadata: `socratic-learn`

The GitHub repository will include a concise description, relevant topics,
Python 3.11 and CI badges, and links to the installation and extension
documentation.

## Rename strategy

The rename is a compatible migration, not a dual-brand product.
`socratic_learn` is canonical for all new commands, documentation,
installations, receipts, skills, adapters, and generated artifacts.

The old `learning_tutor` Python module remains temporarily as a deprecated
compatibility shim. It forwards the old module command to the new
implementation and emits a concise deprecation warning to standard error.
It does not maintain a second implementation or private state.

Legacy managed installations under `.learning-tutor/` remain recognizable.
An update may migrate them only when the existing receipt proves ownership
and all managed files still match their recorded identities and hashes.
Modified, ambiguous, or unowned paths are preserved and rejected with
actionable diagnostics. Migration produces one canonical
`.socratic-learn/` installation and never duplicates private learner state.

The manifest and receipt schemas remain version-compatible where possible.
Name changes that affect interpretation must be represented explicitly and
validated as closed schema fields rather than inferred from paths.

## README information architecture

The README is the primary onboarding document and uses this order:

1. Product name, tagline, CI/Python badges, and a one-paragraph definition.
2. What Socratic Learn provides and what it deliberately does not provide.
3. A short safe quick start that does not modify an existing project.
4. How a Socratic learning session works.
5. Installation choices for Generic, Cursor, Claude Code, and Pi.
6. Build, export, install, update, and doctor commands.
7. Private learner-state rules.
8. Filesystem security model and recovery behavior.
9. Migration from Learning Tutor.
10. Development, validation, contribution, and MIT license information.

Examples and documentation remain in English for universal distribution.
Claims must stay precise: Socratic Learn is a protocol and distribution
toolkit, not an AI model, chat interface, search provider, or guarantee that
all models behave identically.

## Component changes

### Python package and CLI

Move the implementation to `socratic_learn/`. All internal imports, tests,
workflow commands, examples, and diagnostics use the canonical package.
Keep `learning_tutor/` only as the smallest forwarding package needed for
the compatibility window.

### Distribution artifacts

The deterministic build emits `dist/socratic-learn.prompt.md` and a manifest
whose paths, identifiers, hashes, contracts, and adapter metadata use the new
name. Checked-in artifacts are rebuilt and remain byte-deterministic.

### Installations and adapters

New installs use `.socratic-learn/` and namespaced `socratic-learn` skills or
loaders. Cursor, Claude Code, Pi, and generic adapters retain their current
behavior and collision guarantees. Existing third-party or user-owned
`learning-tutor` and `socratic-learn` paths are never merged or overwritten.

### Doctor and migration

`doctor` diagnoses canonical installations and reports legacy installations
with a clear migration action. A migration is transactional, publishes the
new receipt last, and follows the existing conservative recovery policy.
Private workspace records are moved only when ownership and identity are
proven; otherwise both the legacy state and any recovery artifacts are
preserved.

### Repository documentation

Rename adapter directories, skill directories, templates, examples, and
links where they are part of the public contract. Historical design and plan
documents may retain old terminology when it describes the historical
system, but they must clearly link to this rename decision when ambiguity is
possible.

## Safety and error handling

The existing filesystem threat model remains unchanged. The tools protect
against ordinary collisions, accidental concurrent changes, and cooperating
Socratic Learn processes. Detected ambiguity is preserved for manual
recovery. Malicious same-principal POSIX leaf-entry replacement remains an
explicitly documented operating-system limitation.

There is no `--force` option. Export, installation, migration, and update use
atomic no-replace publication and identity-aware recovery. Errors name the
affected path, state what was preserved, and give one concrete remediation.

## Testing and validation

Tests cover:

- canonical package imports and every CLI command;
- legacy module forwarding and deprecation output;
- deterministic renamed artifacts and closed manifest validation;
- clean installs for all four adapters;
- successful owned legacy migration;
- rejection of modified, ambiguous, or unowned legacy paths;
- preservation of private learner state;
- doctor behavior before and after migration;
- README links, badges, commands, terminology, and private-state guidance;
- repository validation and clean-clone smoke tests.

The native CI matrix runs Python 3.11 on Windows, Ubuntu, and macOS. It builds
the distribution, runs the complete test suite and validator, performs
install/update/doctor smoke tests, and verifies a clean generated diff.

## Publication sequence

1. Implement the rename and compatibility layer on a feature branch.
2. Rebuild artifacts and pass local focused, full, validator, deterministic,
   and clean-clone verification.
3. Complete a whole-branch review.
4. Merge to `master`.
5. Create the public GitHub repository
   `marcos-guilherme/socratic-learn`.
6. Add it as the existing repository's first `origin` and push `master`.
7. Apply the description and topics, then verify the repository URL and
   native CI checks.

No second remote or repository is created if an origin appears before
publication. No secrets, private workspace files, caches, or recovery
artifacts may be included in the public repository.

## Completion criteria

The rename is complete when:

- public documentation and all new-user paths say Socratic Learn;
- canonical package, commands, managed paths, skills, artifacts, manifests,
  and receipts use the new identifiers;
- old module invocation and owned legacy installations have tested,
  non-destructive migration behavior;
- the MIT license and structured README are present;
- all local verification passes;
- the public GitHub repository exists at the expected URL;
- `master` is pushed without private learner data; and
- Windows, Ubuntu, and macOS CI results are observed and reported honestly.
