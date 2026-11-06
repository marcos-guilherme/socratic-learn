# One-Command Learning Launcher — Design

## Goal

Make Socratic Learn usable from any terminal through one memorable command:

```text
socratic
```

The command starts an interactive learning session by reusing a compatible
agent already installed and authenticated on the user's machine. Socratic
Learn remains model- and provider-independent: it does not operate its own
chat service, request API keys, or proxy model traffic.

## User experience

Running `socratic` without arguments asks:

```text
What do you want to learn?
```

The user can skip that question by supplying the goal directly:

```text
socratic "I want to learn linear algebra"
```

On the first run, the launcher detects compatible agents, asks the user to
choose one, and saves that choice. Later runs immediately use the saved agent.
The user can override it for one session:

```text
socratic --agent pi
socratic --agent claude
socratic --agent antigravity
```

The first launcher release supports Pi, Claude Code, and Antigravity. Their
installed command-line interfaces have been verified to support an initial
interactive prompt. Cursor remains supported through the existing
project-local integration, but it is not a launcher target until a suitable
terminal conversation interface is available.

By default, sessions use a private personal learning space under
`~/.socratic-learn/`. This avoids modifying whichever directory happens to be
active and allows the learner profile and progress to continue across
sessions. `socratic --here` instead uses the current directory when learning
depends on project files.

## Command compatibility

The package gains a standards-based `pyproject.toml` and a console entry point
named `socratic`. The default no-subcommand behavior launches learning.
Existing administrative operations remain available through the same entry
point, including `build`, `export`, `install`, and `doctor`.

The existing `python -m socratic_learn` interface remains compatible. Current
scripts, tests, and repository maintenance workflows must not require an
immediate migration. In particular, invoking the module without a subcommand
continues to return its current usage error; only the new `socratic` console
entry point launches learning by default.

Administrative command names are reserved when they are the first argument.
The explicit form `socratic learn "GOAL"` is available when a learning goal
begins with one of those names.

## Architecture

The launcher core owns prompting, preference selection, workspace choice, and
process lifecycle. Each host adapter has three responsibilities:

1. detect whether its executable is available;
2. prepare the Socratic Learn protocol for that host;
3. construct and start the interactive process.

Adapters pass argument arrays directly to the operating system. They must not
construct shell command strings. Adding a future host must not require changes
to the common launch flow.

The launcher prepares the canonical protocol through the safest
host-supported mechanism. It may use a system-prompt file, a host discovery
file in the managed workspace, or a short bootstrap instruction that points
to the managed protocol. Adapter acceptance tests must demonstrate that the
host is launched with both the protocol and the learner's goal; command-line
support alone is not sufficient.

The configuration file at `~/.socratic-learn/config.json` stores only
non-secret preferences such as the default agent. It never stores provider
tokens or model credentials. Configuration and managed learning files use
atomic writes.

In personal mode, the launcher creates and maintains the required profile,
progress, session, and protocol files under `~/.socratic-learn/`. In
`--here` mode, it reuses the existing transactional installer and ownership
receipts. It must preserve the current collision and no-overwrite guarantees.

## Process and error behavior

The child agent inherits the interactive terminal so its normal interface,
authentication flow, permissions, and model selection continue to work.
Interrupts such as `Ctrl+C` are forwarded correctly. The launcher returns the
agent's exit status.

Errors identify the failed operation and a direct remediation:

- no compatible agent found: list supported agents and installation links;
- saved agent no longer installed: offer another detected agent;
- agent authentication required: preserve and explain the host's failure;
- project installation conflict: report the owned or conflicting path without
  overwriting it;
- corrupt configuration: preserve the file, explain how to recover, and do
  not silently discard preferences;
- launch failure: include the host name and executable path without exposing
  credentials.

Supplying a goal as a command argument is convenient but may leave that text
in shell history. The interactive no-argument flow is the privacy-preserving
default and the documentation must state this distinction.

## Distribution

The primary distribution is a standalone executable for Windows, macOS, and
Linux. A platform installer downloads the correct release, verifies its
SHA-256 digest, installs it in a user-owned directory, and makes `socratic`
available on `PATH`. Installation must not require administrator access.

The same release is also published as a Python package so developers can use:

```text
pipx install socratic-learn
```

The first native releases may be unsigned. Download pages and installers must
clearly disclose possible Windows SmartScreen and macOS Gatekeeper warnings.
Checksums establish artifact integrity but are not represented as a
substitute for platform code signing. Signing and notarization can be added
when the required developer accounts and certificates are available.

`socratic update` downloads and verifies a release before atomically replacing
the installed executable. An interrupted or failed update leaves the previous
version usable. `socratic uninstall` removes the installed program but
preserves learner data by default. Deleting learner data requires an explicit
option and confirmation.

Update and uninstall behavior is installation-channel-aware. Native installs
record enough non-secret metadata to manage their own executable. A PyPI
installation never attempts to overwrite its environment; it reports the
exact `pipx upgrade` or `pipx uninstall` command instead.

Native artifacts are built from the Python package with PyInstaller unless
implementation research identifies a concrete incompatibility. Release
automation produces a manifest containing version, platform, artifact name,
size, and SHA-256 digest.

## Validation

Most launcher tests use fake agent executables so CI does not require external
accounts or model traffic. Coverage includes:

- agent detection, first-run selection, and saved preference reuse;
- explicit agent overrides and a missing saved agent;
- personal and `--here` workspace behavior;
- protocol and initial-goal delivery for every adapter;
- paths and goals containing spaces and non-ASCII text;
- interrupt forwarding and child exit-code propagation;
- configuration corruption and atomic recovery behavior;
- artifact checksum verification, update rollback, and uninstall data
  preservation;
- package installation and standalone executable smoke tests.

CI runs on Windows, Ubuntu, and macOS. Authenticated live-agent checks are
optional smoke tests, not release gates. Existing deterministic build,
installation, migration, doctor, and repository validation suites remain
release gates.

## Acceptance criteria

The initiative is complete when:

- a new user can install Socratic Learn without cloning the repository;
- `socratic` starts an interactive learning session through a detected agent;
- the first-run agent choice is remembered and can be overridden;
- Pi, Claude Code, and Antigravity satisfy the adapter contract;
- personal learning state persists without modifying the current directory;
- `--here` preserves all existing transactional installation guarantees;
- no Socratic Learn component stores model-provider credentials;
- native downloads are hash-verified and failed updates roll back safely;
- Python-package and native installation paths are documented;
- local tests and hosted Windows, Ubuntu, and macOS validation pass.
