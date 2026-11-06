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

The `socratic` launcher delivers one deterministic prompt bundle to Pi, Claude
Code, or Antigravity. These launcher hosts provide the model, authentication,
and interactive terminal. Cursor remains a project integration, alongside the
Generic, Claude Code, and Pi project-discovery adapters. Capability fallbacks
keep the method usable when a host lacks web search, structured quizzes,
rendering, subagents, persistent memory, or filesystem access.

Socratic Learn asks a question only when the next step is reasonably
discoverable from the learner's demonstrated knowledge. When it is not, the
tutor explains directly and returns control through an application or
prediction.

## Quick start

Normal use requires no repository clone and no source build. The native
installers target x86-64 Windows, Linux, and macOS. Native installation is
available only after GitHub Release v0.1.0 is published. When that release
exists, download its version-scoped installer asset to a temporary file and
review it before execution.

Windows PowerShell:

```powershell
$installer = Join-Path $env:TEMP "socratic-install-v0.1.0.ps1"
Invoke-WebRequest https://github.com/marcos-guilherme/socratic-learn/releases/download/v0.1.0/install.ps1 -OutFile $installer
Get-Content $installer
```

After reviewing the downloaded file:

```powershell
& $installer
```

Linux or macOS:

```sh
installer=$(mktemp)
curl -fL https://github.com/marcos-guilherme/socratic-learn/releases/download/v0.1.0/install.sh -o "$installer"
cat "$installer"
```

After reviewing the downloaded file:

```sh
sh "$installer"
rm -f "$installer"
```

The installers verify release hashes and require confirmation before
downloading. The first native binaries are unsigned and may trigger Windows
SmartScreen or macOS Gatekeeper warnings. A checksum verifies downloaded bytes;
it is not a substitute for code signing. This documentation does not claim
that a public release or tag already exists.

The x86-64 native build is the preferred install-once channel. On another
architecture, or if you prefer a Python-managed environment, use Python 3.11+
and pipx after package publication. The pipx command is available only after
socratic-learn 0.1.0 is published on PyPI.

```text
pipx install socratic-learn
```

Start the launcher without a goal:

```text
socratic
```

It detects Pi, Claude Code, and Antigravity, asks you to select an available
launcher host on first use, and remembers that selection. No-argument prompting
is the privacy default because it avoids putting the learning goal in shell
history. Socratic Learn does not store provider credentials; the selected host
uses its own authentication.

You can pass a goal directly for convenience, but it may enter your shell
history:

```text
socratic "I want to learn linear algebra"
socratic --agent pi
```

By default, personal launcher profiles, progress, and sessions live under
`~/.socratic-learn/learning/.socratic-learn/workspace/`. To use the current
directory as the learning project instead, run:

```text
socratic --here
```

The launcher prepares the protocol and private workspace, then runs the chosen
host in that workspace. The host retains its normal terminal, authentication,
permissions, and model selection, and `socratic` returns its exit status.

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

The launcher is the normal user path. Project-discovery adapters are separate:
they install protocol instructions into an existing project for an agent that
opens that project. Choose one project-local target:

| Target | Command | Discovery path |
| --- | --- | --- |
| Generic | `python -m socratic_learn install generic PROJECT` | `.socratic-learn/loader.md` |
| Cursor | `python -m socratic_learn install cursor PROJECT` | `.cursor/skills/socratic-learn/SKILL.md` |
| Claude Code | `python -m socratic_learn install claude-code PROJECT` | owned `CLAUDE.md` or an emitted snippet |
| Pi | `python -m socratic_learn install pi PROJECT` | `.pi/skills/socratic-learn/SKILL.md` |

The project adapters are documented separately:

- [Cursor adapter](adapters/cursor/README.md)
- [Claude Code adapter](adapters/claude-code/README.md)
- [Pi adapter](adapters/pi/README.md)
- [Pi root-ready skill template](adapters/pi/skills/socratic-learn/SKILL.project.md.template)

Installations are namespaced under `.socratic-learn/`. Existing agent paths
are never merged or overwritten automatically.

## Commands

Native installs update their own verified executable. Pipx installs do not
mutate their environment; these commands print the matching pipx instruction.
Uninstall preserves learner data unless deletion is explicitly requested and
confirmed.

```text
socratic update
socratic uninstall
```

For pipx, the corresponding commands are `pipx upgrade socratic-learn` and
`pipx uninstall socratic-learn`. See the [installation
guide](docs/universal-installation.md), [launcher adapter
contract](docs/launcher-adapters.md), [manifest
reference](docs/manifest-reference.md), and [adapter extension
guide](docs/adding-an-adapter.md).

Source-only administrative commands (`build`, `export`, project `install`, and
`doctor`) are for contributors and project integrations. There is no `--force`
option.

## Private learner state

Personal launcher state belongs under
`~/.socratic-learn/learning/.socratic-learn/workspace/`. Project adapters store
private state under `PROJECT/.socratic-learn/workspace/`. In this source
repository, real goals, profiles, progress, and session records belong under
`workspace/`. Project and repository locations are ignored by version control
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

Contributors, unlike normal users, clone and build the source:

```powershell
git clone https://github.com/marcos-guilherme/socratic-learn.git
cd socratic-learn
python -m socratic_learn build
```

To populate this repository's ignored example workspace:

```powershell
Copy-Item -Recurse workspace.example\* workspace
```

```sh
cp -R workspace.example/. workspace/
```

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
