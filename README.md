# Portable AI Learning Environment

## What this is

This repository is a portable tutor protocol, not an AI application. It defines shared behavior for conducting evidence-aware mathematics and AI learning sessions across compatible agents. The canonical core consists of the [pedagogy](core/pedagogy.md), [session protocol](core/session-protocol.md), [assessment](core/assessment.md), and [evidence policy](core/evidence-policy.md).

The core includes responsive Socratic dialogue: when a next step is discoverable from the learner's demonstrated knowledge, each question responds to the learner's previous reasoning rather than following a fixed script. The tutor uses direct explanation when information is not reasonably discoverable, then returns control through a question or application.

## Universal distribution

“Universal” means that one deterministic protocol and bundle can be installed
through the four supported project-local adapters: Generic, Cursor, Claude
Code, and Pi. It does not mean that every model, model version, or host is
certified. Host capabilities still vary, and the manifest defines fallbacks
when a capability is unavailable.

The distribution tools require Python 3.11 or newer and use no third-party
dependencies. From the repository root, the five primary commands are:

```powershell
python -m learning_tutor build
python -m learning_tutor export prompt --output tutor.prompt.md
python -m learning_tutor install cursor C:/path/to/project
python -m learning_tutor install cursor C:/path/to/project --update
python -m learning_tutor doctor C:/path/to/project
```

Installations live under `.learning-tutor/`; Cursor and Pi also receive thin
native skills, while Claude Code receives an owned thin loader only when root
`CLAUDE.md` is absent. Every install has a schema-1 ownership receipt. Existing
agent paths are never merged or overwritten automatically, and there is no
`--force` option. Export output follows the same rule: an existing or raced
output is preserved and rejected. If publication fails after paths may have appeared, partial
paths, private staging directories, and backups are preserved and reported for
manual recovery rather than deleted.

Start with the [universal installation guide](docs/universal-installation.md).
The [manifest reference](docs/manifest-reference.md) defines artifact and hash
semantics, and [adding an adapter](docs/adding-an-adapter.md) defines extension
boundaries.

## Quick start

1. Clone or download this repository.
2. Create the private working area from the fictitious examples. The tracked `workspace/.gitkeep` means the destination directory already exists.

PowerShell:

```powershell
Copy-Item -Recurse workspace.example\* workspace
```

POSIX shell:

```sh
cp -R workspace.example/. workspace/
```

3. Open the repository with a supported agent and ask to start a learning session with an observable goal. For example:

```text
Quero entender self-attention o suficiente para implementá-la com operações
tensoriais. Faça primeiro um diagnóstico curto dos pré-requisitos.
```

Do not add files under `workspace/` to version control. The repository's ignore rules exclude them while retaining `workspace/.gitkeep`.

## How a learning session works

The tutor first turns the objective into an observable outcome and asks the learner to confirm it. It then diagnoses only relevant prerequisites, proposes the smallest dependency path with explicit edges, and waits for approval before teaching.

The approved path is taught one node at a time. Each node requires observable evidence such as a derivation, explanation, prediction, implementation, or error diagnosis. Questions adapt to the learner's actual answers; direct exposition is used when discovery would be impossible or impose inappropriate cognitive load. At the end, when filesystem access is available, the tutor records evidence, remaining gaps, sources, and one next step under the private workspace. Without filesystem access, the tutor returns the complete Markdown record for the learner to save.

## Supported agents

- **Generic agents:** begin with [AGENTS.md](AGENTS.md), which points to the complete canonical protocol.
- **Cursor:** opening this repository makes the project [learning tutor skill](.cursor/skills/learning-tutor/SKILL.md) available automatically. See the [Cursor adapter](adapters/cursor/README.md).
- **Claude Code:** use the provided [Claude Code loader](adapters/claude-code/CLAUDE.md). Its relative links are adapter-local, so follow the [installation instructions](adapters/claude-code/README.md) when creating a root `CLAUDE.md`.
- **Pi:** follow the non-destructive [Pi installation instructions](adapters/pi/README.md), which install the [root-ready skill template](adapters/pi/skills/learning-tutor/SKILL.project.md.template) against a namespaced canonical package. Pi extensions are optional.

## Private learner state

Real learner profiles, goals, progress, and session records belong only in `workspace/`, which is ignored except for `.gitkeep`. Content in [workspace.example](workspace.example/) is fictitious starter material. Copy it into `workspace/`, edit only the private copies, and verify that Git does not track them:

```powershell
git ls-files workspace
```

The output should contain only `workspace/.gitkeep`.

For a distributed installation, the corresponding private location is
`.learning-tutor/workspace/`. Its nested `.gitignore` keeps records private
even when the host project does not use this repository's root ignore rules.

## Validation

Run the complete unit-test suite and repository validator from the repository root:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
```

The validator checks required files, internal Markdown links, adapter metadata,
canonical-content boundaries, workspace ignore rules, tracked private files,
manifest validity, the generated header, and byte-for-byte agreement between
an in-memory build and checked-in `dist/`. It does not write generated files.

The native CI workflow runs these checks plus build and
install/update/doctor smoke tests on Python 3.11 for Windows, Ubuntu, and
macOS. Native Linux and macOS execution remains pending until hosted CI runs;
local verification does not substitute for those backends.

## Limitations

This repository supplies instructions, curriculum maps, templates, examples, and adapter entry points. It does not provide an AI model, chat interface, quiz engine, web search, rendering service, persistent memory service, or extension runtime. Those capabilities depend on the agent in use. When a capability is absent, the protocol specifies conversational or filesystem-based fallbacks; it does not claim to add the missing tool.

The included curriculum maps cover selected mathematics and AI paths. They are dependency guides rather than exhaustive courses, and learner mastery is not inferred from confidence or self-report.

No claim is made that all models interpret the protocol identically or are
certified. Support means the four discovery/install paths are tested against
this repository's contract.
