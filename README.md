# Socratic Learn

[Native Python safety matrix](https://github.com/marcos-guilherme/socratic-learn/actions/workflows/native-python.yml)
· [Python 3.11+](https://www.python.org/downloads/)
· [License: MIT](LICENSE)

```text
  ███████╗ ██████╗  ██████╗██████╗  █████╗ ████████╗██╗ ██████╗
  ██╔════╝██╔═══██╗██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██║██╔════╝
  ███████╗██║   ██║██║     ██████╔╝███████║   ██║   ██║██║
  ╚════██║██║   ██║██║     ██╔══██╗██╔══██║   ██║   ██║██║
  ███████║╚██████╔╝╚██████╗██║  ██║██║  ██║   ██║   ██║╚██████╗
  ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝
                              L E A R N

  objective → prerequisites → guided route → application → evidence
```

**A portable, evidence-aware Socratic protocol for learning any subject.**

Socratic Learn gives compatible AI agents a clear method for helping people
learn any subject. First, define what the learner should be able to do. Then
check only the knowledge they need, preview the shortest useful route, and ask
them to apply what they learned before calling it progress.

It is a protocol and distribution toolkit. It is not an AI model or chat
application, and it does not claim that questions alone guarantee learning.

## Why I built this

I built Socratic Learn out of a recurring need in my work as an AI researcher.
I often need to learn new theory, tools, and related fields quickly without
mistaking a fluent explanation for real understanding.

The project turns that need into a portable protocol. It asks for clear
outcomes, adapts to what the learner already knows, and uses application as
evidence. It supports any subject or skill. Mathematics and AI are starter
curricula and rigorous examples, not product boundaries.

## The method in 60 seconds

1. **Define the outcome.** Turn “I want to learn X” into something the learner
   can explain, derive, predict, implement, or diagnose.
2. **Find the starting point.** Check only prerequisites that could block that
   outcome.
3. **Preview the route.** Briefly explain what comes first and why, start
   teaching automatically, and let the learner redirect at any time.
4. **Teach adaptively.** Ask when the learner can work out the next step.
   Explain information they cannot work out yet. Then ask them to use it.
5. **Require evidence.** Finish only after the learner applies the idea in the
   original task or a new one. Record what was established, what remains,
   sources, and one next step.

`objective → prerequisites → guided route → application → evidence`

## A compact example

```text
Learner  → I want to understand why attention scales by √dₖ.
Tutor    → What observable result should you be able to derive or predict?
Learner  → I want to derive the scaling and predict what changes without it.
Tutor    → I'll check the starting point first: compare the variance of one
           dot-product term with the variance of a sum of dₖ independent terms.
           I'll use your answer to set the route. You can redirect me at any time.
...
Evidence → The learner derives the variance growth, explains the softmax
           consequence, and transfers the reasoning to a changed dimension.
```

When the learner can reasonably work out the next step, Socratic Learn asks.
When the learner cannot work out the information yet, it explains directly
and then asks the learner to use it.

## How the system is structured

The learning behavior lives in four main documents:

- [pedagogy](core/pedagogy.md): connected ideas, clear reasons for each step,
  responsive dialogue, and active practice.
- [session protocol](core/session-protocol.md): clear outcomes, focused checks,
  tutor-led route selection, a short route preview, and a saved session record.
- [assessment](core/assessment.md): finding what the learner knows and where
  the gap begins.
- [evidence policy](core/evidence-policy.md): types of mathematical claims,
  source priorities, checks for information that can change, and clear
  uncertainty.

The `socratic` launcher delivers one deterministic prompt bundle to Pi, Claude
Code, or Antigravity. Hosts provide the model, authentication, and terminal.
Socratic Learn provides the method and private learning workspace. Cursor and
the project adapters expose the same protocol through project discovery.

## Research foundations

These studies informed design decisions. They do **not** validate Socratic
Learn itself:

- Clear objectives and short active tasks alongside Socratic dialogue:
  [Mahoney et al. (2023)](https://doi.org/10.1016/j.tsc.2023.101422).
- Guidance that adapts to learner behavior:
  [Munshi et al. (2023)](https://doi.org/10.1111/jcal.12761).
- More guidance when the strategy is new:
  [Borchers et al. (2025)](https://doi.org/10.1016/j.compedu.2025.105364).
- Recall of upcoming steps before worked-example feedback:
  [van den Broek et al. (2025)](https://doi.org/10.1016/j.learninstruc.2025.102196).
- Guidance, worked examples, learning from failed attempts, and transfer to
  new tasks:
  [Stogniy et al. (2020)](https://doi.org/10.1096/fasebj.2020.34.s1.04148).
- Recent and promising evidence from GenAI-supported Socratic assessment:
  [Lee et al. (2025)](https://doi.org/10.48550/arXiv.2509.16262).

The AI-specific evidence is recent, and the cited studies examine their own
groups and teaching methods, not this repository. They justify careful
evaluation, not an effectiveness claim.

## Engineering evidence

- **Deterministic distribution:** canonical Markdown builds a versioned prompt
  bundle and manifest with reproducible hashes.
- **Portable runtime:** standard-library Python 3.11+ with native and pipx
  distribution paths.
- **Safe installation:** ownership receipts, no-overwrite
  publication, rollback, and explicit recovery artifacts.
- **Private by default:** learner records and raw semantic evidence are ignored
  and excluded from published packages.
- **Host isolation:** semantic evaluation uses external temporary home
  directories and separate working directories, sanitized tracked reports,
  and strict cleanup checks.
- **Safety and edge-case tests:** symlink, race, timeout, inherited-pipe,
  malformed stream, package-exclusion, and cross-platform safety coverage.

See the [CI workflow](.github/workflows/native-python.yml), [manifest
reference](docs/manifest-reference.md), and [semantic baseline
report](evaluation/reports/2026-11-06-antigravity-baseline.md).

## Evaluation status

The first semantic baseline tried three unchanged-protocol Antigravity sessions,
one each for conceptual physics, practical programming, and
communication writing. All three stopped before a learner response because
Antigravity headless mode denied the same workspace-inspection command.

Because no learner could respond, no pedagogy score was assigned. Socratic
Learn does not convert runtime failure, engagement, or self-reported
confidence into evidence of learning. The sanitized result is tracked in the [baseline
report](evaluation/reports/2026-11-06-antigravity-baseline.md). Raw streams
remain private and untracked.

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
SmartScreen or macOS Gatekeeper warnings. A checksum verifies downloaded
bytes. It is not a substitute for code signing. This documentation does not
claim that a public release or tag already exists.

The x86-64 native build is the preferred one-time installation method. For
other architectures, or if you prefer a Python-managed environment, use Python
3.11+ and pipx after package publication. The pipx command is available only
after socratic-learn 0.1.0 is published on PyPI.

```text
pipx install socratic-learn
```

Start the launcher without a goal:

```text
socratic
```

It detects Pi, Claude Code, and Antigravity, asks you to select an available
launcher host on first use, and remembers that selection. Starting without a
goal is the privacy default because it avoids putting the learning goal in
shell history. Socratic Learn does not store provider credentials. The
selected host uses its own authentication.

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

## Supported hosts and project adapters

The launcher is the normal user path. Project adapters are separate:
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

Installation files are stored under `.socratic-learn/`. Existing agent paths
are never merged or overwritten automatically.

Pi, Claude Code, and Antigravity are launcher hosts: they provide the model,
authentication, and terminal. Cursor remains a project integration, alongside
the Generic, Claude Code, and Pi project-discovery adapters. Capability
fallbacks keep the method usable when a host lacks web search, structured
quizzes, rendering, subagents, persistent memory, or filesystem access.

### Launcher lifecycle

Native installs update their own verified executable. Pipx installs do not
change their environment. These commands print the matching pipx instruction.
Uninstall preserves learner data unless deletion is explicitly requested and
confirmed.

```text
socratic update
socratic uninstall
```

For pipx, the matching commands are `pipx upgrade socratic-learn` and
`pipx uninstall socratic-learn`. See the [installation
guide](docs/universal-installation.md), [launcher adapter
contract](docs/launcher-adapters.md), [manifest
reference](docs/manifest-reference.md), and [adapter extension
guide](docs/adding-an-adapter.md).

Contributor-only commands (`build`, `export`, project `install`, and
`doctor`) are for contributors and project integrations. There is no `--force`
option.

## Privacy, security, and limitations

### Private learner state

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
[workspace.example](workspace.example/) is made up and safe to copy.

### Security and recovery

Socratic Learn protects against ordinary collisions, accidental concurrent
changes, and cooperating Socratic Learn processes. Controls include atomic
no-replace publication, parent-directory bindings, identity rechecks,
exact-topology cleanup, recovery artifacts, and Windows handle-bound
operations.

If publication becomes ambiguous, the tool preserves partial paths, staging,
and backups and reports manual recovery steps. It does not knowingly overwrite
modified or unowned files.

On POSIX systems, the threat model does not cover hostile or uncooperative
processes running as the same OS user. The `rename`, `unlink`, and `rmdir`
system calls cannot tie a final path change to an inode that is already open.
This leaves a final-path TOCTOU race that cannot be removed completely.

### Migrating from Learning Tutor

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

### Limitations

Socratic Learn does not provide an AI model, chat interface, quiz engine,
search provider, rendering service, persistent memory service, or agent
runtime. Those capabilities belong to the selected host. The protocol defines
fallbacks. It cannot create tools the selected host does not provide.

The bundled mathematics and AI maps are starter curricula, not the boundary
of the protocol and not complete courses. For another subject or skill, the
agent constructs the smallest relevant dependency path from the learner's
goal and available evidence.

Universal protocol scope does not mean universal host knowledge. Reliability
still depends on the selected model, available sources and tools, and the
quality of evidence produced during the session. Socratic Learn does not
guarantee mastery.

Support means the four installation and discovery paths satisfy this
repository's contract. It does not verify every model or guarantee identical
interpretation.

## Development and documentation

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
protected content boundaries, workspace privacy, manifests, generated
artifacts, README contracts, and deterministic rebuilds.

The [native CI workflow](.github/workflows/native-python.yml) runs build,
tests, validation, and install/update/doctor smoke checks on Python 3.11 for
Windows, Ubuntu, and macOS.

Documentation:

- [installation guide](docs/universal-installation.md)
- [launcher adapter contract](docs/launcher-adapters.md)
- [manifest reference](docs/manifest-reference.md)
- [adapter extension guide](docs/adding-an-adapter.md)
- [Cursor adapter README](adapters/cursor/README.md)
- [Claude Code adapter README](adapters/claude-code/README.md)
- [Pi adapter README](adapters/pi/README.md)

## License

Socratic Learn is available under the [MIT License](LICENSE).
