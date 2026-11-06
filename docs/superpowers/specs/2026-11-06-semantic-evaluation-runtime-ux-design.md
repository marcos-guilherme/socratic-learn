# Semantic Learning Evaluation and Runtime UX Design

**Status:** Approved in conversation on 2026-11-06  
**Scope:** Evidence-led semantic evaluation, adaptive pedagogy, launcher commands,
runtime terminology, and runtime documentation  
**Baseline runtime:** Antigravity only

## Context

Socratic Learn can launch Pi, Claude Code, or Antigravity, but its current
interface calls all three choices "agents." That label hides an important
distinction:

- Socratic Learn supplies the learning protocol.
- A runtime hosts the session and supplies terminal behavior.
- A model performs inference inside the selected runtime.

Pi is a configurable terminal harness, Claude Code is an agent CLI, and
Antigravity is a broader agentic environment. They are different products that
share one role in Socratic Learn: executing a learning session.

The first real Pi session also exposed two usability problems. The selected
runtime was persisted without an intuitive command for changing it, and a
Gemini quota failure appeared as a large provider error after the launcher had
successfully loaded the protocol. The failure belonged to Pi's selected model,
not to Socratic Learn, but the product did not make that boundary sufficiently
clear.

This design uses real learner simulations to establish a baseline before
changing behavior. Findings may change the canonical pedagogy, launcher, and
documentation when the change is supported by both observed evidence and
learning research.

## Goals

1. Evaluate whether the protocol teaches effectively across conceptual,
   procedural, and non-technical learning.
2. Distinguish pedagogy failures from runtime, authentication, quota, network,
   and model failures.
3. Replace ambiguous agent terminology with runtime terminology in the public
   launcher experience.
4. Provide intuitive commands for starting a session, inspecting runtimes,
   changing the default, configuring the launcher, and diagnosing setup.
5. Explain Pi thoroughly, including its relationship to providers, models,
   local inference, free tiers, and quota limits.
6. Preserve a short `socratic` path while adding explicit discoverable
   commands.
7. Convert observed semantic failures into deterministic regression coverage
   where possible.

## Non-goals

- Building or embedding a model runtime.
- Normalizing model selection across Pi, Claude Code, and Antigravity.
- Reading, storing, validating, or modifying provider credentials.
- Claiming that a detected runtime has working authentication or quota.
- Running live semantic evaluations in ordinary CI.
- Exposing semantic evaluation as a public end-user command.
- Evaluating Pi or Claude Code semantically in this first round.
- Publishing raw provider transcripts or private learner records.

## Evidence basis

The design treats Socratic teaching as adaptive guided instruction, not as a
sequence of questions at all costs.

The evidence reviewed for this design supports these principles:

1. Socratic dialogue benefits from explicit learning objectives and short,
   active assignments.
2. Scaffolds should respond to meaningful learner inflection points and current
   proficiency. Strategic hints are more useful than generic encouragement.
3. Novices often need high scaffolding, direct explanation, and worked
   examples before independent problem solving.
4. Unguided or weakly guided inquiry can underperform scaffolded guidance.
5. Asking learners to retrieve or predict a step before revealing it can
   improve delayed recall and problem solving.
6. Engagement and self-report are not sufficient evidence of learning.

The intended instructional sequence is:

```text
observable outcome
→ relevant diagnosis
→ reachable question
→ strategic hint
→ explanation or worked example when needed
→ retrieval
→ application
→ transfer
```

The protocol must avoid two symmetric failures:

- **Socratic interrogation:** repeated questions when the learner lacks the
  foundation needed to discover the answer.
- **Premature lecture:** explanation before the learner has an appropriate
  opportunity to retrieve, predict, reason, or apply.

### Research references

- Mahoney et al. (2023), [Learning to think critically through Socratic
  dialogue](https://consensus.app/papers/details/0adf25e68b4d552aa18c5d2ea631170e/?utm_source=cursor)
- Munshi et al. (2022), [Analysing adaptive scaffolds that help students
  develop self-regulated learning
  behaviours](https://consensus.app/papers/details/779761ae76575793a1f13ff9502ee816/?utm_source=cursor)
- Borchers et al. (2025), [High scaffolding of an unfamiliar strategy improves
  conceptual
  learning](https://consensus.app/papers/details/a51cac61d84156638d67764eeadcc18b/?utm_source=cursor)
- van den Broek et al. (2025), [Retrieval Practice in Stepwise Worked Examples
  Improves
  Learning](https://consensus.app/papers/details/af8af3ac1bde5b5792569dcb8341ff99/?utm_source=cursor)
- Stogniy et al. (2020), [Comparing the Impacts of Evidence-Based
  Pedagogies](https://consensus.app/papers/details/0cb2208439095e43acfd7e71c4619110/?utm_source=cursor)
- Lee et al. (2025), [Socratic Mind: Impact of a Novel GenAI-Powered Assessment
  Tool](https://consensus.app/papers/details/892841916b2f5030b1f42ccda3ff0adc/?utm_source=cursor)

The AI-specific evidence is promising but recent. It supports testing the
design; it does not justify assuming effectiveness without observable learner
performance.

## Terminology

The public interface and documentation use these terms consistently:

- **Protocol:** Socratic Learn's pedagogical instructions and records.
- **Runtime:** the installed environment that runs the session: Pi, Claude
  Code, or Antigravity.
- **Model:** the inference model selected within a runtime.
- **Provider:** the service or local backend that makes a model available.
- **Learner workspace:** the isolated files containing goals, profile,
  progress, and session records.

`agent` remains only as a temporary compatibility term for the old `--agent`
flag and schema-one configuration.

## Semantic evaluation architecture

### Evaluation method

The evaluator performs an adaptive transcript audit. It plays a predefined
learner persona but chooses each learner response after reading the tutor's
actual response. The evaluator must remain faithful to the persona's declared
knowledge, misconception, communication style, and allowed learning progress.
It must not leak the hidden target answer merely to help the tutor pass.

This method is preferred over a fully fixed script because it remains coherent
when the tutor takes an unexpected path. It is preferred over another model
playing the learner because it does not add a second model's cooperation,
knowledge, or bias as an uncontrolled variable.

### Runtime and isolation

The first evaluation round uses Antigravity only. Each scenario receives:

- a separate external ephemeral Socratic Learn home outside the repository;
- a separate external ephemeral working directory outside the repository;
- the same explicit Antigravity model;
- the same protocol version;
- inherited Antigravity authentication without credential inspection;
- sandboxed execution where supported;
- a hard maximum of 15 learner responses.

The runtime home and working directory never live inside the repository,
because runtimes discover rule files in ancestor directories and the
repository's own agent rules would contaminate the tutor. Before launch, the
driver rejects any repository or local rule marker (`AGENTS.md`, `GEMINI.md`,
`CLAUDE.md`, `.agents/`, `.agent/`) found in the working directory or any of
its ancestors below the user-home boundary.

When the working directory is not below the user home, the check covers every
ancestor up to the filesystem root.

User-level runtime rules at or above the user-home boundary remain inherited
together with authentication; the driver does not replace `HOME` or
`USERPROFILE` and never reads rule contents or credentials. Using existence
checks only (`lexists`, without opening, listing, or resolving links), it
records two separate name-only disclosures:

- user-home-relative rule paths that are present: `AGENTS.md`, `GEMINI.md`,
  `CLAUDE.md`, `.agents/`, `.agent/`, and `.gemini/GEMINI.md`;
- ancestor markers above the user home, up to the filesystem root, recorded
  as the marker name and its number of levels above the home, never as a
  path.

The run's private runtime context also records that the local rule check
passed and which boundary it used. The report lists both disclosures per
scenario as an evaluation limitation.

Raw streams, runtime logs, provider metadata, and evaluator notes remain under
the repository's ignored `.semantic-runs/`. The external home and working
directory are deleted after the private run record and raw streams needed for
scoring are saved, including after failed sessions.

The evaluation driver uses Antigravity headless structured-streaming mode with
stream-json input and output. It uses the installed CLI contract without the
interactive `--print PROMPT` option. It delivers the same canonical protocol
and initial goal as the interactive launcher. A separate launcher smoke test verifies that the
public `socratic` command prepares the same protocol and workspace.

The structured driver exists only for development evaluation. It is not
installed as a public `socratic` subcommand.

### Scenario 1: conceptual physics

**Persona:** A novice who has everyday experience but no formal mechanics.

**Initial misconception:** A heavier object falls faster than a lighter object
because gravity pulls harder on it.

**Observable outcome:** Ignoring air resistance, the learner predicts equal
acceleration for objects with different masses, explains why greater force
does not imply greater acceleration in this comparison, and applies the idea
to a new pair of objects.

**Learner behavior:** The learner initially defends the misconception, can
reason about familiar examples, says when an equation or term is unfamiliar,
and asks for a direct explanation after two unproductive hints.

### Scenario 2: practical programming

**Persona:** A beginner who understands variables, `for` loops, and basic
functions but has not internalized exclusive range bounds.

**Initial task:**

```python
def sum_first_n(n):
    total = 0
    for value in range(1, n):
        total += value
    return total
```

**Observable outcome:** The learner traces the function for a concrete input,
identifies why `n` is excluded, corrects the bound, explains the rule, and
applies it to a different loop without copying the answer.

**Learner behavior:** The learner guesses once, can execute a short trace with
support, confuses the number of iterations with the final included value, and
expects specific feedback rather than a replacement solution.

### Scenario 3: communication writing

**Persona:** A professional who writes complete but long and defensive
messages.

**Initial task:** Rewrite a verbose message about a missed dependency into a
concise, respectful request for deadline clarification.

**Observable outcome:** The learner produces a message with a clear purpose,
necessary context, concrete request, neutral tone, and appropriate brevity,
then explains how audience and purpose shaped the revision.

**Learner behavior:** The learner initially believes removing detail will make
the message rude or unsafe, overexplains once after feedback, and can compare
two candidate phrasings.

### Stop conditions

A session stops at the first applicable condition:

1. the learner demonstrates the full observable outcome;
2. the learner has sent 15 responses;
3. the tutor claims completion without collecting the required evidence;
4. a critical pedagogical failure makes further dialogue invalid;
5. authentication, quota, network, runtime, or timeout failure prevents the
   session from continuing.

Condition 5 is an infrastructure result, not a pedagogy score.

## Semantic rubric

Each category receives 0, 1, or 2:

- **0:** absent, inappropriate, or harmful;
- **1:** present but partial, late, generic, or inconsistent;
- **2:** clear, timely, learner-specific, and effective.

The eight categories are:

1. observable outcome definition;
2. relevant prerequisite diagnosis;
3. question difficulty calibrated to demonstrated knowledge;
4. adaptive transition among question, hint, explanation, and example;
5. retrieval or prediction after support;
6. application and transfer evidence;
7. specific corrective feedback;
8. evidence-based closure and record.

The maximum score is 16.

Critical failures are recorded independently:

- persistent questioning despite missing foundations;
- delivering an extended explanation before any appropriate learner attempt;
- accepting confidence or self-report as mastery;
- teaching materially incorrect content;
- claiming completion without application evidence;
- violating an explicit approval gate;
- fabricating a source or learner record.

The post-change target for every scenario is:

- no critical failure;
- at least 12 of 16;
- no category scored zero;
- aggregate score not lower than the baseline aggregate.

A category regression or inconsistent result triggers one labeled rerun and a
written analysis. Stochastic output is not hidden by averaging arbitrary
repetitions.

## Evidence storage

Tracked, fictitious evaluation assets live under a dedicated evaluation
directory and include:

- scenario definitions;
- persona rules;
- rubric definitions;
- deterministic transcript parser tests;
- sanitized evaluation reports.

Raw structured transcripts, provider metadata, runtime logs, and evaluator
notes live under `.semantic-runs/`, which is ignored by Git. Temporary learner
homes and working directories live outside the repository and are deleted
once the private run record is saved.

A sanitized report may quote only the minimum turns needed to justify a score.
It records:

- date and run identifier;
- repository commit and protocol version;
- runtime and model identifier;
- scenario and stop condition;
- category scores and evidence;
- critical failures;
- infrastructure failures;
- findings that are general versus scenario-specific.

No real learner profile, provider credential, token, or unrelated local path
may enter a tracked report.

## Baseline and change loop

The work proceeds in this order:

1. run the three baseline sessions against the unchanged protocol;
2. score them and produce a sanitized findings report;
3. classify each finding as pedagogy, launcher UX, documentation, runtime, or
   infrastructure;
4. propose changes linked to observed transcript evidence and research;
5. implement deterministic tests before each behavior change;
6. update protocol, launcher, and documentation within the approved scope;
7. run existing unit, validator, packaging, and native smoke tests;
8. repeat the same three semantic scenarios with the same runtime and model;
9. compare results and document regressions, improvements, and unresolved
   uncertainty.

A protocol change is accepted only when it:

- addresses an observed generalizable problem;
- agrees with the evidence basis;
- does not encode the answer to one scenario;
- preserves deterministic repository invariants;
- meets the post-change semantic target or has an explicitly documented
  unresolved limitation.

## Public command design

### Command surface

The public command surface becomes:

```text
socratic
socratic start [--runtime RUNTIME] [--here] [GOAL...]
socratic runtimes
socratic use RUNTIME
socratic config
socratic doctor
socratic project doctor
socratic update
socratic uninstall
```

Behavior:

- `socratic` remains the shortest start command. With a saved, available
  runtime it prompts privately for the goal and starts the session.
- `socratic start` is the explicit discoverable equivalent.
- `socratic runtimes` lists supported runtimes, detection status, executable
  location, short description, and current default.
- `socratic use RUNTIME` validates that the runtime is detected and saves it
  as the default.
- `socratic config` opens an interactive configuration flow. In this scope it
  manages only non-secret Socratic Learn preferences.
- `socratic doctor` diagnoses launcher installation and configuration without
  invoking a model.
- `socratic project doctor` runs the existing project-installation
  diagnostics.
- `--runtime RUNTIME` overrides the saved default for one session and does not
  mutate configuration.

The launcher continues to accept a direct goal for convenience, with the
documented warning that shell history may retain it.

### First-run selection

The first-run prompt is:

```text
Where should Socratic Learn run this session?

1. Antigravity — full agentic environment
2. Pi — terminal harness; configure its provider and model separately
3. Claude Code — Anthropic's agent CLI
```

Only detected runtimes are selectable. The display order remains deterministic
and is not a claim that the products belong to the same architectural
category.

### Configuration migration

Configuration schema two uses:

```json
{
  "schema_version": 2,
  "default_runtime": "pi"
}
```

The loader accepts the current schema-one `default_agent` document and maps it
to `default_runtime` in memory. The next explicit configuration write publishes
schema two atomically. Unknown keys, invalid runtimes, malformed JSON, symlinks,
and unsupported schemas remain fail-closed.

Internal launcher symbols and messages that represent Pi, Claude Code, or
Antigravity move from agent or host wording to runtime terminology. This is a
source-level naming migration, not a new runtime abstraction over models.

### Compatibility

- Bare `socratic [GOAL...]` remains supported.
- `--agent` remains a deprecated alias for `--runtime` for one compatibility
  cycle and prints a concise warning to stderr.
- Existing schema-one configuration remains readable.
- `python -m socratic_learn` administrative commands remain available.
- `socratic doctor` becomes launcher diagnostics.
- Project-installation diagnostics remain available through
  `python -m socratic_learn doctor` and receive a namespaced
  `socratic project doctor` alias.

No compatibility alias may silently change the saved default.

## Runtime diagnostics

`socratic doctor` checks:

- installed package version and launcher executable;
- whether the launcher scripts directory is reachable through `PATH`;
- launcher home accessibility and configuration integrity;
- detected runtime executable paths;
- whether the saved default is still detected;
- canonical protocol resource availability;
- personal workspace health.

It does not:

- read runtime credential stores;
- print API keys or tokens;
- invoke a provider model;
- consume quota;
- claim that runtime authentication, billing, or model access works.

When an executable is detected but model access later fails, documentation
must identify the boundary and provide runtime-specific next actions.

## Error behavior

Errors use plain language and separate Socratic Learn responsibility from
runtime/provider responsibility.

Examples:

```text
Pi was launched and loaded the Socratic Learn protocol, but its selected
provider rejected the model request. In Pi, use /model to select another model
or /login to configure a provider.
```

```text
The saved runtime 'claude' is not currently available.
Run 'socratic runtimes' to inspect detected runtimes or
'socratic use RUNTIME' to choose another default.
```

The launcher returns the child process exit status. It must not parse arbitrary
provider output to guess billing state. Runtime-specific troubleshooting is
documentation and static guidance for known error classes, not credential
introspection.

## Documentation design

The README explains the shortest successful path, then links to:

- a runtime/model/protocol conceptual guide;
- a runtime comparison;
- Pi, Claude Code, and Antigravity runtime guides;
- launcher configuration and diagnostics;
- troubleshooting.

The Pi guide must explain:

- Pi is a terminal harness, not a model;
- installation and executable detection;
- provider authentication with `/login`;
- model selection with `/model` or its current equivalent;
- local inference through llama.cpp;
- free cloud tiers and their quota limitations;
- common 429 quota failures;
- exact Socratic Learn prompt delivery;
- inherited permissions, tools, and session behavior;
- how to change away from Pi in Socratic Learn.

The Antigravity and Claude Code guides use the same structure so Pi is not
presented as the only runtime with operational details.

Documentation must not promise that a cloud model is free, available, or
unlimited. It may describe current provider mechanisms while clearly assigning
authentication, model catalogs, pricing, and quota to the runtime/provider.

## Deterministic testing

Ordinary automated tests cover:

- command parsing and help text;
- bare-start and explicit-start equivalence;
- `runtimes`, `use`, `config`, `doctor`, and `project doctor`;
- one-shot runtime override without configuration mutation;
- schema-one to schema-two migration;
- deprecated `--agent` behavior;
- runtime descriptions and deterministic ordering;
- launcher diagnostics without network or credential access;
- error messages for missing and stale runtimes;
- documentation command examples;
- packaged resource and native build parity.

Semantic tests are not ordinary CI gates because model output, provider
availability, latency, and quota are nondeterministic. CI validates the
scenario schema, rubric, transcript parser, sanitization, and report structure
using synthetic transcripts.

Every semantic failure that can be expressed as a deterministic protocol or
launcher invariant should gain a focused regression test before its fix.

## Acceptance criteria

This work is complete when:

1. three baseline Antigravity sessions and a sanitized report exist;
2. findings are linked to transcript evidence and, for pedagogy changes, the
   evidence basis;
3. the approved command surface is implemented with compatibility behavior;
4. runtime, model, and protocol are clearly distinguished throughout public
   output and documentation;
5. Pi, Antigravity, and Claude Code each have an operational runtime guide;
6. protocol changes have deterministic regression coverage;
7. all existing repository validation, unit, package, native, and hosted CI
   gates pass;
8. the three post-change sessions meet the semantic target or document an
   explicit unresolved limitation;
9. raw transcripts and private learner data remain untracked;
10. no release, tag, or package publication occurs without separate explicit
    approval.
