# Launcher Adapters

Launcher adapters connect the installed `socratic` console to an interactive
agent executable. They are not project-discovery adapters: they start a host
process for a learning session rather than placing host-specific files in an
existing repository.

## Current hosts

Host selection follows this executable detection order:

1. Pi: detect `pi`.
2. Claude Code: detect `claude`.
3. Antigravity: detect `agy`.

An explicit `--agent` selection must be detected. Otherwise the launcher uses
the saved default if it is still available, or asks the learner to choose and
saves the result in `~/.socratic-learn/config.json`.

## Exact command construction

The launcher passes an argument vector directly to the child process; it does
not interpolate a shell command.

- Pi: `pi --append-system-prompt PROTOCOL GOAL`
- Claude Code: `claude --append-system-prompt-file PROTOCOL GOAL`
- Antigravity: `agy --prompt-interactive BOOTSTRAP`

For Antigravity, `BOOTSTRAP` is exactly:

```text
Before responding, read and follow the Socratic Learn protocol at PROTOCOL. The learner's initial objective is: GOAL
```

`PROTOCOL` is the absolute path to the prepared
`.socratic-learn/socratic-learn.prompt.md`. `GOAL` is delivered as one argument,
including spaces and non-ASCII text. Every launcher adapter must provide
protocol delivery before the host responds to the learning goal.

## Host-owned behavior

The child inherits authentication from the selected host; Socratic Learn does
not read or store provider credentials. It also inherits terminal input,
output, permissions, environment, and host-specific model selection. The
launcher runs the child in the prepared personal or `--here` workspace and
returns the child's exit status.

## Adding a launcher host

A new launcher adapter must define:

- its stable public agent name and executable detection names;
- exact command construction as an argument vector;
- how the full protocol path and exact initial goal are delivered;
- any host limitation that changes interactive terminal behavior.

Tests must use a fake executable found through an isolated `PATH`; no provider
account or network request belongs in the release gate. Required tests cover
detection, exact arguments, protocol delivery, working directory, Unicode and
spaces, saved-default reuse, explicit override, inherited exit status, and no
mutation outside the isolated home and test directory.

For project-local discovery files instead, follow
[Adding an Adapter](adding-an-adapter.md).
