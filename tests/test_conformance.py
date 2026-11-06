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

## Responsive Socratic dialogue

Use Socratic mode when the next step is discoverable. Each question derives
from the learner's preceding answer.

Use direct exposition when essential information is not deducible. After
exposition, return control through an active application or an active question.
""",
    "core/session-protocol.md": """# Session Protocol

## 1. Define an observable outcome

Convert the objective into a performance that can be observed in this session.

## 2. Diagnose relevant prerequisites

Inspect only prerequisites that could block the outcome.

## 3. Present and approve a dependency path

Do not begin teaching until the learner approves or adjusts the path.

## 4. Teach one node at a time

Teach one approved node at a time.

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
""",
    "curricula/mathematics/map.md": "# Mathematics\n\n### algebra — Algebra\n",
    "curricula/ai/map.md": "# AI\n\n### learning — Learning\n",
}


def minimal_bundle() -> str:
    sections = ["# Universal Learning Tutor"]
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

    def test_requires_explicit_plan_approval_gate(self) -> None:
        self.assert_only_code(
            minimal_bundle().replace(
                "Do not begin teaching until the learner approves or adjusts the path.",
                "Present the path.",
            ),
            "plan-approval-before-teaching",
        )

    def test_requires_plan_approval_before_teaching_order(self) -> None:
        bundle = minimal_bundle()
        approval = "## 3. Present and approve a dependency path"
        gate = "Do not begin teaching until the learner approves or adjusts the path."
        teaching = (
            "## 4. Teach one node at a time\n\n"
            "Teach one approved node at a time."
        )
        bundle = bundle.replace(
            f"{approval}\n\n{gate}\n\n{teaching}",
            f"{approval}\n\n{teaching}\n\n{gate}",
        )

        self.assertIn(gate, bundle)

        self.assert_only_code(bundle, "plan-approval-before-teaching")

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
            minimal_bundle().replace("against a primary source", "from memory"),
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
        self.assertEqual("dist/learning-tutor.prompt.md", str(raised.exception.path))
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
