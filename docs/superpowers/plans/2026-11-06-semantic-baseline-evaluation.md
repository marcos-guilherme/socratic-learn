# Semantic Baseline Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private, development-only semantic evaluation system and use it to run exactly one unchanged-protocol Antigravity baseline session for each of the conceptual physics, practical programming, and communication-writing scenarios, producing a tracked sanitized evidence report.

**Architecture:** Keep all evaluation implementation and fictitious fixtures in the repository-root `evaluation/` package, which is importable from a checkout but excluded from published wheels, source distributions, and native executables. A contract-capture gate records Antigravity's observed stream-json envelope and one explicit available model before the adapter is implemented; isolated sessions then reuse the public launcher's exact Antigravity bootstrap with an ephemeral home and working directory outside the repository, while storing every raw event under the repository's ignored `.semantic-runs/`. The implementing agent is the only adaptive learner evaluator: it reads each tutor turn, responds faithfully to the scenario persona, chooses stop reasons, and scores evidence through a console workflow without delegating the learner role to another model.

**Tech Stack:** Python 3.11+ standard library, `unittest`, newline-delimited JSON, existing `socratic_learn` resource/workspace/host interfaces, Antigravity CLI headless structured-streaming mode with stream-json input and output (no `--print`, no `--mode`).

## Global Constraints

- Work only on branch `feat/semantic-evaluation-runtime-ux`.
- This plan is the independently testable baseline-evaluation subproject; it does not implement protocol, launcher UX, runtime terminology, or public documentation changes.
- Do not modify `core/*.md`, `dist/socratic-learn.prompt.md`, `dist/manifest.json`, public launcher behavior, runtime documentation, or any protocol byte.
- The evaluation implementation lives under repository-root `evaluation/`, outside `socratic_learn`, `learning_tutor`, and every published package.
- Semantic evaluation remains a private development workflow; it is not a `socratic` subcommand and does not run in ordinary CI.
- Use Antigravity only. Each live session must pass one explicit model identifier, and all three sessions must use the same identifier.
- Antigravity must run in headless structured-streaming mode with `--input-format stream-json`, `--output-format stream-json`, `--sandbox`, and a bounded print timeout. Never pass `--print` or `--mode`.
- Compatibility rationale (user decision, 2026-11-06): installed `agy 1.5.2` treats `--print` as an option that takes a prompt value, so it consumes the next flag as the prompt; the first-party headless documentation runs stream-json input without `--print`. `--mode auto` is unavailable for this account and unnecessary for stream-json. `--sandbox` stays.
- Do not infer or hard-code the unknown Antigravity stream-json envelope. Capture it from a successful installed-CLI probe, sanitize it, and commit the resulting adapter fixture before implementing parsing.
- Each scenario has a separate external ephemeral `SOCRATIC_LEARN_HOME` and working directory under an external runtime root outside the repository (live default: a fresh `tempfile.mkdtemp()` directory in the secure system temporary location). Preserve the parent environment so Antigravity inherits existing authentication without credential inspection.
- Runtime/raw split (user decision, 2026-11-06): the runtime home and cwd are always external; only raw evidence lives under the repository's ignored `.semantic-runs/{suite_id}/{scenario_id}/`. Runtimes discover rule files in cwd ancestors, so a cwd inside the repository would load the repository's own agent rules into the tutor.
- Before launch, reject repository/local rule markers (`AGENTS.md`, `GEMINI.md`, `CLAUDE.md`, `.agents/`, `.agent/`) in the cwd and every ancestor strictly below the user-home boundary. Do not reject user-home/global rule markers: they stay inherited with authentication, and only their names (never their contents) are recorded privately as an evaluation limitation.
- Delete each external home/cwd after the private run record and raw streams needed for scoring are saved, including on failure paths.
- Never pass `--dangerously-skip-permissions`, inspect credential stores, print environment values, or copy authentication material.
- The public-launcher-equivalent initial objective bootstrap does not consume the response budget. The hard cap is 15 adaptive learner responses after that bootstrap, and the runner must prevent response 16.
- The implementing agent acts as the adaptive learner. No model, subagent, scripted response generator, or second runtime may play the learner in live baselines.
- Raw transcripts, input envelopes, stderr, runtime logs, provider metadata, runtime-context records, learner-record snapshots, evaluator notes, and unsanitized scorecards live only under ignored `.semantic-runs/`. Temporary learner homes and working directories never live there; they are external and ephemeral.
- Never replace `HOME` or `USERPROFILE`, and never read the contents of any rule file or credential store.
- Tracked fixtures are fictitious and sanitized. The tracked baseline report contains only the minimum quoted turns required to justify scores.
- Infrastructure failures are recorded separately and never converted into pedagogy scores.
- The three baseline scenarios run once each under the unchanged protocol. Do not average arbitrary repetitions or silently rerun a scenario.
- Python tests may use scripted synthetic evaluators and fake Antigravity processes; those test doubles must not be usable by the live baseline command.
- Use standard-library code only; do not add a project dependency.
- Every commit in this plan is a local implementation checkpoint. Do not create a release, tag, package publication, GitHub Release, or PyPI publication.

---

## File Responsibilities

Create these focused development-only files before expanding any public surface:

- `evaluation/__init__.py`: marks the checkout-only evaluation package and exports no public product API.
- `evaluation/schema.py`: immutable scenario, rubric, stream-contract, run-record, scorecard, and finding types plus strict exact-key JSON loaders.
- `evaluation/sanitize.py`: recursive secret/path/identifier redaction and tracked-artifact privacy assertions.
- `evaluation/contract_capture.py`: records installed Antigravity help, model listing, one successful stream-json probe, and publishes the sanitized observed contract.
- `evaluation/parser.py`: JSON Pointer helpers and deterministic extraction of tutor text and turn-completion events from the captured contract.
- `evaluation/isolation.py`: creates one run layout that splits internal raw evidence (`.semantic-runs/{suite_id}/{scenario_id}/`) from an external ephemeral runtime home/cwd outside the repository, prepares the unchanged packaged protocol in the external working directory, rejects local rule-marker ancestors, discloses user-home-relative rule paths and above-home ancestor marker names only (existence checks, never contents), snapshots learner records without following links, and removes the per-run external runtime root.
- `evaluation/antigravity.py`: constructs the exact Antigravity argv, owns the persistent stream-json process, writes raw input/output/stderr, and returns parsed tutor turns.
- `evaluation/session.py`: applies the 15-message cap, stop conditions, manual evaluator console, immutable run-record persistence, and guaranteed external-runtime cleanup after records are saved.
- `evaluation/scoring.py`: validates eight rubric scores, critical failures, evidence turn references, finding classifications, and infrastructure outcomes.
- `evaluation/report.py`: renders and validates the sanitized Markdown baseline report.
- `evaluation/cli.py`: private `python -m evaluation.cli` entry point for contract capture, preflight, live baseline, scoring, report generation, and validation.
- `evaluation/fixtures/rubric.json`: exact eight-category rubric, score anchors, critical failures, and infrastructure classes.
- `evaluation/fixtures/scenarios/conceptual-physics.json`: fictitious novice mechanics persona and observable outcome.
- `evaluation/fixtures/scenarios/practical-programming.json`: fictitious beginner Python persona and range-bound outcome.
- `evaluation/fixtures/scenarios/communication-writing.json`: fictitious professional-writing persona and revision outcome.
- `evaluation/fixtures/antigravity/stream-contract.json`: generated, sanitized record of the actually observed Antigravity stream-json request and output contract.
- `evaluation/fixtures/synthetic/session.json`: deterministic fictitious transcript/run fixture used by parser, scoring, and report tests.
- `evaluation/reports/2026-11-06-antigravity-baseline.md`: generated sanitized evidence report from the three real baseline sessions.
- `tests/test_evaluation_schema.py`: strict schema and fixture validation.
- `tests/test_evaluation_contract.py`: contract capture and tracked fixture validation with a fake process boundary.
- `tests/test_evaluation_parser.py`: NDJSON and JSON Pointer behavior against the captured and synthetic fixtures.
- `tests/test_evaluation_sanitize.py`: recursive redaction and leak rejection.
- `tests/test_evaluation_isolation.py`: raw-path containment, external runtime placement, separate homes/directories, local rule-ancestor rejection, name-only user-home/above-home disclosure, runtime-context recording, link-safe snapshots, runtime cleanup, protocol identity, and inherited-environment behavior.
- `tests/test_evaluation_antigravity.py`: exact argv, persistent process, raw logging, timeout/error classification, and no learner-model behavior.
- `tests/test_evaluation_session.py`: manual evaluator flow, message cap, stop precedence, and run-record persistence.
- `tests/test_evaluation_report.py`: score validation, minimum evidence quoting, infrastructure separation, and deterministic report rendering.
- `tests/test_evaluation_privacy.py`: ignored raw storage, tracked-file privacy, package exclusion, and protocol immutability gates.

Modify only these existing non-product files:

- `.gitignore`: ignore the complete `/.semantic-runs/` tree.
- `tests/test_packaging.py`: prove wheels and source distributions exclude `evaluation/` and `.semantic-runs/`.
- `tests/validate_repository.py`: reject tracked raw semantic artifacts and require the private ignore boundary.
- `tests/test_validate_repository.py`: exercise the new repository privacy rules.

Do not add `evaluation/` to `pyproject.toml`, `socratic-learn.spec`, package data, console entry points, or release workflows.

---

### Task 1: Deterministic Scenario and Rubric Schemas

**Files:**
- Create: `evaluation/__init__.py`
- Create: `evaluation/schema.py`
- Create: `evaluation/fixtures/rubric.json`
- Create: `evaluation/fixtures/scenarios/conceptual-physics.json`
- Create: `evaluation/fixtures/scenarios/practical-programming.json`
- Create: `evaluation/fixtures/scenarios/communication-writing.json`
- Create: `tests/test_evaluation_schema.py`

**Interfaces:**
- Produces: `Scenario`, `Rubric`, `RubricCategory`, `StreamContract`, `RunRecord`, `Scorecard`, and `Finding` frozen dataclasses.
- Produces: `load_scenario(path: Path) -> Scenario`
- Produces: `load_rubric(path: Path) -> Rubric`
- Produces: `load_stream_contract(path: Path) -> StreamContract`
- Produces: `load_run_record(path: Path) -> RunRecord`
- Produces: `canonical_json(value: object) -> bytes`
- Produces: `fixture_root() -> Path`

- [ ] **Step 1: Write failing exact-key fixture tests**

```python
# tests/test_evaluation_schema.py
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evaluation.schema import fixture_root, load_rubric, load_scenario


class EvaluationSchemaTests(unittest.TestCase):
    def test_three_scenarios_have_distinct_domains_and_hard_cap(self) -> None:
        scenarios = [
            load_scenario(path)
            for path in sorted((fixture_root() / "scenarios").glob("*.json"))
        ]
        self.assertEqual(
            ["communication-writing", "conceptual-physics", "practical-programming"],
            sorted(scenario.identifier for scenario in scenarios),
        )
        self.assertEqual(
            {"communication", "conceptual", "procedural"},
            {scenario.domain for scenario in scenarios},
        )
        self.assertTrue(all(scenario.max_learner_responses == 15 for scenario in scenarios))

    def test_rubric_has_exact_categories_and_score_range(self) -> None:
        rubric = load_rubric(fixture_root() / "rubric.json")
        self.assertEqual(8, len(rubric.categories))
        self.assertEqual(16, rubric.maximum_score)
        self.assertEqual((0, 1, 2), rubric.allowed_scores)

    def test_unknown_scenario_key_is_rejected(self) -> None:
        source = fixture_root() / "scenarios/conceptual-physics.json"
        document = json.loads(source.read_text(encoding="utf-8"))
        document["unexpected"] = True
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scenario.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected"):
                load_scenario(path)
```

- [ ] **Step 2: Run the focused test and verify the missing-package failure**

Run:

```powershell
python -m unittest tests.test_evaluation_schema -v
```

Expected: `ModuleNotFoundError: No module named 'evaluation'`.

- [ ] **Step 3: Implement strict immutable loaders**

Use these exact public shapes in `evaluation/schema.py`:

```python
JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
StopReason = Literal[
    "observable_outcome",
    "maximum_learner_responses",
    "completion_without_evidence",
    "critical_pedagogical_failure",
    "infrastructure_failure",
]
FindingClass = Literal[
    "pedagogy",
    "launcher_ux",
    "documentation",
    "runtime",
    "infrastructure",
]


@dataclass(frozen=True)
class Scenario:
    schema_version: int
    identifier: str
    title: str
    domain: Literal["conceptual", "procedural", "communication"]
    initial_goal: str
    persona: Mapping[str, tuple[str, ...] | str]
    observable_outcome: tuple[str, ...]
    response_policy: tuple[str, ...]
    max_learner_responses: int


@dataclass(frozen=True)
class RubricCategory:
    identifier: str
    label: str
    anchors: Mapping[int, str]


@dataclass(frozen=True)
class Rubric:
    schema_version: int
    allowed_scores: tuple[int, ...]
    categories: tuple[RubricCategory, ...]
    critical_failures: tuple[str, ...]
    infrastructure_failures: tuple[str, ...]

    @property
    def maximum_score(self) -> int:
        return len(self.categories) * max(self.allowed_scores)


@dataclass(frozen=True)
class StreamContract:
    schema_version: int
    antigravity_version: str
    model_identifier: str
    request_text_pointer: str
    output_text_pointers: tuple[str, ...]
    completion_pointer: str
    completion_value: JsonValue
    request_template: dict[str, JsonValue]
    sample_output_events: tuple[dict[str, JsonValue], ...]


@dataclass(frozen=True)
class TurnRecord:
    number: int
    learner: str
    tutor: str


@dataclass(frozen=True)
class RunRecord:
    schema_version: int
    run_id: str
    suite_id: str
    scenario_id: str
    repository_commit: str
    protocol_version: str
    protocol_sha256: str
    runtime: Literal["antigravity"]
    runtime_version: str
    model_identifier: str
    learner_response_count: int
    stop_reason: StopReason
    infrastructure_failure: str | None
    turns: tuple[TurnRecord, ...]


@dataclass(frozen=True)
class CategoryScore:
    identifier: str
    score: Literal[0, 1, 2]
    evidence_turns: tuple[int, ...]
    rationale: str


@dataclass(frozen=True)
class Scorecard:
    schema_version: int
    scenario_id: str
    categories: tuple[CategoryScore, ...]
    critical_failures: tuple[str, ...]

    @property
    def total(self) -> int:
        return sum(category.score for category in self.categories)


@dataclass(frozen=True)
class Finding:
    identifier: str
    classification: FindingClass
    scope: Literal["general", "scenario-specific"]
    scenario_ids: tuple[str, ...]
    evidence_turns: tuple[str, ...]
    summary: str
    research_links: tuple[str, ...]
```

`load_scenario` must require exactly:

```python
{
    "schema_version",
    "identifier",
    "title",
    "domain",
    "initial_goal",
    "persona",
    "observable_outcome",
    "response_policy",
    "max_learner_responses",
}
```

Require schema version `1`, non-empty strings, a unique lowercase-hyphen identifier, non-empty outcome and response-policy arrays, and `max_learner_responses == 15`. Reject booleans where integers are expected. `canonical_json` must use:

```python
return (
    json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
).encode("utf-8")
```

- [ ] **Step 4: Add the complete rubric fixture**

Create `evaluation/fixtures/rubric.json` with this exact content:

```json
{
  "schema_version": 1,
  "allowed_scores": [0, 1, 2],
  "categories": [
    {
      "identifier": "observable-outcome",
      "label": "Observable outcome definition",
      "anchors": {
        "0": "Absent or not observable.",
        "1": "Present but incomplete, late, or weakly confirmed.",
        "2": "Clear, observable, learner-confirmed, and tied to completion evidence."
      }
    },
    {
      "identifier": "relevant-diagnosis",
      "label": "Relevant prerequisite diagnosis",
      "anchors": {
        "0": "Absent or focused on irrelevant prerequisites.",
        "1": "Partially relevant but inefficient or insufficiently evidenced.",
        "2": "Efficiently brackets only prerequisites that can block the outcome."
      }
    },
    {
      "identifier": "calibrated-questioning",
      "label": "Question difficulty calibrated to demonstrated knowledge",
      "anchors": {
        "0": "Questions are inaccessible, trivial, or detached from learner evidence.",
        "1": "Calibration is mixed, late, or generic.",
        "2": "Each question is reachable from demonstrated knowledge and adapts promptly."
      }
    },
    {
      "identifier": "adaptive-support",
      "label": "Adaptive transition among question, hint, explanation, and example",
      "anchors": {
        "0": "Support mode is inappropriate or remains stuck despite evidence.",
        "1": "Transitions occur but are late, generic, or inconsistent.",
        "2": "Transitions are timely, learner-specific, and restore productive activity."
      }
    },
    {
      "identifier": "retrieval-after-support",
      "label": "Retrieval or prediction after support",
      "anchors": {
        "0": "Support is not followed by learner retrieval or prediction.",
        "1": "Retrieval is present but overly scaffolded or incomplete.",
        "2": "The learner independently reconstructs or predicts after support."
      }
    },
    {
      "identifier": "application-transfer",
      "label": "Application and transfer evidence",
      "anchors": {
        "0": "No observable application or transfer is collected.",
        "1": "Application is partial, copied, or limited to the original case.",
        "2": "The learner applies the idea and transfers it to a distinct case."
      }
    },
    {
      "identifier": "corrective-feedback",
      "label": "Specific corrective feedback",
      "anchors": {
        "0": "Feedback is absent, incorrect, or generic.",
        "1": "Feedback identifies a problem but not the operative assumption or next action.",
        "2": "Feedback identifies the specific assumption or inference and enables a new attempt."
      }
    },
    {
      "identifier": "evidence-closure",
      "label": "Evidence-based closure and record",
      "anchors": {
        "0": "Closure is absent or claims mastery without evidence.",
        "1": "Closure records some evidence but omits material limits or required headings.",
        "2": "Closure accurately records outcome, evidence, limits, next step, and sources."
      }
    }
  ],
  "critical_failures": [
    "persistent-questioning-despite-missing-foundations",
    "extended-explanation-before-appropriate-attempt",
    "self-report-accepted-as-mastery",
    "materially-incorrect-content",
    "completion-without-application-evidence",
    "approval-gate-violation",
    "fabricated-source-or-learner-record"
  ],
  "infrastructure_failures": [
    "authentication",
    "quota",
    "network",
    "runtime",
    "timeout"
  ]
}
```

- [ ] **Step 5: Add the three complete adaptive scenario fixtures**

Create `evaluation/fixtures/scenarios/conceptual-physics.json`:

```json
{
  "schema_version": 1,
  "identifier": "conceptual-physics",
  "title": "Mass and gravitational acceleration",
  "domain": "conceptual",
  "initial_goal": "I want to understand whether a heavier object falls faster than a lighter object.",
  "persona": {
    "knowledge": [
      "Has everyday experience dropping objects.",
      "Does not know formal mechanics equations.",
      "Can compare familiar examples when prompted."
    ],
    "misconception": "A heavier object falls faster because gravity pulls harder on it.",
    "communication_style": [
      "Initially defends the misconception in plain language.",
      "States when an equation or technical term is unfamiliar.",
      "Answers one focused question at a time."
    ],
    "allowed_progress": [
      "May revise a claim only after the tutor supplies usable reasoning or evidence.",
      "May ask for a direct explanation after two unproductive hints.",
      "May apply an established idea to a new object pair."
    ],
    "forbidden_behavior": [
      "Must not introduce Newton's second law before the tutor makes it accessible.",
      "Must not reveal the target explanation merely to help the tutor pass.",
      "Must not claim understanding without explaining or applying the idea."
    ]
  },
  "observable_outcome": [
    "Predicts equal acceleration for objects with different masses when air resistance is ignored.",
    "Explains why greater gravitational force does not imply greater acceleration in this comparison.",
    "Applies the explanation to a new pair of objects."
  ],
  "response_policy": [
    "Interpret the tutor's latest response before choosing the next learner reply.",
    "Keep the initial misconception until the tutor elicits or explains a reason to revise it.",
    "If two consecutive hints remain unusable, explicitly request a direct explanation.",
    "After a clear explanation, attempt retrieval in the learner's own words before transfer.",
    "Remain within the declared novice knowledge and record uncertainty honestly."
  ],
  "max_learner_responses": 15
}
```

Create `evaluation/fixtures/scenarios/practical-programming.json`:

```json
{
  "schema_version": 1,
  "identifier": "practical-programming",
  "title": "Exclusive range bounds",
  "domain": "procedural",
  "initial_goal": "Help me fix this function without replacing it for me:\n\ndef sum_first_n(n):\n    total = 0\n    for value in range(1, n):\n        total += value\n    return total",
  "persona": {
    "knowledge": [
      "Understands variables, for loops, addition, and basic functions.",
      "Can execute a short trace when given a concrete input.",
      "Has not internalized Python's exclusive range stop bound."
    ],
    "misconception": "The number of loop iterations determines that n itself is included.",
    "communication_style": [
      "Guesses once before tracing.",
      "Expects feedback about the specific mistaken step.",
      "Uses short code or plain-language answers."
    ],
    "allowed_progress": [
      "May trace range values with support.",
      "May correct the bound after identifying why n is excluded.",
      "May transfer the rule to a different loop without copying an answer."
    ],
    "forbidden_behavior": [
      "Must not pretend to know exclusive bounds before evidence establishes them.",
      "Must not copy a complete replacement solution supplied prematurely.",
      "Must not treat a correct guess as an explanation."
    ]
  },
  "observable_outcome": [
    "Traces the function for a concrete input.",
    "Identifies that the stop value n is excluded.",
    "Corrects the bound and explains the exclusive-stop rule.",
    "Applies the rule to a different loop without copying."
  ],
  "response_policy": [
    "Make one plausible novice guess if the tutor first requests a prediction.",
    "When asked to trace, list only values justified by current understanding.",
    "Preserve the iteration-count versus included-value confusion until feedback addresses it.",
    "After correction, explain the rule before attempting a transfer loop.",
    "Do not import programming concepts outside the persona's declared knowledge."
  ],
  "max_learner_responses": 15
}
```

Create `evaluation/fixtures/scenarios/communication-writing.json`:

```json
{
  "schema_version": 1,
  "identifier": "communication-writing",
  "title": "Concise deadline clarification",
  "domain": "communication",
  "initial_goal": "Help me revise this message while keeping it respectful and safe:\n\nHi Priya, I wanted to follow up because I know everyone has been extremely busy and I do not want this to sound like I am blaming anyone, but the data export that I expected on Tuesday has not arrived yet, and because I need it before I can finish the forecast I am now concerned that the Friday deadline may no longer be realistic, although I am still willing to do everything possible on my side, so could you please let me know what you think we should do and whether the deadline is still the same?",
  "persona": {
    "knowledge": [
      "Writes grammatical and complete workplace messages.",
      "Understands the intended audience and project context.",
      "Can compare two candidate phrasings."
    ],
    "misconception": "Removing detail will make the message rude or leave the writer unsafe.",
    "communication_style": [
      "Initially writes long and defensive messages.",
      "Overexplains once after receiving feedback.",
      "Can discuss audience and purpose in plain language."
    ],
    "allowed_progress": [
      "May remove defensive framing after seeing why it obscures the request.",
      "May choose between two concise phrasings.",
      "May explain how audience and purpose shaped the final revision."
    ],
    "forbidden_behavior": [
      "Must not produce an expert edit before the tutor elicits a revision.",
      "Must not remove necessary dependency and deadline context.",
      "Must not call a shorter message better without explaining why."
    ]
  },
  "observable_outcome": [
    "Produces a message with a clear purpose and only necessary context.",
    "Includes a concrete request for deadline clarification.",
    "Uses a neutral, respectful tone and appropriate brevity.",
    "Explains how audience and purpose shaped the revision."
  ],
  "response_policy": [
    "Defend the need for detail once when the tutor first recommends shortening.",
    "Make one revision that remains too long if feedback is only generic.",
    "Use specific feedback to remove defensive framing while retaining dependency context.",
    "Compare candidate phrasings when the tutor offers or requests alternatives.",
    "Explain the final choices rather than relying on self-reported confidence."
  ],
  "max_learner_responses": 15
}
```

- [ ] **Step 6: Run schema tests and commit**

Run:

```powershell
python -m unittest tests.test_evaluation_schema -v
```

Expected: 3 tests pass; all three scenario files and the rubric load without coercion.

Commit:

```powershell
git add evaluation/__init__.py evaluation/schema.py evaluation/fixtures/rubric.json evaluation/fixtures/scenarios tests/test_evaluation_schema.py
git commit -m "test: define semantic evaluation fixtures"
```

---

### Task 2: Private Storage and Sanitization Boundary

**Files:**
- Modify: `.gitignore`
- Create: `evaluation/sanitize.py`
- Create: `tests/test_evaluation_sanitize.py`

**Interfaces:**
- Produces: `RedactionRule(literal: str, replacement: str)`
- Produces: `sanitize_json(value: JsonValue, rules: Sequence[RedactionRule]) -> JsonValue`
- Produces: `sanitize_text(text: str, rules: Sequence[RedactionRule]) -> str`
- Produces: `assert_tracked_safe(text: str, *, forbidden_literals: Sequence[str]) -> None`
- Produces: `write_private(path: Path, data: bytes, *, private_root: Path) -> None`

- [ ] **Step 1: Write failing recursive-redaction and containment tests**

```python
# tests/test_evaluation_sanitize.py
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evaluation.sanitize import (
    RedactionRule,
    assert_tracked_safe,
    sanitize_json,
    write_private,
)


class EvaluationSanitizeTests(unittest.TestCase):
    def test_recursive_redaction_preserves_json_shape(self) -> None:
        value = {
            "session_id": "provider-secret-id",
            "nested": ["C:/Users/Marcos/private", {"token": "Bearer abc123"}],
        }
        rules = (
            RedactionRule("provider-secret-id", "REDACTED_SESSION_ID"),
            RedactionRule("C:/Users/Marcos/private", "REDACTED_RUN_ROOT"),
            RedactionRule("Bearer abc123", "REDACTED_SECRET"),
        )
        self.assertEqual(
            {
                "session_id": "REDACTED_SESSION_ID",
                "nested": ["REDACTED_RUN_ROOT", {"token": "REDACTED_SECRET"}],
            },
            sanitize_json(value, rules),
        )

    def test_tracked_text_rejects_secret_and_absolute_home(self) -> None:
        with self.assertRaises(ValueError):
            assert_tracked_safe(
                "authorization: Bearer abc123\nC:\\Users\\Marcos\\private",
                forbidden_literals=("abc123",),
            )

    def test_private_write_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(ValueError):
                write_private(root.parent / "escape.txt", b"x", private_root=root)
```

- [ ] **Step 2: Run the test and verify the missing-module failure**

Run:

```powershell
python -m unittest tests.test_evaluation_sanitize -v
```

Expected: import failure for `evaluation.sanitize`.

- [ ] **Step 3: Add the raw-run ignore boundary and implementation**

Append exactly this repository-root rule to `.gitignore`:

```gitignore
/.semantic-runs/
```

Implement literal replacement longest-first, then reject tracked text matching any of:

```python
_TRACKED_FORBIDDEN = (
    re.compile(r"(?i)\b(?:authorization|api[_-]?key|access[_-]?token)\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"),
    re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\r\n]+\\"),
    re.compile(r"/(?:Users|home)/[^/\r\n]+/"),
    re.compile(r"(?i)\b(?:conversation|session)[_-]?id\b.*[A-Za-z0-9_-]{12,}"),
)
```

`write_private` must resolve `private_root`, require the destination to remain relative to it, create parents, write to a sibling temporary file with mode `0o600`, flush and `fsync`, then `os.replace`. It must not print content or environment values.

- [ ] **Step 4: Run focused tests and prove Git ignores raw runs**

Run:

```powershell
python -m unittest tests.test_evaluation_sanitize -v
git check-ignore -v .semantic-runs/probe/raw.ndjson
```

Expected: 3 tests pass; `git check-ignore` identifies `/.semantic-runs/`.

- [ ] **Step 5: Commit**

```powershell
git add .gitignore evaluation/sanitize.py tests/test_evaluation_sanitize.py
git commit -m "test: isolate raw semantic evidence"
```

---

### Task 3: Antigravity Contract Capture Gate

**Files:**
- Create: `evaluation/contract_capture.py`
- Create after successful capture: `evaluation/fixtures/antigravity/stream-contract.json`
- Create: `tests/test_evaluation_contract.py`

**Interfaces:**
- Consumes: an exact one-line request envelope copied from first-party Antigravity documentation or emitted by the installed CLI; the code never synthesizes envelope fields.
- Produces: `capture_contract(executable: str, model: str, request_line: bytes, raw_root: Path, *, completion_pointer: str, completion_value: JsonValue, run: Callable[..., CompletedProcess[bytes]] = subprocess.run) -> dict[str, JsonValue]`
- Produces: `publish_contract_fixture(capture: Mapping[str, JsonValue], destination: Path, *, rules: Sequence[RedactionRule]) -> Path`
- Produces: private CLI commands `discover`, `select-model`, `capture`, and `validate-fixture`.

- [ ] **Step 1: Write a failing fake-process contract test without asserting a wire shape**

```python
# tests/test_evaluation_contract.py
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from evaluation.contract_capture import capture_contract, publish_contract_fixture
from evaluation.schema import load_stream_contract
from evaluation.sanitize import RedactionRule


class EvaluationContractTests(unittest.TestCase):
    def test_capture_preserves_observed_envelope_and_sanitizes_values(self) -> None:
        request = b'{"observed_request":{"text":"STREAM_CONTRACT_OK"}}\n'
        output = (
            b'{"observed_event":"delta","payload":"STREAM_CONTRACT_OK"}\n'
            b'{"observed_event":"complete","session":"private-session-123456"}\n'
        )

        def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[bytes]:
            self.assertIn("--input-format", argv)
            self.assertIn("stream-json", argv)
            self.assertEqual(request, kwargs["input"])
            return CompletedProcess(argv, 0, output, b"")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            captured = capture_contract(
                "agy",
                "captured-model-id",
                request,
                root / "raw",
                completion_pointer="/observed_event",
                completion_value="complete",
                run=fake_run,
            )
            fixture = publish_contract_fixture(
                captured,
                root / "stream-contract.json",
                rules=(
                    RedactionRule(
                        "private-session-123456",
                        "REDACTED_SESSION_ID",
                    ),
                ),
            )
            contract = load_stream_contract(fixture)
            fixture_text = fixture.read_text(encoding="utf-8")

        self.assertEqual("captured-model-id", contract.model_identifier)
        self.assertIn("REDACTED_SESSION_ID", fixture_text)
        self.assertNotIn("private-session-123456", fixture_text)
```

The fake keys are deliberately test-only. They do not claim Antigravity uses that shape.

- [ ] **Step 2: Run the test and verify the missing capture module**

Run:

```powershell
python -m unittest tests.test_evaluation_contract -v
```

Expected: import failure for `evaluation.contract_capture`.

- [ ] **Step 3: Implement capture without inventing envelope fields**

The capture command must execute exactly:

```python
argv = [
    executable,
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--model",
    model,
    "--sandbox",
    "--disable-slash-commands",
    "--print-timeout",
    "300s",
    "--log-file",
    str(raw_root / "antigravity.log"),
]
```

The argv must not contain `--print` or `--mode` (see the compatibility rationale in Global Constraints); the exact-argv test asserts both are absent.

It writes request, stdout, stderr, argv, `agy --version`, `agy --help`, and `agy models` output under `.semantic-runs/contract/`. It parses every non-empty stdout line with `json.loads`; a non-JSON line, non-zero exit, absent marker, or missing completion event fails capture without publishing a tracked fixture.

The operator must identify two values from observed successful data:

1. the JSON Pointer to `STREAM_CONTRACT_OK` in the request object;
2. the JSON Pointer/value pair that marks the completed output turn.

The command validates both pointers against captured JSON before publication. The tracked fixture has this stable wrapper while retaining the observed nested objects unchanged:

```python
fixture = {
    "schema_version": 1,
    "antigravity_version": captured["antigravity_version"],
    "model_identifier": captured["model_identifier"],
    "request_text_pointer": captured["request_text_pointer"],
    "output_text_pointers": captured["output_text_pointers"],
    "completion_pointer": captured["completion_pointer"],
    "completion_value": captured["completion_value"],
    "request_template": captured["request_template"],
    "sample_output_events": captured["sample_output_events"],
}
```

Do not add a fallback envelope. A missing first-party example or unsuccessful probe is an infrastructure blocker with exit code `2`.

- [ ] **Step 4: Capture the installed CLI and exact available model**

Run these commands from the repository root:

```powershell
New-Item -ItemType Directory -Force .semantic-runs/contract | Out-Null
agy --version | Set-Content -Encoding utf8 .semantic-runs/contract/version.txt
agy --help | Set-Content -Encoding utf8 .semantic-runs/contract/help.txt
agy models | Tee-Object -FilePath .semantic-runs/contract/models.txt
python -m evaluation.contract_capture select-model --models-file .semantic-runs/contract/models.txt --output .semantic-runs/contract/model.txt
python -m evaluation.contract_capture discover --raw-root .semantic-runs/contract
```

At the `select-model` prompt, the implementing agent enters one exact model identifier printed in the first column of `agy models`; the command rejects any other value. At the `discover` prompt, paste one exact one-line stream-json request example obtained from first-party Antigravity material, change only its user-text value to `STREAM_CONTRACT_OK`, and enter the two observed JSON Pointers. Do not infer field names from another runtime.

Then run:

```powershell
python -m evaluation.contract_capture capture `
  --raw-root .semantic-runs/contract `
  --model-file .semantic-runs/contract/model.txt `
  --fixture evaluation/fixtures/antigravity/stream-contract.json
python -m evaluation.contract_capture validate-fixture evaluation/fixtures/antigravity/stream-contract.json
```

Expected:

- the probe exits zero;
- stdout contains one or more valid JSON values;
- the extracted tutor text contains exactly `STREAM_CONTRACT_OK`;
- the selected model is an exact listed identifier;
- all raw material remains ignored under `.semantic-runs/contract/`;
- the tracked fixture contains no absolute user path, credential, provider identifier, or raw conversation/session identifier;
- validation prints `Antigravity stream contract fixture is valid.`

- [ ] **Step 5: Run focused tests and commit the observed fixture**

Run:

```powershell
python -m unittest tests.test_evaluation_contract -v
git check-ignore --quiet .semantic-runs/contract/stdout.ndjson
git diff --check
```

Expected: focused tests pass, the raw capture is ignored, and only the sanitized fixture is trackable.

Commit:

```powershell
git add evaluation/contract_capture.py evaluation/fixtures/antigravity/stream-contract.json tests/test_evaluation_contract.py
git commit -m "test: capture antigravity stream contract"
```

---

### Task 4: Contract-Driven NDJSON Parser

**Files:**
- Create: `evaluation/parser.py`
- Create: `tests/test_evaluation_parser.py`

**Interfaces:**
- Consumes: `StreamContract` loaded from the captured fixture.
- Produces: `parse_ndjson(data: bytes) -> tuple[dict[str, JsonValue], ...]`
- Produces: `json_pointer_get(value: JsonValue, pointer: str) -> JsonValue`
- Produces: `json_pointer_set(value: JsonValue, pointer: str, replacement: JsonValue) -> JsonValue`
- Produces: `request_line(contract: StreamContract, text: str) -> bytes`
- Produces: `collect_tutor_turn(events: Sequence[dict[str, JsonValue]], contract: StreamContract) -> TutorTurn`
- Produces: `TutorTurn(text: str, event_count: int, completed: bool)`

- [ ] **Step 1: Write failing parser tests against the captured fixture**

```python
# tests/test_evaluation_parser.py
from __future__ import annotations

import json
import unittest

from evaluation.parser import (
    collect_tutor_turn,
    json_pointer_get,
    parse_ndjson,
    request_line,
)
from evaluation.schema import fixture_root, load_stream_contract


class EvaluationParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_stream_contract(
            fixture_root() / "antigravity/stream-contract.json"
        )

    def test_request_replaces_only_observed_text_location(self) -> None:
        encoded = request_line(self.contract, "learner cafés")
        document = json.loads(encoded)
        self.assertEqual(
            "learner cafés",
            json_pointer_get(document, self.contract.request_text_pointer),
        )

    def test_sample_events_replay_to_completed_tutor_turn(self) -> None:
        turn = collect_tutor_turn(
            self.contract.sample_output_events,
            self.contract,
        )
        self.assertTrue(turn.completed)
        self.assertIn("STREAM_CONTRACT_OK", turn.text)

    def test_invalid_ndjson_reports_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_ndjson(b'{"ok":true}\nnot-json\n')
```

- [ ] **Step 2: Run tests and verify the parser module is missing**

Run:

```powershell
python -m unittest tests.test_evaluation_parser -v
```

Expected: import failure for `evaluation.parser`.

- [ ] **Step 3: Implement RFC 6901 pointer handling and contract-driven extraction**

Implement pointer token decoding exactly:

```python
def _tokens(pointer: str) -> tuple[str, ...]:
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must be empty or start with '/'")
    return tuple(
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    )
```

`request_line` deep-copies `request_template`, sets only `request_text_pointer`, serializes compact UTF-8 JSON with `ensure_ascii=False`, and appends one newline. `collect_tutor_turn` visits only the captured `output_text_pointers`, preserves event order, joins non-empty text fragments without duplicating cumulative snapshots, and requires the exact captured completion pointer/value match. Unknown event keys are preserved in raw storage but ignored by text extraction.

- [ ] **Step 4: Run parser and contract suites**

Run:

```powershell
python -m unittest tests.test_evaluation_parser tests.test_evaluation_contract -v
```

Expected: all tests pass using the actual captured fixture; no Antigravity process is invoked.

- [ ] **Step 5: Commit**

```powershell
git add evaluation/parser.py tests/test_evaluation_parser.py
git commit -m "feat: parse captured antigravity streams"
```

---

### Task 5: Isolated Run Layout and Unchanged Protocol Identity

**Files:**
- Create: `evaluation/isolation.py`
- Create: `tests/test_evaluation_isolation.py`

**Interfaces:**
- Consumes: `prepare_personal_workspace`, `build_distribution`, `PROTOCOL_VERSION`, `write_private`.
- Produces: `RULE_MARKERS = ("AGENTS.md", "GEMINI.md", "CLAUDE.md", ".agents", ".agent")`: marker *names* checked in individual directories (the cwd ancestry, and ancestors above the user home).
- Produces: `USER_HOME_RULE_PATHS = ("AGENTS.md", "GEMINI.md", "CLAUDE.md", ".agents", ".agent", ".gemini/GEMINI.md")`: POSIX *paths relative to the user home* that are disclosed when present.
- Produces: `class LocalRuleContamination(ValueError)`
- Produces: `AboveHomeMarker(levels_above_home: int, marker: str)` and `RuleDisclosure(boundary: Literal["user_home", "filesystem_root"], user_home_rule_paths: tuple[str, ...], above_home_markers: tuple[AboveHomeMarker, ...])`
- Produces: `RunLayout(run_dir: Path, raw: Path, evaluator: Path, runtime_root: Path, owns_runtime_root: bool, home: Path, cwd: Path, records: Path, protocol: Path, user_home: Path, rule_disclosure: RuleDisclosure)`
  - internal (repository, ignored): `run_dir = raw_root / suite_id / scenario_id`, `raw = run_dir / "raw"`, `evaluator = run_dir / "evaluator"`;
  - external (outside the repository): `runtime_root` is the **per-run** directory removed at cleanup, `home = runtime_root / "home"`, and `cwd`, `records`, `protocol` come from `prepare_personal_workspace(home)`, so `cwd == home / "learning"`.
- Produces: `ProtocolIdentity(repository_commit: str, protocol_version: str, bundle_sha256: str)`
- Produces: `create_run_layout(repository: Path, suite_id: str, scenario_id: str, *, raw_root: Path | None = None, runtime_base: Path | None = None, user_home: Path | None = None) -> RunLayout`
  - live defaults: `raw_root = repository / ".semantic-runs"`; with `runtime_base=None` the per-run `runtime_root` is `Path(tempfile.mkdtemp(prefix="socratic-semantic-"))` (a fresh owner-only directory in the secure system temporary location, `owns_runtime_root=True`); `user_home = Path.home()`;
  - tests inject `raw_root`, `runtime_base`, and `user_home` as temporary directories. An injected `runtime_base` is a shared parent that is never deleted; the per-run `runtime_root` is `runtime_base / suite_id / scenario_id` with `owns_runtime_root=False`.
- Produces: `assert_no_local_rule_ancestors(cwd: Path, user_home: Path) -> Literal["user_home", "filesystem_root"]` (returns the boundary used)
- Produces: `disclose_rule_markers(user_home: Path, boundary: Literal["user_home", "filesystem_root"]) -> RuleDisclosure`
- Produces: `load_runtime_context(run_dir: Path) -> RuntimeContext` with `RuntimeContext(runtime_root: Path, runtime_outside_repository: bool, local_rule_check_passed: bool, rule_disclosure: RuleDisclosure)`
- Produces: `snapshot_learner_records(layout: RunLayout) -> Path`
- Produces: `remove_runtime_root(layout: RunLayout, repository: Path) -> None`
- Produces: `isolated_environment(layout: RunLayout, parent: Mapping[str, str]) -> dict[str, str]`
- Produces: `capture_protocol_identity(repository: Path) -> ProtocolIdentity`
- Produces: `assert_protocol_unchanged(expected: ProtocolIdentity, repository: Path) -> None`

- [ ] **Step 1: Write failing isolation tests**

```python
# tests/test_evaluation_isolation.py
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from evaluation.isolation import (
    RULE_MARKERS,
    AboveHomeMarker,
    LocalRuleContamination,
    assert_no_local_rule_ancestors,
    create_run_layout,
    disclose_rule_markers,
    isolated_environment,
    load_runtime_context,
    remove_runtime_root,
    snapshot_learner_records,
)


class EvaluationIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.outer = Path(temporary.name).resolve()
        self.user_home = self.outer / "home"
        self.repository = self.user_home / "projects" / "repo"
        self.repository.mkdir(parents=True)
        self.raw_root = self.repository / ".semantic-runs"
        self.runtime_base = self.user_home / "runtime"
        self.runtime_base.mkdir()

    def layout(self, scenario: str, **overrides: object):
        arguments = {
            "raw_root": self.raw_root,
            "runtime_base": self.runtime_base,
            "user_home": self.user_home,
        }
        arguments.update(overrides)
        return create_run_layout(self.repository, "suite", scenario, **arguments)

    def test_raw_is_internal_and_runtime_is_external(self) -> None:
        layout = self.layout("conceptual-physics")
        self.assertEqual(self.raw_root / "suite" / "conceptual-physics", layout.run_dir)
        self.assertTrue(layout.raw.is_relative_to(layout.run_dir))
        self.assertEqual(self.runtime_base / "suite" / "conceptual-physics", layout.runtime_root)
        self.assertFalse(layout.home.is_relative_to(self.repository))
        self.assertFalse(layout.cwd.is_relative_to(self.repository))
        self.assertEqual(layout.home / "learning", layout.cwd)
        self.assertTrue(layout.protocol.is_file())

    def test_runtime_context_records_check_and_boundary(self) -> None:
        layout = self.layout("conceptual-physics")
        context = load_runtime_context(layout.run_dir)
        self.assertEqual(layout.runtime_root, context.runtime_root)
        self.assertTrue(context.runtime_outside_repository)
        self.assertTrue(context.local_rule_check_passed)
        self.assertEqual("user_home", context.rule_disclosure.boundary)

    def test_scenarios_receive_separate_home_and_cwd(self) -> None:
        first = self.layout("conceptual-physics")
        second = self.layout("practical-programming")
        self.assertNotEqual(first.home, second.home)
        self.assertNotEqual(first.cwd, second.cwd)
        self.assertNotEqual(first.run_dir, second.run_dir)

    def test_live_default_runtime_is_secure_temporary_outside_repository(self) -> None:
        # Machine-dependent: uses the real system temp directory and real user home.
        layout = create_run_layout(
            self.repository,
            "suite",
            "conceptual-physics",
            raw_root=self.raw_root,
            user_home=Path.home(),
        )
        try:
            self.assertTrue(layout.owns_runtime_root)
            self.assertTrue(
                layout.runtime_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
            )
            self.assertFalse(layout.cwd.is_relative_to(self.repository))
        finally:
            remove_runtime_root(layout, self.repository)

    def test_runtime_inside_repository_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.layout("conceptual-physics", runtime_base=self.repository / "runtime")
        with self.assertRaises(ValueError):
            self.layout("practical-programming", runtime_base=self.raw_root / "runtime")
        self.assertFalse((self.raw_root / "suite").exists())

    def test_local_rule_markers_below_user_home_are_rejected(self) -> None:
        for marker in RULE_MARKERS:
            with self.subTest(marker):
                parent = self.user_home / f"ancestor-{marker.strip('.')}"
                cwd = parent / "child" / "learning"
                cwd.mkdir(parents=True)
                if marker.endswith(".md"):
                    (parent / marker).write_text("not read", encoding="utf-8")
                else:
                    (parent / marker).mkdir()
                with self.assertRaises(LocalRuleContamination):
                    assert_no_local_rule_ancestors(cwd, self.user_home)

    def test_marker_in_cwd_itself_is_rejected(self) -> None:
        cwd = self.user_home / "work" / "learning"
        cwd.mkdir(parents=True)
        (cwd / "AGENTS.md").write_text("not read", encoding="utf-8")
        with self.assertRaises(LocalRuleContamination):
            assert_no_local_rule_ancestors(cwd, self.user_home)

    def test_cwd_outside_user_home_uses_filesystem_root_boundary(self) -> None:
        cwd = self.outer / "elsewhere" / "learning"
        cwd.mkdir(parents=True)
        real_lexists = os.path.lexists

        def scoped(path: object) -> bool:
            # Ancestors above the temporary tree are real machine directories.
            return Path(path).is_relative_to(self.outer) and real_lexists(path)

        with mock.patch("evaluation.isolation.os.path.lexists", side_effect=scoped):
            self.assertEqual(
                "filesystem_root", assert_no_local_rule_ancestors(cwd, self.user_home)
            )
            (self.outer / "elsewhere" / "CLAUDE.md").write_text("not read", encoding="utf-8")
            with self.assertRaises(LocalRuleContamination):
                assert_no_local_rule_ancestors(cwd, self.user_home)

    def test_user_level_rules_are_allowed_and_disclosed_by_name_only(self) -> None:
        (self.user_home / "AGENTS.md").write_text("private rule text", encoding="utf-8")
        (self.user_home / ".agents").mkdir()
        (self.user_home / ".gemini").mkdir()
        (self.user_home / ".gemini" / "GEMINI.md").write_text("private", encoding="utf-8")
        (self.outer / "GEMINI.md").write_text("private above-home rule", encoding="utf-8")
        cwd = self.user_home / "work" / "learning"
        cwd.mkdir(parents=True)
        with mock.patch("builtins.open", side_effect=AssertionError("must not read")):
            boundary = assert_no_local_rule_ancestors(cwd, self.user_home)
            disclosure = disclose_rule_markers(self.user_home, boundary)
        self.assertEqual(
            ("AGENTS.md", ".agents", ".gemini/GEMINI.md"),
            disclosure.user_home_rule_paths,
        )
        # Ancestors above `outer` are real machine directories, so assert containment only.
        self.assertIn(AboveHomeMarker(1, "GEMINI.md"), disclosure.above_home_markers)

    def test_layout_rejects_contaminated_external_runtime(self) -> None:
        (self.runtime_base / "GEMINI.md").write_text("not read", encoding="utf-8")
        with self.assertRaises(LocalRuleContamination):
            self.layout("conceptual-physics")
        self.assertFalse((self.runtime_base / "suite" / "conceptual-physics").exists())

    def test_snapshot_copies_regular_files_and_skips_links(self) -> None:
        layout = self.layout("conceptual-physics")
        (layout.records / "progress.md").write_text("learner record", encoding="utf-8")
        outside = self.outer / "outside.txt"
        outside.write_text("must not be copied", encoding="utf-8")
        try:
            os.symlink(outside, layout.records / "linked.txt")
        except OSError:
            linked = False
        else:
            linked = True
        snapshot = snapshot_learner_records(layout)
        self.assertEqual("learner record", (snapshot / "progress.md").read_text("utf-8"))
        self.assertFalse((snapshot / "linked.txt").exists())
        if linked:
            skipped = json.loads((snapshot.parent / "skipped-links.json").read_text("utf-8"))
            self.assertEqual(["linked.txt"], skipped)

    def test_remove_runtime_root_deletes_only_per_run_runtime(self) -> None:
        layout = self.layout("conceptual-physics")
        layout.raw.mkdir(parents=True, exist_ok=True)
        remove_runtime_root(layout, self.repository)
        self.assertFalse(layout.runtime_root.exists())
        self.assertTrue(self.runtime_base.is_dir())
        self.assertTrue(layout.run_dir.is_dir())
        unsafe = replace(layout, runtime_root=self.repository)
        with self.assertRaises(ValueError):
            remove_runtime_root(unsafe, self.repository)
        self.assertTrue(self.repository.is_dir())

    def test_environment_inherits_auth_without_inspection(self) -> None:
        parent = {
            "PATH": "C:/bin",
            "ANTIGRAVITY_AUTH_STATE": "opaque-parent-value",
            "HOME": "C:/Users/tester",
        }
        layout = type("Layout", (), {"home": Path("C:/private/home")})()
        child = isolated_environment(layout, parent)
        self.assertEqual("opaque-parent-value", child["ANTIGRAVITY_AUTH_STATE"])
        self.assertEqual("C:/Users/tester", child["HOME"])
        self.assertEqual("C:/private/home", child["SOCRATIC_LEARN_HOME"])
```

`test_live_default_runtime_is_secure_temporary_outside_repository` is machine-dependent: it uses the real system temporary directory and the real user home. A `LocalRuleContamination` failure there means this machine has a stray rule marker in its temporary-directory ancestry below the user home; that would also block live runs, so fix the machine rather than weakening the test. All other tests are deterministic: they use only the injected temporary tree, the filesystem-root-boundary test scopes `os.path.lexists` to that tree (so `evaluation.isolation` must call `os.path.lexists` through the `os` module), and above-home disclosure assertions use containment because ancestors above the temporary tree are real directories.

- [ ] **Step 2: Run tests and verify the missing isolation module**

Run:

```powershell
python -m unittest tests.test_evaluation_isolation -v
```

Expected: import failure for `evaluation.isolation`.

- [ ] **Step 3: Implement the external-runtime / internal-raw layout and in-memory protocol verification**

Naming: `runtime_base` is the optional injected shared parent and is never deleted; `runtime_root` is always the per-run directory owned by one layout and removed at cleanup.

```python
raw_root = (raw_root or repository / ".semantic-runs").resolve()
run_dir = raw_root / suite_id / scenario_id
raw = run_dir / "raw"
evaluator = run_dir / "evaluator"
user_home = (user_home or Path.home()).resolve()

if runtime_base is None:
    runtime_root = None  # created by mkdtemp after the checks below
    owns_runtime_root = True
else:
    runtime_root = (runtime_base / suite_id / scenario_id).resolve()
    owns_runtime_root = False
```

Create the layout in this order:

1. Validate `suite_id` and `scenario_id` against `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
2. Validate that `run_dir` resolves under `raw_root` and does not exist. With live defaults, `raw_root` is the repository's `.semantic-runs/`.
3. For an injected `runtime_base`, validate that `runtime_root` resolves outside the resolved repository and outside `raw_root` (`is_relative_to` is false for both), does not exist, and has no link component. Otherwise raise `ValueError`. Steps 1–3 create nothing.
4. Create the per-run `runtime_root`: `mkdtemp` for live defaults, or `mkdir(parents=True)` for an injected base. Re-check that the resolved `runtime_root` is outside the repository and `raw_root`. From here on, any failure removes `runtime_root` before re-raising.
5. `workspace = prepare_personal_workspace(runtime_root / "home")`; use `cwd=workspace.root`, `protocol=workspace.protocol`, `records=workspace.records`. This matches bare `socratic` rather than the `--here` variant.
6. `boundary = assert_no_local_rule_ancestors(cwd, user_home)`.
7. `disclosure = disclose_rule_markers(user_home, boundary)`.
8. Create `run_dir` and write `run_dir / "runtime-context.json"` with `write_private`. It contains exactly:
   - `runtime_root`: the absolute external path, private, used only for deletion checks;
   - `runtime_outside_repository`: `true`;
   - `local_rule_check_passed`: `true`;
   - `rule_boundary`: `"user_home"` or `"filesystem_root"`;
   - `user_home_rule_paths`: list of relative paths;
   - `above_home_markers`: list of `{"levels_above_home": int, "marker": str}`.

   It records no user-home path and no rule content.

`assert_no_local_rule_ancestors(cwd, user_home)` walks `cwd` and its ancestors:

- When `user_home` is an ancestor of `cwd`, it stops before `user_home` and returns `"user_home"`. User-home and above-home markers are never rejected.
- Otherwise it checks every ancestor up to and including the filesystem root and returns `"filesystem_root"`.
- For each checked directory it tests only `os.path.lexists(directory / marker)` for each `RULE_MARKERS` entry. On a hit it raises `LocalRuleContamination` naming the marker and the number of levels above `cwd`, never an absolute path.
- It never opens, reads, lists, or resolves rule files.

`disclose_rule_markers(user_home, boundary)` performs existence checks only, with `os.path.lexists` and no reads, listing, or link resolution, in two clearly separate groups:

1. **User-home-relative rule paths:** each `USER_HOME_RULE_PATHS` entry that exists as `user_home / entry`. These are recorded as the relative POSIX path, in tuple order, for example `".gemini/GEMINI.md"`.
2. **Above-home ancestor markers:** for each ancestor strictly above `user_home`, walking up to and including the filesystem root, each `RULE_MARKERS` name that exists in that directory. These are recorded as `AboveHomeMarker(levels_above_home, marker)`, where the parent of `user_home` is level 1. Ancestor paths are not recorded.

Both groups are disclosed as baseline limitations: user-level and above-home rules are inherited together with authentication and are not removed. When the boundary is `"filesystem_root"`, any marker in the cwd ancestry has already been rejected, so above-home disclosure covers only the user home's own ancestry.

`snapshot_learner_records(layout)` copies the external `layout.records` tree into `layout.run_dir / "learner-records"` with `write_private`, walking with `os.walk(followlinks=False)`:

- It copies regular files only.
- It skips every symbolic link, Windows junction, or other reparse point without opening or resolving it. Detection uses `os.lstat`, with `stat.S_ISLNK` and, on Windows, `st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`.
- It records each skipped entry's records-relative POSIX path in `layout.run_dir / "skipped-links.json"`.
- It returns the snapshot directory.

`remove_runtime_root(layout, repository)` refuses with `ValueError` any `runtime_root` that is:

- inside the repository or `raw_root`;
- equal to or an ancestor of `layout.user_home`;
- a link.

Otherwise it removes the per-run `runtime_root` with `shutil.rmtree`. For live defaults that is the whole `mkdtemp` directory; it never removes an injected `runtime_base`.

Do not modify the process-wide environment.

Build child environment exactly:

```python
environment = dict(parent)
environment["SOCRATIC_LEARN_HOME"] = str(layout.home)
environment["PYTHONDONTWRITEBYTECODE"] = "1"
return environment
```

Do not replace `HOME`, `USERPROFILE`, runtime-specific variables, or credential variables. Authentication and user-level runtime rules are therefore inherited unchanged.

`capture_protocol_identity` must:

1. run `git rev-parse HEAD`;
2. call `build_distribution(repository)` in memory;
3. compare its bundle and manifest bytes to checked-in `dist/`;
4. record `PROTOCOL_VERSION` and SHA-256 of the bundle;
5. perform no write.

- [ ] **Step 4: Run isolation and existing workspace tests**

Run:

```powershell
python -m unittest tests.test_evaluation_isolation tests.test_workspace -v
git diff --exit-code -- core dist
```

Expected: tests pass; every test layout's home/cwd is outside the injected repository; local rule markers below the user home (or up to the filesystem root when the cwd is outside it) are rejected; user-home-relative rule paths including `.gemini/GEMINI.md` and above-home ancestor markers are disclosed by name only; the runtime context records `local_rule_check_passed` and the boundary; snapshots skip links; per-run runtimes are removed while raw evidence and the injected base remain; canonical protocol files remain byte-unchanged.

- [ ] **Step 5: Commit**

```powershell
git add evaluation/isolation.py tests/test_evaluation_isolation.py
git commit -m "feat: isolate semantic evaluation runs"
```

---

### Task 6: Persistent Antigravity Stream Adapter

**Files:**
- Create: `evaluation/antigravity.py`
- Create: `tests/test_evaluation_antigravity.py`

**Interfaces:**
- Consumes: `RunLayout` (external `cwd`, internal `raw`), `assert_no_local_rule_ancestors`, `StreamContract`, `request_line`, and `collect_tutor_turn`.
- Consumes: public `ADAPTERS["antigravity"]` and `command_for` from `socratic_learn.hosts`.
- Produces: `initial_bootstrap(protocol: Path, goal: str) -> str`
- Produces: `antigravity_argv(executable: str, model: str, layout: RunLayout) -> tuple[str, ...]`
- Produces: `class AntigravitySession(executable: str, model: str, layout: RunLayout, contract: StreamContract, *, repository: Path, parent_environment: Mapping[str, str], popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen)`. `repository` is the explicit checkout root used for the launch-time containment check; the child environment is `isolated_environment(layout, parent_environment)`.
- Produces: `AntigravitySession.start() -> None`
- Produces: `AntigravitySession.send(text: str) -> TutorTurn`
- Produces: `AntigravitySession.close() -> int`
- Produces: `InfrastructureFailure(kind: Literal["authentication", "quota", "network", "runtime", "timeout"], detail: str)`

- [ ] **Step 1: Write failing exact-argv and fake-stream tests**

```python
# tests/test_evaluation_antigravity.py
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from evaluation.antigravity import antigravity_argv


class EvaluationAntigravityTests(unittest.TestCase):
    def test_argv_is_explicit_streaming_sandboxed_and_model_pinned(self) -> None:
        layout = type(
            "Layout",
            (),
            {"raw": Path("C:/private/raw")},
        )()
        argv = antigravity_argv("agy", "captured-model-id", layout)
        self.assertEqual("agy", argv[0])
        self.assertEqual(1, argv.count("captured-model-id"))
        self.assertNotIn("--print", argv)
        self.assertNotIn("--mode", argv)
        self.assertEqual(
            "stream-json",
            argv[argv.index("--input-format") + 1],
        )
        self.assertEqual(
            "stream-json",
            argv[argv.index("--output-format") + 1],
        )
        self.assertIn("--sandbox", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_adapter_has_no_learner_model_parameter(self) -> None:
        from inspect import signature
        from evaluation.antigravity import AntigravitySession

        parameters = signature(AntigravitySession).parameters
        self.assertNotIn("learner_model", parameters)
        self.assertNotIn("learner_runtime", parameters)
```

- [ ] **Step 2: Run the test and verify the missing adapter**

Run:

```powershell
python -m unittest tests.test_evaluation_antigravity -v
```

Expected: import failure for `evaluation.antigravity`.

- [ ] **Step 3: Implement exact argv and persistent process ownership**

Implement the public-launcher bootstrap adapter without duplicating its text:

```python
from socratic_learn.hosts import ADAPTERS, command_for


def initial_bootstrap(protocol: Path, goal: str) -> str:
    return command_for(
        ADAPTERS["antigravity"],
        "agy",
        protocol,
        goal,
    )[2]
```

Use this exact argv:

```python
return (
    executable,
    "--input-format",
    "stream-json",
    "--output-format",
    "stream-json",
    "--model",
    model,
    "--sandbox",
    "--disable-slash-commands",
    "--print-timeout",
    "300s",
    "--log-file",
    str(layout.raw / "antigravity.log"),
)
```

The log path stays internal (`layout.raw`, under the repository's ignored `.semantic-runs/`), while the subprocess working directory is the external `layout.cwd`. Immediately before launch, `start()`:

1. raises `ValueError` without calling `popen` if `layout.cwd.resolve()` or `layout.runtime_root.resolve()` is relative to `self.repository.resolve()`;
2. calls `assert_no_local_rule_ancestors(layout.cwd, layout.user_home)` again and lets `LocalRuleContamination` propagate without calling `popen`;
3. only then calls `popen(...)`.

Start with:

```python
self.popen(
    list(argv),
    cwd=layout.cwd,  # external runtime cwd, never inside the repository
    env=environment,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=False,
)
```

`send` writes exactly one `request_line`, flushes, records it as raw NDJSON, reads stdout lines until the captured completion match, records every line before parsing, and returns one `TutorTurn`. A daemon thread drains stderr into `raw/stderr.log` to prevent pipe deadlock. `close` closes stdin, waits at most 10 seconds, terminates once, waits 5 seconds, then kills only the child if still running.

Classify failure from process status and stderr without parsing arbitrary provider prose into a pedagogy result. Preserve the exact raw stderr privately; tracked reports receive only the failure class and a sanitized one-line summary.

- [ ] **Step 4: Add fake-process coverage for multiple turns and raw logging**

Add a fake `Popen` object whose stdout is built from the sanitized captured fixture twice. Assert:

```python
self.assertEqual(
    ["first learner turn", "second learner turn"],
    decoded_request_texts,
)
self.assertTrue((layout.raw / "input.ndjson").is_file())
self.assertTrue((layout.raw / "output.ndjson").is_file())
self.assertEqual("captured-model-id", session.model)
```

Also test timeout, early EOF, non-JSON output, and non-zero exit as infrastructure failures.

Add fake-`popen` tests using a layout from `create_run_layout` with injected `raw_root`, `runtime_base`, and `user_home`, and an injected temporary `repository`:

- the recorded `cwd` keyword equals `layout.cwd` and is not inside `repository`, and the `--log-file` value is `layout.raw / "antigravity.log"`;
- `start()` raises `LocalRuleContamination` without calling `popen` when an `AGENTS.md` is placed in an ancestor of `layout.cwd` below `layout.user_home` after the layout is created;
- `start()` raises `ValueError` without calling `popen` for `dataclasses.replace(layout, cwd=repository / "learning")`, proving the check uses the explicit `repository` argument.

- [ ] **Step 5: Run adapter and parser tests**

Run:

```powershell
python -m unittest tests.test_evaluation_antigravity tests.test_evaluation_parser -v
```

Expected: all tests pass without network or Antigravity invocation.

- [ ] **Step 6: Commit**

```powershell
git add evaluation/antigravity.py tests/test_evaluation_antigravity.py
git commit -m "feat: add private antigravity adapter"
```

---

### Task 7: Manual Adaptive Session Controller

**Files:**
- Create: `evaluation/session.py`
- Create: `evaluation/cli.py`
- Create: `tests/test_evaluation_session.py`

**Interfaces:**
- Consumes: scenario, isolated layout, protocol identity, and `AntigravitySession`.
- Produces: `EvaluatorDecision(action: Literal["respond", "stop"], response: str | None, stop_reason: StopReason | None)`
- Produces: `EvaluatorContext(scenario: Scenario, tutor_turns: tuple[TutorTurn, ...], learner_responses: tuple[str, ...])`
- Produces: `ConsoleEvaluator.decide(context: EvaluatorContext) -> EvaluatorDecision`
- Produces: `SessionProgress(turns: list[TurnRecord], learner_response_count: int)`: a mutable collector that `run_session` updates after every completed tutor turn.
- Produces: `run_session(scenario: Scenario, tutor: TutorSession, evaluator: ConsoleEvaluator, identity: ProtocolIdentity, initial_request: str, run_id: str, *, record_path: Path | None = None, progress: SessionProgress | None = None) -> RunRecord`
- Produces: `infrastructure_record(*, scenario: Scenario, identity: ProtocolIdentity, run_id: str, suite_id: str, runtime_version: str, model_identifier: str, kind: Literal["authentication", "quota", "network", "runtime", "timeout"], progress: SessionProgress) -> dict[str, JsonValue]`
- Produces: `class RuntimeCleanupError(RuntimeError)` carrying the cleanup step names that failed.
- Produces: `execute_isolated_run(layout: RunLayout, repository: Path, suite_id: str, scenario: Scenario, tutor_factory: Callable[[RunLayout], TutorSession], evaluator: ConsoleEvaluator, identity: ProtocolIdentity, run_id: str, *, model_identifier: str, runtime_version: str) -> RunRecord`. `model_identifier` is the validated model-file value and `runtime_version` is the preflight `agy --version`, so failure records are complete even when no tutor was constructed.
- Produces: `verify_run_isolation(run_dir: Path, repository: Path) -> None`
- Produces: private commands `preflight`, `run`, `verify-isolation`, `score`, `report`, and `validate-report`.

- [ ] **Step 1: Write failing cap and stop-precedence tests**

```python
# tests/test_evaluation_session.py
from __future__ import annotations

import unittest

from evaluation.antigravity import InfrastructureFailure
from evaluation.isolation import ProtocolIdentity
from evaluation.parser import TutorTurn
from evaluation.schema import RunRecord, Scenario
from evaluation.session import EvaluatorDecision, run_session


class FakeTutor:
    model = "synthetic-model"
    runtime_version = "synthetic-runtime"

    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> TutorTurn:
        self.messages.append(text)
        return TutorTurn(
            text=f"tutor-{len(self.messages)}",
            event_count=1,
            completed=True,
        )


class FailingTutor(FakeTutor):
    def send(self, text: str) -> TutorTurn:
        raise InfrastructureFailure(kind="quota", detail="synthetic quota failure")


class ExplodingEvaluator:
    def decide(self, context: object) -> EvaluatorDecision:
        raise AssertionError("infrastructure failure must stop before evaluator input")


def scenario() -> Scenario:
    return Scenario(
        schema_version=1,
        identifier="synthetic",
        title="Synthetic cap",
        domain="conceptual",
        initial_goal="Synthetic initial goal",
        persona={
            "knowledge": ("Synthetic knowledge.",),
            "misconception": "Synthetic misconception.",
            "communication_style": ("Answers briefly.",),
            "allowed_progress": ("May revise after evidence.",),
            "forbidden_behavior": ("Must not reveal hidden answers.",),
        },
        observable_outcome=("Demonstrates a synthetic outcome.",),
        response_policy=("Respond to the latest tutor turn.",),
        max_learner_responses=15,
    )


def identity() -> ProtocolIdentity:
    return ProtocolIdentity(
        repository_commit="0" * 40,
        protocol_version="1.0.0",
        bundle_sha256="a" * 64,
    )


class EvaluationSessionTests(unittest.TestCase):
    def test_bootstrap_does_not_consume_response_budget(self) -> None:
        tutor = FakeTutor()
        evaluator = type(
            "Evaluator",
            (),
            {
                "decide": lambda self, context: EvaluatorDecision(
                    action="respond",
                    response=f"learner-{len(context.learner_responses) + 1}",
                    stop_reason=None,
                )
            },
        )()
        record = run_session(
            scenario=scenario(),
            tutor=tutor,
            evaluator=evaluator,
            identity=identity(),
            initial_request="Synthetic public-launcher bootstrap.",
            run_id="cap-test",
        )
        self.assertEqual(15, record.learner_response_count)
        self.assertEqual("maximum_learner_responses", record.stop_reason)
        self.assertEqual(16, len(tutor.messages))
        self.assertEqual("Synthetic public-launcher bootstrap.", tutor.messages[0])

    def test_infrastructure_failure_has_no_pedagogy_score(self) -> None:
        record = run_session(
            scenario=scenario(),
            tutor=FailingTutor(),
            evaluator=ExplodingEvaluator(),
            identity=identity(),
            initial_request="Synthetic public-launcher bootstrap.",
            run_id="infrastructure-test",
        )
        self.assertEqual("infrastructure_failure", record.stop_reason)
        self.assertEqual("quota", record.infrastructure_failure)
```

- [ ] **Step 2: Run tests and verify the missing session module**

Run:

```powershell
python -m unittest tests.test_evaluation_session -v
```

Expected: import failure for `evaluation.session`.

- [ ] **Step 3: Implement the manual evaluator boundary**

The live `ConsoleEvaluator` emits the display with concrete runtime values:

```python
output.write(
    f"Scenario: {context.scenario.title}\n"
    f"Learner responses used: {len(context.learner_responses)}/15\n"
    "Tutor turn:\n"
    f"{context.tutor_turns[-1].text}\n\n"
    "Choose: respond | outcome | completion-without-evidence | critical-failure\n"
)
```

For `respond`, it reads one learner message from the implementing agent. Empty responses are rejected. For stop choices, it maps to the exact `StopReason`. The context display includes persona knowledge, misconception, allowed progress, forbidden behavior, and response policy on every turn so the evaluator remains faithful.

There is no callable, configuration key, or command-line flag for a learner model. A scripted evaluator class may exist only inside `tests/`.

Stop precedence is:

1. infrastructure failure;
2. observable outcome;
3. completion without evidence;
4. critical pedagogical failure;
5. automatic 15-response cap.

Send `initial_request` once before asking the evaluator for any response. The
private CLI computes it with
`initial_bootstrap(layout.protocol, scenario.initial_goal)`, so the first
stream request exactly matches the public Antigravity launcher's protocol-path
and initial-objective bootstrap. It is recorded as the setup turn but does not
count as an adaptive learner response.

After each tutor turn, allow the evaluator to select a stop reason before
enforcing the response cap. If the evaluator selects `respond`, enforce:

```python
if len(learner_responses) >= scenario.max_learner_responses:
    return replace(
        record,
        stop_reason="maximum_learner_responses",
        learner_response_count=len(learner_responses),
    )
```

When `record_path` is provided, require it to resolve under `.semantic-runs/`
and write the unsanitized run record there with `write_private`. The live CLI
passes `layout.run_dir / "run-record.json"`, which equals
`layout.raw.parent / "run-record.json"` and is internal; tests may leave
`record_path` as `None`.

`execute_isolated_run` owns the external runtime lifecycle. It saves the private record first and then cleans up, with every cleanup step isolated so that one failing step cannot skip the others:

```python
progress = SessionProgress(turns=[], learner_response_count=0)
record_path = layout.run_dir / "run-record.json"
tutor = None
started = False
primary: BaseException | None = None
try:
    tutor = tutor_factory(layout)
    tutor.start()
    started = True
    return run_session(
        scenario, tutor, evaluator, identity,
        initial_bootstrap(layout.protocol, scenario.initial_goal), run_id,
        record_path=record_path, progress=progress,
    )
except BaseException as error:  # includes KeyboardInterrupt
    primary = error
    _save_failure_evidence(
        layout=layout, record_path=record_path, error=error, progress=progress,
        phase="session" if started else "start",
        scenario=scenario, identity=identity, run_id=run_id, suite_id=suite_id,
        model_identifier=model_identifier, runtime_version=runtime_version,
    )
    raise
finally:
    failed_steps = []
    for name, step in (
        ("close", lambda: tutor.close() if tutor is not None else None),
        ("snapshot", lambda: snapshot_learner_records(layout)),
        ("remove-runtime", lambda: remove_runtime_root(layout, repository)),
    ):
        try:
            step()
        except Exception as cleanup_error:
            failed_steps.append(name)
            if primary is not None:
                primary.add_note(f"cleanup step {name} failed: {type(cleanup_error).__name__}")
    if failed_steps and primary is None:
        raise RuntimeCleanupError(failed_steps)
```

Rules:

- **Cleanup order and independence.** `close` flushes the raw input, output, and stderr under `layout.raw`. A `close` failure still runs `snapshot` and `remove-runtime`. A `snapshot` failure still runs `remove-runtime`. The external home and cwd are therefore removed on every path in which `remove_runtime_root` itself can succeed.
- **`_save_failure_evidence`** runs only on the exception path, before cleanup:
  1. Map the error to a rubric infrastructure class. `InfrastructureFailure` keeps its `kind`. Any other `Exception`, and `KeyboardInterrupt`, map to `"runtime"`. `run_session` already converts `InfrastructureFailure` raised during turns into a returned record, so this path covers start-up, unexpected, and interrupt errors.
  2. Call `infrastructure_record(scenario=scenario, identity=identity, run_id=run_id, suite_id=suite_id, runtime_version=runtime_version, model_identifier=model_identifier, kind=kind, progress=progress)`, using the explicit arguments passed to `execute_isolated_run`.
  3. Write it with `write_private(record_path, canonical_json(record), private_root=layout.run_dir)`, but only if `record_path` does not exist yet.
  4. Write `layout.run_dir / "failure.json"` containing only `{"exception_type": type(error).__name__, "phase": phase}`. `phase` is `"start"` when the factory or `start()` raised, and `"session"` afterwards. The exception message is not recorded, because it may contain paths.
  5. A failure inside `_save_failure_evidence` is added as a note on the primary error and never replaces it.
- **`infrastructure_record`** returns a JSON-serializable `dict[str, JsonValue]` with exactly the `RunRecord` keys:
  - `schema_version=1`, the given `run_id`, `suite_id`, and `scenario_id=scenario.identifier`;
  - the identity's commit, version, and hash;
  - `runtime="antigravity"`, the given `runtime_version` and `model_identifier`;
  - `learner_response_count=progress.learner_response_count`;
  - `stop_reason="infrastructure_failure"` and `infrastructure_failure=kind`;
  - `turns` built from `progress.turns` (completed turns only).

  A test round-trips it through `canonical_json` and `load_run_record`.
- **Preservation of original errors.** The primary exception is always re-raised unchanged. Cleanup and evidence failures are attached with `add_note` (Python 3.11+). `RuntimeCleanupError` is raised only when the session itself succeeded.
- **`KeyboardInterrupt`.** It is caught as `BaseException`, recorded as a `"runtime"` infrastructure record plus `failure.json`, cleaned up, and then re-raised. The CLI lets it propagate, so the process exits as interrupted. It is never converted into a pedagogy outcome.
- Raw streams are written incrementally by the adapter, so they are already saved before cleanup.

`verify_run_isolation(run_dir, repository)` reads only the private `run_dir / "runtime-context.json"` (via `load_runtime_context`) and `run-record.json`. It fails unless:

- the record exists;
- `runtime_outside_repository` and `local_rule_check_passed` are true, and `rule_boundary` is `"user_home"` or `"filesystem_root"`;
- the recorded `runtime_root` is outside the repository and no longer exists;
- `user_home_rule_paths` contains only `USER_HOME_RULE_PATHS` entries, and every `above_home_markers` entry has a positive level and a `RULE_MARKERS` name.

Add session tests with fake tutor factories and layouts from `create_run_layout` using injected `raw_root`, `runtime_base`, and `user_home`. Fake tutors implement `start()`, `send()`, and `close()` and expose `model` and `runtime_version`.

- **Success:** the record exists, `layout.runtime_root` is gone, and `layout.run_dir` remains.
- **`InfrastructureFailure` from `send`:** the infrastructure record exists and the runtime is gone.
- **Unexpected `RuntimeError` from `send` after two completed turns:** the same `RuntimeError` object is re-raised, the record has `infrastructure_failure == "runtime"` and the two completed turns, `failure.json` has `exception_type == "RuntimeError"`, and the runtime is gone.
- **`KeyboardInterrupt` from `send`:** `KeyboardInterrupt` is re-raised, the `"runtime"` record exists, and the runtime is gone.
- **`close()` raising after a successful session:** the snapshot was still taken, the runtime is gone, and `RuntimeCleanupError(["close"])` is raised.
- **`close()` raising after a failing session:** the original session error is re-raised with a `cleanup step close failed` note, and the runtime is gone.
- **Failing `snapshot_learner_records`:** the runtime is still removed.
- **`verify_run_isolation`:** it passes after a successful run, and fails while the runtime still exists, when the context reports a repository runtime, or when `local_rule_check_passed` is false.

- [ ] **Step 4: Wire private CLI preflight and single-session run**

`preflight` must validate:

- current branch is `feat/semantic-evaluation-runtime-ux`;
- contract fixture is valid;
- exact model file value equals the fixture model and appears in fresh `agy models`;
- `agy --version` matches the captured fixture version;
- checked-in protocol bytes equal `build_distribution(repository)` in memory;
- `git diff --exit-code -- core dist` succeeds;
- `.semantic-runs/` is ignored;
- no `.semantic-runs/` path is tracked.

`run` requires explicit arguments:

```text
python -m evaluation.cli run --suite-id 2026-11-06-antigravity-baseline --scenario conceptual-physics --model-file .semantic-runs/contract/model.txt
```

It must refuse an unknown scenario, a model argument not read from the validated model file, an existing run directory, or a dirty protocol. `run` executes in this order:

1. Run all prechecks with no runtime directory in existence: arguments, scenario, model file, contract fixture, and protocol identity (`capture_protocol_identity`, `assert_protocol_unchanged`).
2. Create the layout with live defaults immediately before execution: `create_run_layout(repository, suite_id, scenario_id)`. This puts raw evidence under `.semantic-runs/` and the per-run runtime in a fresh system temporary directory.
3. Call `execute_isolated_run(layout, repository, suite_id, scenario, lambda layout: AntigravitySession("agy", model, layout, contract, repository=repository, parent_environment=os.environ), ConsoleEvaluator(...), identity, run_id, model_identifier=model, runtime_version=agy_version)` with no prompt, network call, or other check in between. If anything raises between steps 2 and 3, call `remove_runtime_root(layout, repository)` before re-raising.
4. Run `verify_run_isolation(layout.run_dir, repository)` and exit non-zero if it fails.

`verify-isolation --suite-id SUITE --scenario SCENARIO` runs `verify_run_isolation` for one recorded scenario and prints `Runtime isolation verified.` It prints no absolute path, no marker content, and no environment value.

`run_session` itself still requires only `send()` plus the `model` and `runtime_version` attributes.

- [ ] **Step 5: Run session, isolation, and adapter tests**

Run:

```powershell
python -m unittest tests.test_evaluation_session tests.test_evaluation_isolation tests.test_evaluation_antigravity -v
```

Expected: all tests pass; no live runtime is invoked; every test runtime home/cwd is removed after its private record is saved, on success and failure paths.

- [ ] **Step 6: Commit**

```powershell
git add evaluation/session.py evaluation/cli.py tests/test_evaluation_session.py
git commit -m "feat: run manual adaptive evaluations"
```

---

### Task 8: Scoring, Findings, and Sanitized Report Rendering

**Files:**
- Create: `evaluation/scoring.py`
- Create: `evaluation/report.py`
- Create: `evaluation/fixtures/synthetic/session.json`
- Create: `tests/test_evaluation_report.py`

**Interfaces:**
- Produces: `validate_scorecard(scorecard: Scorecard, rubric: Rubric, record: RunRecord) -> None`
- Produces: `interactive_score(record: RunRecord, rubric: Rubric) -> Scorecard`
- Consumes: `RuleDisclosure`, `AboveHomeMarker`, `USER_HOME_RULE_PATHS`, `RULE_MARKERS`, and `load_runtime_context` from `evaluation.isolation`.
- Produces: `ScenarioRuntimeDisclosure(scenario_id: str, local_rule_check_passed: bool, rule_disclosure: RuleDisclosure)`. This is the report's only runtime-context input; it carries no paths.
- Produces: `render_baseline_report(records: Sequence[RunRecord], scorecards: Sequence[Scorecard], findings: Sequence[Finding], *, runtime_disclosures: Mapping[str, ScenarioRuntimeDisclosure], rules: Sequence[RedactionRule]) -> str`. `runtime_disclosures` is keyed by `scenario_id`. The private CLI `report` command builds it from each scenario's `load_runtime_context(run_dir)`, dropping `runtime_root`.
- Produces: `validate_baseline_report(text: str) -> None`
- Produces: `write_sanitized_report(path: Path, text: str) -> Path`

- [ ] **Step 1: Add an exact fictitious synthetic session fixture**

Create `evaluation/fixtures/synthetic/session.json`:

```json
{
  "schema_version": 1,
  "run_id": "synthetic-conceptual-physics",
  "suite_id": "synthetic-suite",
  "scenario_id": "conceptual-physics",
  "repository_commit": "0000000000000000000000000000000000000000",
  "protocol_version": "1.0.0",
  "protocol_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "runtime": "antigravity",
  "runtime_version": "synthetic",
  "model_identifier": "synthetic-model",
  "learner_response_count": 3,
  "stop_reason": "observable_outcome",
  "infrastructure_failure": null,
  "turns": [
    {
      "number": 1,
      "learner": "I think the heavier ball falls faster.",
      "tutor": "What would we need to compare fairly?"
    },
    {
      "number": 2,
      "learner": "The same shape and no air resistance.",
      "tutor": "Good. If force and mass both double, what happens to force divided by mass?"
    },
    {
      "number": 3,
      "learner": "The ratio stays the same, so acceleration stays the same.",
      "tutor": "Apply that to a bowling ball and a metal sphere in a vacuum."
    },
    {
      "number": 4,
      "learner": "They have equal acceleration because each object's larger force is matched by its larger mass.",
      "tutor": "That explanation and transfer meet the outcome."
    }
  ]
}
```

- [ ] **Step 2: Write failing score and report tests**

```python
# tests/test_evaluation_report.py
from __future__ import annotations

from dataclasses import replace
import unittest

from evaluation.isolation import AboveHomeMarker, RuleDisclosure
from evaluation.report import (
    ScenarioRuntimeDisclosure,
    render_baseline_report,
    validate_baseline_report,
)
from evaluation.schema import Finding, fixture_root, load_rubric, load_run_record
from evaluation.scoring import scorecard_from_mapping


def disclosure(
    user_home_rule_paths: tuple[str, ...] = (),
    above_home_markers: tuple[AboveHomeMarker, ...] = (),
    *,
    passed: bool = True,
) -> dict[str, ScenarioRuntimeDisclosure]:
    return {
        "conceptual-physics": ScenarioRuntimeDisclosure(
            scenario_id="conceptual-physics",
            local_rule_check_passed=passed,
            rule_disclosure=RuleDisclosure(
                boundary="user_home",
                user_home_rule_paths=user_home_rule_paths,
                above_home_markers=above_home_markers,
            ),
        )
    }


class EvaluationReportTests(unittest.TestCase):
    def render(self, runtime_disclosures: dict[str, ScenarioRuntimeDisclosure]) -> str:
        rubric = load_rubric(fixture_root() / "rubric.json")
        record = load_run_record(fixture_root() / "synthetic/session.json")
        scorecard = scorecard_from_mapping(
            {
                "schema_version": 1,
                "scenario_id": "conceptual-physics",
                "categories": [
                    {
                        "identifier": category.identifier,
                        "score": 2,
                        "evidence_turns": [2, 3, 4],
                        "rationale": "Synthetic evidence demonstrates this category."
                    }
                    for category in rubric.categories
                ],
                "critical_failures": [],
            },
            rubric,
            record,
        )
        return render_baseline_report(
            [record],
            [scorecard],
            [
                Finding(
                    identifier="synthetic-finding",
                    classification="pedagogy",
                    scope="general",
                    scenario_ids=("conceptual-physics",),
                    evidence_turns=("conceptual-physics:2",),
                    summary="The synthetic tutor connected diagnosis to application.",
                    research_links=(
                        "https://consensus.app/papers/details/"
                        "0adf25e68b4d552aa18c5d2ea631170e/",
                    ),
                )
            ],
            runtime_disclosures=runtime_disclosures,
            rules=(),
        )

    def test_report_contains_exact_audit_sections_and_total(self) -> None:
        report = self.render(disclosure())
        validate_baseline_report(report)
        self.assertIn("Total: 16/16", report)
        self.assertIn("## General findings", report)
        self.assertIn("## Scenario-specific findings", report)
        self.assertIn("## Infrastructure results", report)

    def test_limitations_list_recorded_rule_names_only(self) -> None:
        report = self.render(
            disclosure(
                ("AGENTS.md", ".gemini/GEMINI.md"),
                (AboveHomeMarker(1, "CLAUDE.md"),),
            )
        )
        validate_baseline_report(report)
        limitations = report.split("## Baseline limitations", 1)[1]
        self.assertIn(
            "- conceptual-physics: user-home rule paths: AGENTS.md, .gemini/GEMINI.md; "
            "above-home markers: CLAUDE.md (1 level above home)",
            limitations,
        )
        self.assertIn("inherited with authentication", limitations)

    def test_limitations_state_none_when_nothing_was_recorded(self) -> None:
        report = self.render(disclosure())
        self.assertIn(
            "- conceptual-physics: user-home rule paths: none; above-home markers: none",
            report,
        )

    def test_report_rejects_missing_or_unsafe_runtime_disclosure(self) -> None:
        cases = {
            "missing scenario": {},
            "failed local check": disclosure(passed=False),
            "unknown user-home path": disclosure(("notes/rules.md",)),
            "unknown above-home marker": disclosure((), (AboveHomeMarker(1, "README.md"),)),
            "non-positive level": disclosure((), (AboveHomeMarker(0, "AGENTS.md"),)),
        }
        for label, runtime_disclosures in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                self.render(runtime_disclosures)

    def test_infrastructure_record_is_not_scored(self) -> None:
        rubric = load_rubric(fixture_root() / "rubric.json")
        record = replace(
            load_run_record(fixture_root() / "synthetic/session.json"),
            stop_reason="infrastructure_failure",
            infrastructure_failure="quota",
        )
        with self.assertRaisesRegex(ValueError, "infrastructure"):
            scorecard_from_mapping(
                {
                    "schema_version": 1,
                    "scenario_id": "conceptual-physics",
                    "categories": [
                        {
                            "identifier": category.identifier,
                            "score": 2,
                            "evidence_turns": [2],
                            "rationale": "Synthetic evidence."
                        }
                        for category in rubric.categories
                    ],
                    "critical_failures": [],
                },
                rubric,
                record,
            )
```

- [ ] **Step 3: Run tests and verify scoring/report modules are missing**

Run:

```powershell
python -m unittest tests.test_evaluation_report -v
```

Expected: import failures for `evaluation.report` and `evaluation.scoring`.

- [ ] **Step 4: Implement exact scorecard and finding validation**

Reuse `CategoryScore`, `Scorecard`, and `Finding` from `evaluation.schema`;
do not redeclare parallel dataclasses in `evaluation.scoring`. Each successful
pedagogy scorecard requires all eight categories exactly once, with the
following already-defined field contract:

```python
@dataclass(frozen=True)
class CategoryScore:
    identifier: str
    score: Literal[0, 1, 2]
    evidence_turns: tuple[int, ...]
    rationale: str


@dataclass(frozen=True)
class Scorecard:
    schema_version: int
    scenario_id: str
    categories: tuple[CategoryScore, ...]
    critical_failures: tuple[str, ...]

    @property
    def total(self) -> int:
        return sum(category.score for category in self.categories)
```

A category score requires at least one valid evidence turn and a non-empty rationale. Critical failure identifiers must come from the rubric. An infrastructure record must have no scorecard.

Each finding requires:

```python
@dataclass(frozen=True)
class Finding:
    identifier: str
    classification: FindingClass
    scope: Literal["general", "scenario-specific"]
    scenario_ids: tuple[str, ...]
    evidence_turns: tuple[str, ...]
    summary: str
    research_links: tuple[str, ...]
```

Pedagogy findings require at least one research link already present in the approved design specification. Runtime or infrastructure findings may use an empty research-link tuple.

- [ ] **Step 5: Implement deterministic minimum-quote report rendering**

The report begins:

```markdown
# Antigravity Semantic Baseline — 2026-11-06

## Evaluation identity
## Scenario results
## General findings
## Scenario-specific findings
## Infrastructure results
## Privacy statement
## Baseline limitations
```

`## Baseline limitations` is rendered only from `runtime_disclosures`.

- It contains one line per run record, in record order, exactly:

  ```text
  - <scenario_id>: user-home rule paths: <comma-separated paths or none>; above-home markers: <comma-separated "<marker> (<n> level(s) above home)" or none>
  ```

  Use `level` when `n == 1` and `levels` otherwise.
- It is followed by the sentence `User-level and above-home runtime rules were inherited with authentication; only their names were recorded, never their contents.`
- `render_baseline_report` raises `ValueError` when any of these hold:
  - a record's scenario has no disclosure;
  - `local_rule_check_passed` is false;
  - a user-home path is not in `USER_HOME_RULE_PATHS`;
  - an above-home marker is not in `RULE_MARKERS`, or its level is below 1.

  This keeps paths, contents, and invented names out of the report.

For each score, include score, rationale, and only the referenced learner/tutor turns. Deduplicate repeated quotations across categories. Reject quotations longer than 600 characters per turn and report text containing a forbidden literal or raw absolute home path.

The privacy statement must be exactly:

```text
Raw Antigravity streams, runtime logs, provider metadata, and evaluator notes remain only under ignored .semantic-runs/. Temporary learner homes and working directories were created outside the repository and deleted after private run records were saved. This tracked report contains fictitious scenario data and the minimum sanitized excerpts needed to justify its scores.
```

- [ ] **Step 6: Run report and schema tests**

Run:

```powershell
python -m unittest tests.test_evaluation_report tests.test_evaluation_schema tests.test_evaluation_sanitize -v
```

Expected: all tests pass and repeated rendering produces byte-identical output.

- [ ] **Step 7: Commit**

```powershell
git add evaluation/scoring.py evaluation/report.py evaluation/fixtures/synthetic/session.json tests/test_evaluation_report.py
git commit -m "feat: render sanitized baseline evidence"
```

---

### Task 9: Privacy, Repository, and Packaging Gates

**Files:**
- Create: `tests/test_evaluation_privacy.py`
- Modify: `tests/test_packaging.py`
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Consumes: tracked file list, wheel/sdist archives, contract fixture, and report validator.
- Produces: deterministic failures for tracked `.semantic-runs/`, missing ignore rule, a runtime home/cwd under `.semantic-runs/`, leaked raw/provider data, packaged evaluation code, or changed protocol bytes.
- Produces: `semantic_runtime_errors(root: Path) -> list[str]` in `tests/validate_repository.py`.

- [ ] **Step 1: Write failing privacy and package-exclusion tests**

```python
# tests/test_evaluation_privacy.py
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from evaluation.report import validate_baseline_report
from evaluation.sanitize import assert_tracked_safe


class EvaluationPrivacyTests(unittest.TestCase):
    def test_no_raw_semantic_run_is_tracked(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files", ".semantic-runs"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual([], tracked)

    def test_tracked_evaluation_assets_are_sanitized(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in sorted((root / "evaluation").rglob("*")):
            if path.is_file() and path.suffix in {".json", ".md", ".py"}:
                with self.subTest(path=path):
                    assert_tracked_safe(path.read_text(encoding="utf-8"), forbidden_literals=())

    def test_canonical_protocol_is_not_an_evaluation_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        evaluation_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "evaluation").rglob("*.py")
        )
        self.assertNotIn("write_distribution(", evaluation_text)
```

Add to `tests/test_packaging.py`:

```python
def test_published_archives_exclude_private_evaluation_system(self) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(
            [sys.executable, "-m", "build", "--outdir", temporary],
            cwd=root,
            check=True,
        )
        wheel = next(Path(temporary).glob("*.whl"))
        sdist = next(Path(temporary).glob("*.tar.gz"))
        with zipfile.ZipFile(wheel) as archive:
            self.assertFalse(
                any(
                    name.startswith("evaluation/") or ".semantic-runs/" in name
                    for name in archive.namelist()
                )
            )
        with tarfile.open(sdist, "r:gz") as archive:
            self.assertFalse(
                any(
                    "/evaluation/" in name or "/.semantic-runs/" in name
                    for name in archive.getnames()
                )
            )
```

- [ ] **Step 2: Run focused tests and observe validator gaps**

Run:

```powershell
python -m unittest tests.test_evaluation_privacy tests.test_packaging tests.test_validate_repository -v
```

Expected: privacy/package tests expose missing validator enforcement for the new raw-run boundary.

- [ ] **Step 3: Add repository validation rules**

In `tests/validate_repository.py`, require:

```python
if "/.semantic-runs/" not in rules:
    errors.append(".gitignore must ignore /.semantic-runs/")

tracked_semantic_raw = sorted(
    path for path in tracked if path.startswith(".semantic-runs/")
)
if tracked_semantic_raw:
    errors.append(
        "Tracked raw semantic evaluation files: " + ", ".join(tracked_semantic_raw)
    )
```

Also validate every tracked file under `evaluation/fixtures/antigravity/` and `evaluation/reports/` with the same forbidden credential/path patterns as `assert_tracked_safe`. Do not read ignored `.semantic-runs/` file contents.

Add a deterministic runtime-placement check that inspects directory *names* only and reads no file contents:

```python
RUNTIME_WORKSPACE_MARKERS = (".socratic-learn",)


def semantic_runtime_errors(root: Path) -> list[str]:
    raw_root = root / ".semantic-runs"
    if not raw_root.is_dir():
        return []
    errors = []
    for directory, subdirectories, _ in os.walk(raw_root, followlinks=False):
        relative = Path(directory).relative_to(raw_root).as_posix()
        names = set(subdirectories)
        if names & set(RUNTIME_WORKSPACE_MARKERS) or (
            Path(directory).name == "home" and "learning" in names
        ):
            errors.append(f"Runtime home/cwd under .semantic-runs: {relative}")
    return sorted(errors)
```

Call it from the validator's main error collection. It returns no error when `.semantic-runs/` is absent, as in CI, so the check is deterministic on every checkout.

Add mutation tests to `tests/test_validate_repository.py`. Each must produce the exact error above:

- removing the ignore rule;
- force-adding `.semantic-runs/raw.ndjson`;
- creating `.semantic-runs/suite/scenario/home/learning/` in a temporary repository copy;
- creating `.semantic-runs/suite/scenario/learning/.socratic-learn/` in a temporary repository copy.

Also add a test that a raw-only tree (`.semantic-runs/suite/scenario/raw/output.ndjson`, `runtime-context.json`, `learner-records/progress.md`) produces no runtime-placement error.

- [ ] **Step 4: Run all privacy and package gates**

Run:

```powershell
python -m unittest tests.test_evaluation_privacy tests.test_packaging tests.test_validate_repository -v
python tests/validate_repository.py
git ls-files .semantic-runs
```

Expected: all tests pass, repository validation prints `Repository validation passed.`, and `git ls-files .semantic-runs` prints nothing.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_evaluation_privacy.py tests/test_packaging.py tests/validate_repository.py tests/test_validate_repository.py
git commit -m "test: gate semantic evidence privacy"
```

---

### Task 10: Launcher-Parity and Deterministic Full Gate

**Files:**
- Modify: `tests/test_evaluation_antigravity.py`
- Modify: `tests/test_evaluation_isolation.py`
- Modify: `tests/test_evaluation_report.py`

**Interfaces:**
- Consumes: existing `ADAPTERS["antigravity"]`, `command_for`, `prepare_personal_workspace`, and in-memory distribution build.
- Verifies: evaluation initial bootstrap and protocol bytes are identical to the unchanged public launcher path.

- [ ] **Step 1: Add a failing bootstrap-parity test**

```python
def test_evaluation_initial_message_matches_public_antigravity_bootstrap(self) -> None:
    from pathlib import Path
    from socratic_learn.hosts import ADAPTERS, command_for
    from evaluation.antigravity import initial_bootstrap

    protocol = Path("C:/isolated/.socratic-learn/socratic-learn.prompt.md")
    goal = "learn cafés"
    public = command_for(
        ADAPTERS["antigravity"],
        "agy",
        protocol,
        goal,
    )
    self.assertEqual(public[2], initial_bootstrap(protocol, goal))
```

The `initial_bootstrap` implementation created in Task 6 must continue to call
the existing `command_for`; this parity task must not replace it with duplicated
bootstrap text.

Add an external-runtime parity test that does not use the real checkout for
runtime or raw state. The real repository remains only the canonical source
for `build_distribution`; a temporary repository owns an ignored
`.semantic-runs/` tree and is destroyed with the test:

```python
def test_external_layout_bootstrap_and_protocol_match_public_launcher(self) -> None:
    import tempfile
    from pathlib import Path
    from evaluation.antigravity import initial_bootstrap
    from evaluation.isolation import create_run_layout, remove_runtime_root
    from socratic_learn.build import build_distribution
    from socratic_learn.hosts import ADAPTERS, command_for

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as repository_base, tempfile.TemporaryDirectory() as runtime_base:
        repository = Path(repository_base) / "repo"
        repository.mkdir()
        (repository / ".gitignore").write_text("/.semantic-runs/\n", encoding="utf-8")
        layout = create_run_layout(
            repository,
            "suite",
            "conceptual-physics",
            raw_root=repository / ".semantic-runs",
            runtime_base=Path(runtime_base),
            user_home=Path(runtime_base),
        )
        try:
            self.assertFalse(layout.cwd.resolve().is_relative_to(root))
            self.assertFalse(layout.cwd.resolve().is_relative_to(repository))
            self.assertEqual(build_distribution(root).bundle, layout.protocol.read_bytes())
            goal = "learn cafés"
            public = command_for(ADAPTERS["antigravity"], "agy", layout.protocol, goal)
            self.assertEqual(public[2], initial_bootstrap(layout.protocol, goal))
        finally:
            remove_runtime_root(layout, repository)
```

- [ ] **Step 2: Add protocol-identity and report-triplet tests**

Assert:

```python
self.assertEqual(
    (root / "dist/socratic-learn.prompt.md").read_bytes(),
    build_distribution(root).bundle,
)
self.assertEqual(
    {
        "conceptual-physics",
        "practical-programming",
        "communication-writing",
    },
    {record.scenario_id for record in records},
)
self.assertEqual(1, len({record.model_identifier for record in records}))
```

The report validator must reject duplicate scenario records, a missing scenario, differing model identifiers, or differing protocol hashes.

- [ ] **Step 3: Run the complete deterministic local gate**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
python -m evaluation.cli preflight --model-file .semantic-runs/contract/model.txt
python -m build --outdir package-dist
git diff --exit-code -- core dist
git diff --check
```

Expected:

- all unit tests pass;
- repository validation passes;
- preflight prints the branch, commit, protocol version/hash, Antigravity version, and explicit model without printing authentication data;
- parity holds with an external runtime cwd/home, without a repository cwd;
- wheel and sdist exclude `evaluation/` and `.semantic-runs/`;
- canonical protocol files have no diff.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_evaluation_antigravity.py tests/test_evaluation_isolation.py tests/test_evaluation_report.py
git commit -m "test: verify evaluation launcher parity"
```

---

### Task 11: Three Unchanged-Protocol Baseline Sessions and Evidence Report

**Files:**
- Create privately: `.semantic-runs/2026-11-06-antigravity-baseline/**` (raw evidence, run records, runtime context, learner-record snapshots, evaluator notes; never runtime homes or working directories)
- Create and delete ephemerally: one external runtime home/cwd per scenario in the system temporary location, outside the repository
- Create: `evaluation/reports/2026-11-06-antigravity-baseline.md`

**Interfaces:**
- Consumes: the same captured explicit model, unchanged protocol identity, three scenario fixtures, manual implementing-agent responses, and rubric.
- Produces: exactly three run records, zero to three scorecards depending on infrastructure outcomes, classified findings, and one sanitized tracked report.

- [ ] **Step 1: Record the immutable baseline identity**

Run:

```powershell
git branch --show-current
git rev-parse HEAD
python -m evaluation.cli preflight --model-file .semantic-runs/contract/model.txt
git diff --exit-code -- core dist
```

Expected: branch is `feat/semantic-evaluation-runtime-ux`; preflight succeeds; protocol version/hash and the selected model are recorded under `.semantic-runs/2026-11-06-antigravity-baseline/identity.json`; canonical protocol files have no diff.

- [ ] **Step 2: Run the conceptual-physics baseline once**

Run:

```powershell
python -m evaluation.cli run `
  --suite-id 2026-11-06-antigravity-baseline `
  --scenario conceptual-physics `
  --model-file .semantic-runs/contract/model.txt
```

The implementing agent reads every tutor turn and supplies the next learner response according to the persona and response policy. It must not use another model or prewritten response sequence. Stop at the first applicable stop condition.

Then run:

```powershell
python -m evaluation.cli verify-isolation --suite-id 2026-11-06-antigravity-baseline --scenario conceptual-physics
```

Expected: one private run record with at most 15 adaptive learner responses after the public-launcher-equivalent initial bootstrap; raw input/output/stderr remains under the scenario's ignored run directory; `verify-isolation` prints `Runtime isolation verified.`, which confirms the runtime cwd/home was external, no local rule marker existed in its ancestors below the user home, and the external directory has been deleted.

- [ ] **Step 3: Run the practical-programming baseline once**

Run:

```powershell
python -m evaluation.cli run `
  --suite-id 2026-11-06-antigravity-baseline `
  --scenario practical-programming `
  --model-file .semantic-runs/contract/model.txt
```

Then run `python -m evaluation.cli verify-isolation --suite-id 2026-11-06-antigravity-baseline --scenario practical-programming`.

Expected: one private run record using the identical model and protocol identity, with no reuse of the first scenario's home or working directory; `verify-isolation` prints `Runtime isolation verified.`

- [ ] **Step 4: Run the communication-writing baseline once**

Run:

```powershell
python -m evaluation.cli run `
  --suite-id 2026-11-06-antigravity-baseline `
  --scenario communication-writing `
  --model-file .semantic-runs/contract/model.txt
```

Then run `python -m evaluation.cli verify-isolation --suite-id 2026-11-06-antigravity-baseline --scenario communication-writing`.

Expected: one private run record using the identical model and protocol identity, with no reuse of either earlier home or working directory; `verify-isolation` prints `Runtime isolation verified.`

- [ ] **Step 5: Score successful sessions and classify all findings**

Run:

```powershell
python -m evaluation.cli score --suite-id 2026-11-06-antigravity-baseline
```

For each non-infrastructure session, the implementing agent enters one score per rubric category, evidence turn numbers, rationale, and any critical failure. For every observed issue, classify it as `pedagogy`, `launcher_ux`, `documentation`, `runtime`, or `infrastructure`, and as `general` or `scenario-specific`. Pedagogy findings must cite both transcript evidence and at least one research reference from the approved design. Infrastructure sessions are classified but not scored.

Expected: private exact-key scorecards and findings are saved under the suite directory; all evidence turn references exist.

- [ ] **Step 6: Generate and validate the sanitized report**

Run:

```powershell
python -m evaluation.cli report `
  --suite-id 2026-11-06-antigravity-baseline `
  --output evaluation/reports/2026-11-06-antigravity-baseline.md
python -m evaluation.cli validate-report evaluation/reports/2026-11-06-antigravity-baseline.md
python -m unittest tests.test_evaluation_report tests.test_evaluation_privacy -v
git check-ignore --quiet .semantic-runs/2026-11-06-antigravity-baseline/identity.json
git ls-files .semantic-runs
```

Expected:

- report validation prints `Semantic baseline report is valid.`;
- the report identifies date, run IDs, commit, protocol version/hash, Antigravity version, exact model, scenario stop conditions, scores/evidence where applicable, critical failures, infrastructure failures, and general versus scenario-specific findings;
- quotations are minimal and sanitized;
- the baseline limitations list each scenario's user-home-relative rule paths and above-home marker names (or none) and contain no rule contents or absolute paths;
- raw records remain ignored and untracked;
- `git ls-files .semantic-runs` prints nothing.

- [ ] **Step 7: Run the post-evidence deterministic gate and commit only the report**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
git diff --exit-code -- core dist
git diff --check
git status --short
```

Expected: all deterministic gates pass, including `semantic_runtime_errors` (no runtime home/cwd under the populated `.semantic-runs/`); protocol files remain unchanged; `.semantic-runs/` is absent from status; the only new live-evidence artifact is the sanitized report.

Commit:

```powershell
git add evaluation/reports/2026-11-06-antigravity-baseline.md
git commit -m "docs: record antigravity semantic baseline"
```

---

### Task 12: Evidence-Derived Protocol-Change and Rerun Plan

**Files:**
- Read: `evaluation/reports/2026-11-06-antigravity-baseline.md`
- Create: `docs/superpowers/plans/2026-11-06-semantic-protocol-changes.md`
- Do not modify: product code, `core/*.md`, `dist/*`, launcher files, or runtime documentation.

**Interfaces:**
- Consumes: only sanitized baseline findings, approved research references, and current deterministic tests.
- Produces: a separate implementation plan for evidence-supported protocol changes, deterministic regression tests, and the three post-change reruns with the same scenarios/runtime/model.

- [ ] **Step 1: Re-read the planning skill, approved design, and sanitized evidence**

Run:

```powershell
Get-Content C:\Users\Marcos\.cursor\plugins\cache\cursor-public\superpowers\d884ae04edebef577e82ff7c4e143debd0bbec99\skills\writing-plans\SKILL.md
Get-Content docs/superpowers/specs/2026-11-06-semantic-evaluation-runtime-ux-design.md
Get-Content evaluation/reports/2026-11-06-antigravity-baseline.md
```

Expected: the implementing agent can identify every proposed change's report finding, transcript evidence reference, classification, scope, and research support.

- [ ] **Step 2: Write the evidence-derived implementation plan**

Create `docs/superpowers/plans/2026-11-06-semantic-protocol-changes.md` with the mandatory writing-plans header and these exact constraints:

- include only generalizable pedagogy changes supported by baseline evidence and the approved research basis;
- do not encode answers to any of the three scenarios;
- create a focused deterministic regression test before each protocol change;
- preserve all repository, package, native, and privacy invariants;
- rebuild deterministic protocol artifacts only after source changes;
- rerun the same three scenarios with Antigravity and the exact baseline model identifier;
- use separate external ephemeral homes and working directories outside the repository, with the same local rule-ancestor rejection and `verify-isolation` checks;
- retain the 15-message cap and unchanged evaluator personas;
- compare every category and aggregate against baseline;
- require no critical failure, at least 12/16 per scenario, and no zero category;
- permit one labeled rerun only for a category regression or inconsistent result, with written analysis;
- include an explicit unresolved-limitation path when the target is not met;
- state that no release, tag, or publication is authorized.

Every task in the new plan must cite one or more finding identifiers from the sanitized report. If the baseline contains no generalizable pedagogy finding, the plan must state that protocol bytes remain unchanged and scope post-change work to deterministic evidence gaps and confirmatory reruns rather than inventing a protocol change.

- [ ] **Step 3: Validate that the new plan is evidence-linked and contains no product edit**

Run:

```powershell
python -c "from pathlib import Path; p=Path('docs/superpowers/plans/2026-11-06-semantic-protocol-changes.md'); t=p.read_text(encoding='utf-8'); assert t.startswith('# '); assert 'REQUIRED SUB-SKILL' in t; assert 'evaluation/reports/2026-11-06-antigravity-baseline.md' in t; assert 'no release, tag, or publication' in t.lower()"
git diff --exit-code -- core dist socratic_learn README.md docs/launcher-adapters.md docs/universal-installation.md
git diff --check
```

Expected: plan structure assertions pass, no product/protocol/runtime-documentation file changed, and the diff is whitespace-clean.

- [ ] **Step 4: Commit the follow-on plan**

```powershell
git add docs/superpowers/plans/2026-11-06-semantic-protocol-changes.md
git commit -m "docs: plan evidence-led protocol changes"
```

---

## Completion Gate

This subproject is complete only when all of the following are true:

1. the deterministic evaluation suites and full repository validator pass;
2. the observed Antigravity stream-json contract and exact model are captured without an invented wire format;
3. `evaluation/` remains absent from wheel, source distribution, native executable inputs, and public commands;
4. `.semantic-runs/` is ignored, contains every raw artifact, has no tracked path, and contains no runtime home or working directory;
5. the three scenarios ran exactly once each with Antigravity, one explicit model, unchanged protocol bytes, separate external `SOCRATIC_LEARN_HOME` values, separate external working directories, inherited authentication, sandboxing, and no more than 15 adaptive learner responses after the initial objective bootstrap;
6. `verify-isolation` passed for all three scenarios: each runtime cwd/home was outside the repository, no repository or local rule marker (`AGENTS.md`, `GEMINI.md`, `CLAUDE.md`, `.agents/`, `.agent/`) existed in its ancestors below the boundary recorded in its runtime context, each runtime context records `local_rule_check_passed: true`, each external directory was deleted after its private record was saved, `tests/validate_repository.py` reports no runtime home/cwd under `.semantic-runs/`, and user-home-relative rule paths and above-home marker names are reported as limitations;
7. the implementing agent—not another model—acted as the adaptive learner evaluator;
8. the tracked baseline report validates, contains only sanitized minimum evidence, and separates infrastructure from pedagogy;
9. `core/*.md`, public launcher UX, runtime documentation, and protocol bytes have no diff;
10. the evidence-derived follow-on implementation plan exists and proposes no unsupported or scenario-specific protocol change;
11. no release, tag, package publication, GitHub Release, or PyPI publication occurred.
