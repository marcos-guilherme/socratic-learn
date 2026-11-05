# Portable AI Learning Environment

## What this is

This repository is a portable tutor protocol, not an AI application. It defines shared behavior for conducting evidence-aware mathematics and AI learning sessions across compatible agents. The canonical core consists of the [pedagogy](core/pedagogy.md), [session protocol](core/session-protocol.md), [assessment](core/assessment.md), and [evidence policy](core/evidence-policy.md).

The core includes responsive Socratic dialogue: when a next step is discoverable from the learner's demonstrated knowledge, each question responds to the learner's previous reasoning rather than following a fixed script. The tutor uses direct explanation when information is not reasonably discoverable, then returns control through a question or application.

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
- **Pi:** copy or link the [Pi learning tutor skill](adapters/pi/skills/learning-tutor/SKILL.md) into a skills directory loaded by Pi and preserve or adjust its relative links. See the [Pi adapter](adapters/pi/README.md). Pi extensions are optional.

## Private learner state

Real learner profiles, goals, progress, and session records belong only in `workspace/`, which is ignored except for `.gitkeep`. Content in [workspace.example](workspace.example/) is fictitious starter material. Copy it into `workspace/`, edit only the private copies, and verify that Git does not track them:

```powershell
git ls-files workspace
```

The output should contain only `workspace/.gitkeep`.

## Validation

Run the complete unit-test suite and repository validator from the repository root:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
```

The validator checks required files, internal Markdown links, adapter metadata, canonical-content boundaries, workspace ignore rules, and tracked private files.

## Limitations

This repository supplies instructions, curriculum maps, templates, examples, and adapter entry points. It does not provide an AI model, chat interface, quiz engine, web search, rendering service, persistent memory service, or extension runtime. Those capabilities depend on the agent in use. When a capability is absent, the protocol specifies conversational or filesystem-based fallbacks; it does not claim to add the missing tool.

The included curriculum maps cover selected mathematics and AI paths. They are dependency guides rather than exhaustive courses, and learner mastery is not inferred from confidence or self-report.
