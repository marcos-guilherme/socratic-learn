# Socratic Learn

[![Native Python safety matrix](https://github.com/marcos-guilherme/socratic-learn/actions/workflows/native-python.yml/badge.svg)](https://github.com/marcos-guilherme/socratic-learn/actions/workflows/native-python.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**A portable, evidence-aware Socratic protocol for learning anything.**

Socratic Learn gives compatible AI agents one structured method for helping
people learn any subject or skill—from conceptual domains to practical
abilities. It turns goals into observable outcomes, diagnoses only relevant
prerequisites, and adapts instruction from the learner's demonstrated
understanding.

Mathematics and AI are included as starter curricula and rigorous examples,
not as limits on what the protocol can teach. Socratic Learn is a protocol and
distribution toolkit—not an AI model or a separate chat application.

## What Socratic Learn provides

The canonical behavior lives in four small documents:

- [pedagogy](core/pedagogy.md), including responsive Socratic dialogue;
- [session protocol](core/session-protocol.md), including approval gates;
- [assessment](core/assessment.md), based on observable evidence; and
- [evidence policy](core/evidence-policy.md), including sourcing rules.

One deterministic prompt bundle installs through four project-local adapters:
Generic, Cursor, Claude Code, and Pi. Capability fallbacks keep the method
usable when an agent lacks web search, structured quizzes, rendering,
subagents, persistent memory, or filesystem access.

Socratic Learn asks a question only when the next step is reasonably
discoverable from the learner's demonstrated knowledge. When it is not, the
tutor explains directly and returns control through an application or
prediction.

## Quick start

Requirements: Git and Python 3.11 or newer. Socratic Learn has no third-party
runtime dependencies.

Clone the repository and build the checked-in distribution:

```powershell
git clone https://github.com/marcos-guilherme/socratic-learn.git
cd socratic-learn
python -m socratic_learn build
```

To try it without changing an existing project, create an empty directory:

```powershell
New-Item -ItemType Directory C:\temp\socratic-learn-demo
python -m socratic_learn install generic C:\temp\socratic-learn-demo
python -m socratic_learn doctor C:\temp\socratic-learn-demo
```

To use this repository itself as a learning workspace, copy the fictitious
starter profile into the ignored private area.

PowerShell:

```powershell
Copy-Item -Recurse workspace.example\* workspace
```

POSIX shell:

```sh
cp -R workspace.example/. workspace/
```

Then ask your agent for an observable learning outcome, for example:

```text
I want to learn to write a persuasive policy brief well enough to produce and
revise one for a real audience. First diagnose only the prerequisites needed
for that outcome.
```

```text
I want to understand self-attention well enough to implement it with tensor
operations. First diagnose only the prerequisites needed for that outcome.
```

## How a learning session works

1. The tutor turns the objective into an observable outcome and asks the
   learner to confirm it.
2. It diagnoses only relevant prerequisites.
3. It proposes the smallest dependency path, identifies demonstrated
   foundations and gaps, and waits for approval.
4. It teaches one approved node at a time.
5. The learner produces evidence through derivation, explanation, prediction,
   implementation, or error diagnosis.
6. The tutor records established concepts, remaining gaps, sources, and one
   next step.

Real learner profiles and session records stay private. Confidence and
self-report do not count as mastery without observable application.

## Install for your agent

Choose one project-local target:

| Target | Command | Discovery path |
| --- | --- | --- |
| Generic | `python -m socratic_learn install generic PROJECT` | `.socratic-learn/loader.md` |
| Cursor | `python -m socratic_learn install cursor PROJECT` | `.cursor/skills/socratic-learn/SKILL.md` |
| Claude Code | `python -m socratic_learn install claude-code PROJECT` | owned `CLAUDE.md` or an emitted snippet |
| Pi | `python -m socratic_learn install pi PROJECT` | `.pi/skills/socratic-learn/SKILL.md` |

The repository-native adapters are documented separately:

- [Cursor adapter](adapters/cursor/README.md)
- [Claude Code adapter](adapters/claude-code/README.md)
- [Pi adapter](adapters/pi/README.md)
- [Pi root-ready skill template](adapters/pi/skills/socratic-learn/SKILL.project.md.template)

Installations are namespaced under `.socratic-learn/`. Existing agent paths
are never merged or overwritten automatically.

## Commands

Run commands from the repository root:

```powershell
python -m socratic_learn build
python -m socratic_learn export prompt --output socratic-learn.prompt.md
python -m socratic_learn install cursor C:/path/to/project
python -m socratic_learn install cursor C:/path/to/project --update
python -m socratic_learn doctor C:/path/to/project
```

`build` produces deterministic checked-in artifacts. `export prompt` validates
the manifest before writing exact bundle bytes. `install` and `--update` use
ownership receipts. `doctor` is read-only and reports tampering, missing
files, invalid discovery links, and private-state mistakes.

There is no `--force` option.

See the [installation guide](docs/universal-installation.md), [manifest
reference](docs/manifest-reference.md), and [adapter extension
guide](docs/adding-an-adapter.md).

## Private learner state

In this repository, real goals, profiles, progress, and session records belong
under `workspace/`. In distributed installations they belong under
`.socratic-learn/workspace/`. Both locations are ignored by version control
except for their tracked `.gitkeep` placeholders.

Verify the repository workspace before publishing:

```powershell
git ls-files workspace
```

The output must contain only `workspace/.gitkeep`. Content under
[workspace.example](workspace.example/) is fictitious and safe to copy.

## Security and recovery

Socratic Learn protects against ordinary collisions, accidental concurrent
changes, and cooperating Socratic Learn processes. Controls include atomic
no-replace publication, parent-directory bindings, identity rechecks,
exact-topology cleanup, recovery artifacts, and Windows handle-bound
operations.

If publication becomes ambiguous, the tool preserves partial paths, staging,
and backups and reports manual recovery steps. It does not knowingly overwrite
modified or unowned files.

On POSIX systems, malicious or noncooperating processes running as the same OS
principal are outside the threat model. `rename`, `unlink`, and `rmdir` cannot
bind a leaf-entry mutation to an already-open inode, leaving an irreducible
leaf-entry TOCTOU window.

## Migrating from Learning Tutor

Socratic Learn recognizes an intact managed Learning Tutor installation under
`.learning-tutor/`. Use the same target recorded by that installation:

```powershell
python -m socratic_learn install TARGET PROJECT --update
```

Migration proceeds only when the legacy receipt proves ownership and every
managed hash still matches. Private workspace content moves with the managed
root. Modified, ambiguous, or unowned paths are preserved and migration stops
with an actionable diagnostic.

The old command remains temporarily available:

```powershell
python -m learning_tutor --help
```

It forwards to Socratic Learn and prints a deprecation warning. New
installations use only Socratic Learn names.

## Development

Run the complete local checks:

```powershell
python -m socratic_learn build
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --check
```

The validator checks required files, Markdown links, adapter metadata,
canonical-content boundaries, workspace privacy, manifests, generated
artifacts, README contracts, and deterministic rebuilds.

The [native CI workflow](.github/workflows/native-python.yml) runs build,
tests, validation, and install/update/doctor smoke checks on Python 3.11 for
Windows, Ubuntu, and macOS.

## Limitations

Socratic Learn does not provide an AI model, chat interface, quiz engine,
search provider, rendering service, persistent memory service, or agent
runtime. Those capabilities belong to the selected host. The protocol defines
fallbacks; it does not manufacture missing tools.

The bundled mathematics and AI maps are starter curricula, not the boundary
of the protocol and not exhaustive courses. For another subject or skill, the
agent constructs the smallest relevant dependency path from the learner's
goal and available evidence.

Universal protocol scope does not mean universal host knowledge. Reliability
still depends on the selected model, available sources and tools, and the
quality of evidence produced during the session. Socratic Learn does not
guarantee mastery.

Support means the four installation and discovery paths satisfy this
repository's contract; it does not certify every model or guarantee identical
interpretation.

## License

Socratic Learn is available under the [MIT License](LICENSE).
