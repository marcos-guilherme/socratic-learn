# Universal Learning Tutor Distribution — Design

## Objective

Turn the existing portable learning protocol into a universal distribution
that a person can use with a generic prompt, Cursor, Claude Code, or Pi without
manually reconstructing the canonical files or adapting relative links.

The first release is English-only, project-local, and executable directly from
a cloned or downloaded repository with Python 3.11 or newer. It does not
publish a pip package, standalone binaries, hosted application, model API, or
agent runtime.

## Meaning of Universal

No common discovery, skill, tool, or memory standard exists across all AI
agents. This project therefore defines universal distribution as:

1. one self-contained prompt artifact usable by any model that accepts a
   sufficiently large instruction;
2. tested native loaders for the first-release targets;
3. declared capability requirements and fallbacks;
4. deterministic installation and integrity checks;
5. behavioral conformance contracts that do not claim to certify model
   intelligence.

The canonical content is model-agnostic. Discovery and installation remain
agent-specific.

## First-Release Targets

- `generic`: a pasteable prompt bundle and a short loader.
- `cursor`: a project-local Cursor skill.
- `claude-code`: a safe root loader or a snippet for an existing loader.
- `pi`: a project-local Pi skill.

Codex CLI, Gemini CLI, hosted Custom GPTs, Gems, and other targets are deferred
until the core distribution contract is proven.

## Architecture

### Canonical source

The existing English Markdown files remain the single source of pedagogical
truth:

- `core/pedagogy.md`
- `core/session-protocol.md`
- `core/assessment.md`
- `core/evidence-policy.md`
- curriculum maps and shared record contracts referenced by those files

Generated prompts and target loaders must not become editable second sources.

### Python package

Add a standard-library-only package:

```text
learning_tutor/
├── __init__.py
├── __main__.py
├── build.py
├── manifest.py
├── install.py
├── doctor.py
├── errors.py
└── templates/
```

Responsibilities:

- `build.py`: load, normalize, order, and compile canonical content.
- `manifest.py`: create, parse, hash, and validate manifests and receipts.
- `install.py`: plan, stage, commit, and update target installations.
- `doctor.py`: inspect an installation without modifying it.
- `errors.py`: stable error categories and CLI exit codes.
- `templates/`: thin target-specific loader templates only.

Each module exposes narrow functions so build, install, and validation logic can
be tested without invoking subprocesses.

### Generated distribution

`python -m learning_tutor build` creates:

```text
dist/
├── learning-tutor.prompt.md
└── manifest.json
```

The prompt bundle contains, in fixed order:

1. identity and operating boundaries;
2. canonical pedagogy;
3. session protocol;
4. assessment rules;
5. evidence policy;
6. capability fallbacks;
7. private-state and session-record contracts;
8. curriculum index.

It contains no Cursor, Claude Code, or Pi instructions. A generated-file header
states the protocol version, language, and canonical source paths.

## Deterministic Build Contract

The first protocol version is `1.0.0`; manifest schema version is integer `1`.

Build output is UTF-8 with LF line endings and exactly one trailing newline.
Input ordering is explicit, not filesystem-dependent. Generated artifacts omit
timestamps, absolute paths, machine names, and environment-specific values.
Identical source bytes must produce identical output bytes and SHA-256 hashes
on Windows, macOS, and Linux.

The build fails if:

- a canonical source is absent;
- a referenced local file is absent;
- a forbidden adapter-specific term appears in the universal bundle;
- a required behavioral section is missing;
- an input is not valid UTF-8;
- a generated artifact would contain an absolute local path.

## Manifest Contract

`dist/manifest.json` is stable, sorted, and pretty-printed with a final newline.
It contains:

```json
{
  "schema_version": 1,
  "protocol_version": "1.0.0",
  "language": "en",
  "bundle": {
    "path": "learning-tutor.prompt.md",
    "sha256": "<hex>"
  },
  "sources": [
    {"path": "core/pedagogy.md", "sha256": "<hex>"}
  ],
  "targets": ["generic", "cursor", "claude-code", "pi"],
  "capabilities": {},
  "session_record": {},
  "owned_artifacts": []
}
```

`capabilities` distinguishes required conversational ability from optional web,
structured questions, rendering, filesystem, subagents, and cross-session
memory. Every optional capability names its conversational or file-based
fallback.

`session_record` contains the exact required heading sequence. The manifest
does not duplicate full pedagogical prose.

## Installation Layout

Every target uses a project-local namespaced package:

```text
<project>/
└── .learning-tutor/
    ├── manifest.json
    ├── learning-tutor.prompt.md
    ├── install.json
    ├── loader.md
    ├── .gitignore
    └── workspace/
        └── .gitkeep
```

`.learning-tutor/.gitignore` ignores private files under `workspace/` while
retaining `.gitkeep`. The installer never needs to edit the project's root
`.gitignore`.

Target-specific entry points live in their native project locations. They are
thin loaders that refer back to `.learning-tutor/`:

- Cursor: `.cursor/skills/learning-tutor/SKILL.md`
- Claude Code: root `CLAUDE.md` only when absent; otherwise emit a snippet
- Pi: `.pi/skills/learning-tutor/SKILL.md`
- Generic: no native file; print and store a short loader

Existing agent files are never merged automatically in version 1.

## Installation Receipt and Ownership

`.learning-tutor/install.json` records:

- receipt schema version;
- protocol version;
- selected target;
- installed relative paths;
- SHA-256 of each owned file except `install.json` itself;
- bundle and manifest hashes.

The receipt is owned metadata but is excluded from its own hash map because a
file cannot contain its own stable cryptographic hash. `doctor` validates the
receipt schema, protocol, paths, and every hash it references.

The receipt is the authority for updates. `--update` may replace a managed file
other than the receipt only when:

1. the path is listed in the existing receipt;
2. its current hash matches the old receipt;
3. the new installation plan claims the same path.

A missing, modified, unowned, or colliding path aborts the entire update before
mutation. There is no `--force` option in version 1.

## CLI Contract

```text
python -m learning_tutor build
python -m learning_tutor export prompt [--output FILE]
python -m learning_tutor install TARGET PROJECT
python -m learning_tutor install TARGET PROJECT --update
python -m learning_tutor doctor PROJECT
```

### Build

Validates canonical sources, writes deterministic distribution artifacts, and
prints their relative paths and hashes.

### Export

Writes the already validated prompt bundle to stdout or `--output`. It does not
reformat or customize the bundle.

### Install

Accepts only `generic`, `cursor`, `claude-code`, or `pi`. The project must
already exist and be a directory. Installation is collision-safe and
project-local.

### Doctor

Checks receipt schema, owned-file hashes, manifest and bundle integrity, local
links, target discovery path, private-state ignore rules, protocol version,
and unexpected missing files. It is read-only and returns actionable
diagnostics.

## Transaction and Error Model

Installation has two phases:

1. calculate and validate the complete operation in memory;
2. stage artifacts in a temporary directory on the target filesystem and
   rename them into place.

No target file is changed until all preconditions pass. If commit-time
filesystem failure occurs, the installer removes files created by the current
operation and reports any path it could not restore. It never removes
pre-existing paths.

Stable exit codes:

- `0`: success;
- `2`: command usage or unsupported target;
- `3`: collision or modified managed file;
- `4`: source, manifest, receipt, hash, or link integrity failure;
- `5`: filesystem or transaction failure.

Errors go to stderr and contain the failing path, cause, and next safe action.
Normal machine-readable output is not required in version 1.

## Target Behavior

### Generic

Install the namespaced package and store `loader.md`. Print the loader so it can
be pasted into any system prompt or chat that supports a sufficiently large
context. No automatic discovery is claimed.

### Cursor

Install a project skill that loads the namespaced prompt and state contract.
Refuse to overwrite an existing `.cursor/skills/learning-tutor` directory.

### Claude Code

If root `CLAUDE.md` is absent, install a thin owned loader. If it exists, leave
it untouched, install the namespaced package, and emit an exact snippet for
manual integration. The receipt must distinguish an installed loader from an
emitted snippet.

### Pi

Install a root-ready project skill under `.pi/skills/learning-tutor/`. Refuse
any existing directory collision, including an empty directory.

## Conformance Contract

Conformance validates generated instructions, not model intelligence. Fixtures
must prove the prompt explicitly requires:

1. conversion of a vague interest into an observable outcome;
2. bounded prerequisite diagnosis;
3. plan presentation and learner approval before teaching;
4. responsive Socratic dialogue based on the preceding answer;
5. direct exposition when discovery is not reasonable;
6. return to active application after exposition;
7. mathematical assumptions and claim classification;
8. primary-source verification for volatile technical claims;
9. capability fallbacks;
10. private-state handling;
11. evidence-based session closure.

The suite must avoid testing arbitrary prose or exact full-document wording.

## Tests

### Unit tests

- deterministic normalization and compilation;
- SHA-256 and sorted manifest serialization;
- manifest and receipt validation;
- CLI parsing and exit-code mapping;
- install-plan collision and update ownership rules.

### Installation tests

Use temporary project directories for all four targets. Cover clean install,
every native-path collision, existing Claude loader, modified managed files,
missing receipt, update success, transaction failure, private-state ignore
rules, and `doctor` diagnostics.

### End-to-end smoke

From a clean repository copy:

1. build twice and compare bytes and hashes;
2. install each target in a separate temporary project;
3. run `doctor` for each;
4. verify private workspace files are ignored;
5. run an unchanged update;
6. confirm the repository validator and complete unit suite pass.

Tests must use `pathlib` and standard-library temporary directories and work on
Windows-compatible paths.

## Documentation

The root README gains a universal distribution quick start, command reference,
target support statement, safety model, and explicit definition of what
“universal” does and does not mean.

Add:

- `docs/universal-installation.md`
- `docs/manifest-reference.md`
- `docs/adding-an-adapter.md`

All user-facing distribution documentation and CLI messages are English.

## Out of Scope

- pip or system package publication;
- standalone executables;
- hosted UI or model gateway;
- model API calls;
- automatic modification of existing agent instruction files;
- remote updates;
- telemetry;
- runtime tool abstraction or MCP server;
- certification of arbitrary model quality;
- non-English generated bundles.

## Acceptance Criteria

1. A user with Python 3.11 can build and export one portable prompt.
2. The same repository installs collision-safe loaders for all four targets.
3. Repeated builds are byte-identical.
4. `doctor` detects tampering, missing files, invalid links, and privacy errors.
5. Updates never overwrite user-modified or unowned files.
6. A generic user can paste one loader and prompt bundle without understanding
   the repository layout.
7. The generated artifacts encode every behavioral conformance requirement.
8. The full suite and clean-copy smoke pass on Windows-compatible paths.
