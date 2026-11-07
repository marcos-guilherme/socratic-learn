from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from socratic_learn.build import CANONICAL_SOURCES, build_distribution
from socratic_learn.conformance import (
    CONFORMANCE_CONTRACT_VERSION,
    REQUIRED_DIAGNOSTIC_CODES,
    check_conformance,
)
from socratic_learn.errors import IntegrityError


SOURCE_CONTENTS = {
    "core/pedagogy.md": """# Pedagogy

## Vocabulary readiness and concept ramp

Require vocabulary readiness. The learner used it correctly, demonstrated the
underlying idea, or the tutor introduced it in plain language. Avoid hidden
prerequisites.

## Connected perspectives

Use one primary explanation and up to two additional perspectives. Explicitly
connect the views.

## Productive effort and graduated support

Require a learner attempt before a complete solution. Use paper and pen when
useful. Do not include the solution with the task. Give a small cue, then an
alternative representation or simpler case, then a direct explanation, then a
new application.

## Silent self-review

Before teaching, run a silent self-review for alignment with the learner-owned
objective, prerequisite evidence, vocabulary readiness and cognitive load, the
smallest useful next step, whether a perspective contributes distinct value,
whether factual currency or uncertainty requires research, and whether the
response asks the learner to make a decision they lack the basis to evaluate.
Do not narrate this silent self-review.

## Responsive Socratic dialogue

Use Socratic mode when the next step is discoverable. Each question derives
from the learner's preceding answer.

Use direct exposition when essential information is not deducible. After
exposition, return control through an active application or an active question.
""",
    "core/session-protocol.md": """# Session Protocol

## Natural learner-facing conversation

Keep protocol orchestration internal. Do not announce stage names, diagnostic
budgets, or question counters unless the learner explicitly asks.

## 1. Define an observable outcome

Convert the objective into a performance that can be observed in this session.

## 2. Diagnose relevant prerequisites

Inspect only prerequisites that could block the outcome.

## 3. Build and preview the learning route

The tutor owns technical route selection. Do not ask the learner to validate a
technical sequence. Give a brief preview in ordinary language and begin
teaching without formal approval. The learner may redirect at any time.

## 4. Teach one node at a time

Teach one route step at a time.

## 5. Close and persist

Close with diagnostic evidence, application evidence, and remaining gaps.
Keep real learner data under `workspace/` and out of version control.

## Capability fallbacks

Without structured quiz support, ask one question at a time in conversation.
Without web access, mark volatile claims unverified.
Without filesystem access, return the complete session record as Markdown.
Without subagents or parallel work, research and teach sequentially.
Without diagram rendering, use Mermaid or a textual edge list.
Without cross-session memory, ask for a prior summary.
""",
    "core/assessment.md": """# Assessment

## Diagnostic budget

Use at most six diagnostic questions by default. Stop early when the evidence
is sufficient to propose a path.
""",
    "core/evidence-policy.md": """# Evidence Policy

## Mathematical claims

For each material mathematical claim, state its domain and hypotheses and
classify it as a definition, theorem, consequence, approximation, heuristic,
or empirical observation.

## Volatile technical claims

Verify each consequential volatile claim against a primary source before
presenting it as current.

## Autonomous current-information research

Search autonomously for consequential current, volatile, disputed, or uncertain
claims. Prefer primary sources and include date or version context. External
queries must exclude private learner data.

## No-web fallback

When research tools are unavailable, the no-web fallback continues with stable
material.
""",
    "curricula/mathematics/map.md": "# Mathematics\n\n### algebra — Algebra\n",
    "curricula/ai/map.md": "# AI\n\n### learning — Learning\n",
}


def minimal_bundle() -> str:
    sections = ["# Socratic Learn"]
    for relative in CANONICAL_SOURCES:
        sections.extend(
            (
                f"<!-- source:{relative} -->",
                SOURCE_CONTENTS[relative].strip(),
                f"<!-- /source:{relative} -->",
            )
        )
    return "\n".join(sections) + "\n"


class ConformanceTests(unittest.TestCase):
    def assert_only_code(self, bundle: str, expected: str) -> None:
        diagnostics = check_conformance(bundle)

        self.assertEqual([expected], [diagnostic.code for diagnostic in diagnostics])
        diagnostic = diagnostics[0]
        self.assertTrue(diagnostic.path)
        self.assertTrue(diagnostic.message)
        self.assertTrue(diagnostic.remediation)

    def test_minimal_behavioral_bundle_conforms(self) -> None:
        self.assertEqual([], check_conformance(minimal_bundle()))

    def test_requires_observable_outcome(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("performance that can be observed", "goal"),
            "observable-outcome",
        )

    def test_requires_bounded_diagnosis(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("at most six diagnostic questions", "questions"),
            "bounded-diagnosis",
        )

    def test_requires_silent_orchestration(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Keep protocol orchestration internal.",
                "Describe every protocol stage.",
            ),
            "silent-orchestration",
        )

    def test_requires_vocabulary_readiness(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "The learner used it correctly, demonstrated the\n"
                "underlying idea, or the tutor introduced it in plain language.",
                "Use domain terminology immediately.",
            ),
            "vocabulary-readiness",
        )

    def test_requires_connected_perspectives(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Explicitly\nconnect the views.",
                "List several views.",
            ),
            "connected-perspectives",
        )

    def test_requires_productive_effort(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Require a learner attempt before a complete solution.",
                "Give the complete solution first.",
            ),
            "productive-effort",
        )

    def test_requires_graduated_support(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Give a small cue, then an\n"
                "alternative representation or simpler case, then a direct "
                "explanation, then a\nnew application.",
                "Repeat the same question.",
            ),
            "graduated-support",
        )

    def test_requires_agent_led_route(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "The tutor owns technical route selection.",
                "The learner chooses the technical sequence.",
            ),
            "agent-led-route",
        )

    def test_requires_silent_self_review(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Do not narrate this silent self-review.",
                "Narrate every internal review.",
            ),
            "silent-self-review",
        )

    def test_requires_autonomous_current_research(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Search autonomously for consequential current, volatile, disputed, "
                "or uncertain\nclaims.",
                "Wait for the learner to request research.",
            ),
            "autonomous-current-research",
        )

    def test_requires_responsive_socratic_follow_up(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Each question derives\nfrom the learner's preceding answer.",
                "Ask a fixed sequence of questions.",
            ),
            "responsive-socratic-follow-up",
        )

    def test_requires_exposition_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Use direct exposition when essential information is not deducible.",
                "Continue asking questions.",
            ),
            "exposition-fallback",
        )

    def test_requires_active_return_after_exposition(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "After\nexposition, return control through an active application or an active question.",
                "After exposition, continue explaining.",
            ),
            "active-return-after-exposition",
        )

    def test_requires_mathematical_assumptions_and_classification(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "state its domain and hypotheses and\nclassify it as a definition, theorem, consequence, approximation, heuristic,\nor empirical observation",
                "describe it",
            ),
            "mathematical-assumptions-classification",
        )

    def test_requires_primary_source_verification_for_volatile_claims(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Verify each consequential volatile claim against a primary source "
                "before\npresenting it as current.",
                "Recall volatile claims from memory.",
            ),
            "volatile-primary-source-verification",
        )

    def test_requires_structured_quiz_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("structured quiz support", "assessment feature"),
            "capability-fallbacks",
        )

    def test_requires_web_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("web access", "network access"),
            "capability-fallbacks",
        )

    def test_requires_filesystem_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("filesystem access", "persistent storage"),
            "capability-fallbacks",
        )

    def test_requires_subagent_or_parallelism_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("subagents or parallel work", "extra workers"),
            "capability-fallbacks",
        )

    def test_requires_diagram_or_rendering_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("diagram rendering", "visual tool"),
            "capability-fallbacks",
        )

    def test_requires_cross_session_memory_fallback(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("cross-session memory", "saved context"),
            "capability-fallbacks",
        )

    def test_requires_private_state_protection(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("and out of version control", ""),
            "private-state",
        )

    def test_requires_evidence_based_closure(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace("application evidence", "a summary"),
            "evidence-based-closure",
        )

    def test_diagnostics_have_deterministic_code_path_order(self) -> None:
        bundle = minimal_bundle().replace("against a primary source", "from memory")
        bundle = bundle.replace("performance that can be observed", "goal")

        diagnostics = check_conformance(bundle)

        observed = [(diagnostic.code, diagnostic.path) for diagnostic in diagnostics]
        self.assertEqual(sorted(observed), observed)

    def test_build_rejects_nonconforming_sources_with_actionable_diagnostics(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)
        protocol = root / "core/session-protocol.md"
        protocol.write_text(
            protocol.read_text(encoding="utf-8").replace(
                "performance that can be observed",
                "goal",
            ),
            encoding="utf-8",
        )

        with self.assertRaises(IntegrityError) as raised:
            build_distribution(root)

        self.assertIn("observable-outcome", str(raised.exception))
        self.assertEqual("dist/socratic-learn.prompt.md", str(raised.exception.path))
        self.assertTrue(raised.exception.remediation)

    def test_manifest_records_contract_version_and_required_codes(self) -> None:
        temporary, root = self.make_repository()
        self.addCleanup(temporary.cleanup)

        manifest = json.loads(build_distribution(root).manifest)

        self.assertEqual(
            {
                "version": CONFORMANCE_CONTRACT_VERSION,
                "required_diagnostic_codes": list(REQUIRED_DIAGNOSTIC_CODES),
            },
            manifest["conformance"],
        )

    def make_repository(self) -> tuple[TemporaryDirectory, Path]:
        temporary = TemporaryDirectory()
        root = Path(temporary.name)
        for relative, content in SOURCE_CONTENTS.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        return temporary, root


if __name__ == "__main__":
    unittest.main()
