from __future__ import annotations

from dataclasses import replace
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from evaluation.isolation import AboveHomeMarker, RuleDisclosure
from evaluation.report import (
    LIMITATIONS_STATEMENT,
    PRIVACY_STATEMENT,
    ScenarioRuntimeDisclosure,
    render_baseline_report,
    validate_baseline_report,
    write_sanitized_report,
)
from evaluation.sanitize import RedactionRule
from evaluation.schema import Finding, fixture_root, load_rubric, load_run_record
from evaluation.scoring import interactive_score, scorecard_from_mapping, validate_scorecard


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
    def scorecard(self):
        rubric = load_rubric(fixture_root() / "rubric.json")
        record = load_run_record(fixture_root() / "synthetic/session.json")
        scorecard = scorecard_from_mapping(
            {
                "schema_version": 1,
                "scenario_id": record.scenario_id,
                "categories": [
                    {
                        "identifier": category.identifier,
                        "score": 2,
                        "evidence_turns": [2, 3, 4],
                        "rationale": "Synthetic evidence demonstrates this category.",
                    }
                    for category in rubric.categories
                ],
                "critical_failures": [],
            },
            rubric,
            record,
        )
        return rubric, record, scorecard

    def render(self, runtime_disclosures: dict[str, ScenarioRuntimeDisclosure]) -> str:
        _rubric, record, scorecard = self.scorecard()
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

    def test_scorecard_validation_rejects_invalid_evidence_and_categories(self) -> None:
        rubric, record, scorecard = self.scorecard()
        validate_scorecard(scorecard, rubric, record)
        cases = {
            "duplicate category": replace(
                scorecard,
                categories=scorecard.categories[:-1] + (scorecard.categories[0],),
            ),
            "missing evidence": replace(
                scorecard,
                categories=(
                    replace(scorecard.categories[0], evidence_turns=()),
                    *scorecard.categories[1:],
                ),
            ),
            "unknown turn": replace(
                scorecard,
                categories=(
                    replace(scorecard.categories[0], evidence_turns=(99,)),
                    *scorecard.categories[1:],
                ),
            ),
            "blank rationale": replace(
                scorecard,
                categories=(
                    replace(scorecard.categories[0], rationale=" "),
                    *scorecard.categories[1:],
                ),
            ),
            "unknown critical failure": replace(
                scorecard,
                critical_failures=("not-approved",),
            ),
        }
        for label, invalid in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_scorecard(invalid, rubric, record)

    def test_interactive_score_collects_and_validates_all_categories(self) -> None:
        rubric, record, _scorecard = self.scorecard()
        answers: list[str] = []
        for _category in rubric.categories:
            answers.extend(("2", "2,3,4", "Synthetic rationale."))
        answers.append("")
        with mock.patch("builtins.input", side_effect=answers):
            scorecard = interactive_score(record, rubric)
        self.assertEqual(16, scorecard.total)
        validate_scorecard(scorecard, rubric, record)

    def test_render_is_deterministic_deduplicated_and_sanitized(self) -> None:
        first = self.render(disclosure())
        second = self.render(disclosure())
        self.assertEqual(first.encode(), second.encode())
        self.assertEqual(1, first.count("> Learner: The same shape and no air resistance."))

        _rubric, record, scorecard = self.scorecard()
        report = render_baseline_report(
            [record],
            [replace(
                scorecard,
                categories=(
                    replace(scorecard.categories[0], rationale="Private literal."),
                    *scorecard.categories[1:],
                ),
            )],
            [],
            runtime_disclosures=disclosure(),
            rules=(RedactionRule("Private literal", "Sanitized rationale"),),
        )
        self.assertNotIn("Private literal", report)
        self.assertIn("Sanitized rationale", report)

    def test_render_rejects_invalid_findings_and_long_quotations(self) -> None:
        _rubric, record, scorecard = self.scorecard()
        invalid_finding = Finding(
            identifier="unsupported",
            classification="pedagogy",
            scope="general",
            scenario_ids=(record.scenario_id,),
            evidence_turns=(f"{record.scenario_id}:2",),
            summary="Unsupported research.",
            research_links=("https://example.invalid/research",),
        )
        with self.assertRaises(ValueError):
            render_baseline_report(
                [record],
                [scorecard],
                [invalid_finding],
                runtime_disclosures=disclosure(),
                rules=(),
            )

        long_record = replace(
            record,
            turns=(
                replace(record.turns[0], learner="x" * 601),
                *record.turns[1:],
            ),
        )
        long_scorecard = replace(
            scorecard,
            categories=tuple(
                replace(category, evidence_turns=(1,)) for category in scorecard.categories
            ),
        )
        with self.assertRaisesRegex(ValueError, "600"):
            render_baseline_report(
                [long_record],
                [long_scorecard],
                [],
                runtime_disclosures=disclosure(),
                rules=(),
            )

    def test_validate_and_write_reject_unsafe_report_text(self) -> None:
        report = self.render(disclosure())
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "baseline.md"
            self.assertEqual(destination, write_sanitized_report(destination, report))
            self.assertEqual(report, destination.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            validate_baseline_report(report + "\n/home/private/raw.txt\n")

    def test_validator_requires_exact_privacy_and_limitations_sections(self) -> None:
        report = self.render(disclosure())
        cases = {
            "altered privacy": report.replace(
                PRIVACY_STATEMENT,
                PRIVACY_STATEMENT.replace("Raw Antigravity streams", "Raw provider streams"),
            ),
            "extra privacy content": report.replace(
                f"{PRIVACY_STATEMENT}\n\n## Baseline limitations",
                f"{PRIVACY_STATEMENT}\nExtra privacy claim.\n\n## Baseline limitations",
            ),
            "extra limitations content": report.replace(
                LIMITATIONS_STATEMENT,
                f"Additional limitation.\n{LIMITATIONS_STATEMENT}",
            ),
        }
        for label, malformed in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_baseline_report(malformed)

    def test_validator_rejects_structurally_incomplete_scenario_results(self) -> None:
        report = self.render(disclosure())
        cases = {
            "missing stop reason": report.replace(
                "- Stop reason: observable_outcome\n",
                "",
                1,
            ),
            "missing total": report.replace("- Total: 16/16\n", "", 1),
            "missing tutor quotation": report.replace(
                "> Tutor: Good. If force and mass both double, what happens to force divided by mass?\n",
                "",
                1,
            ),
        }
        for label, malformed in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_baseline_report(malformed)

    def test_private_cli_scores_renders_and_validates_report(self) -> None:
        from evaluation import cli

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            fixtures = repository / "evaluation" / "fixtures"
            fixtures.mkdir(parents=True)
            shutil.copy2(fixture_root() / "rubric.json", fixtures / "rubric.json")
            run_dir = repository / ".semantic-runs" / "synthetic-suite" / "conceptual-physics"
            run_dir.mkdir(parents=True)
            shutil.copy2(
                fixture_root() / "synthetic" / "session.json",
                run_dir / "run-record.json",
            )
            (run_dir / "runtime-context.json").write_text(
                json.dumps(
                    {
                        "runtime_root": "/tmp/fictitious-semantic-runtime",
                        "runtime_outside_repository": True,
                        "local_rule_check_passed": True,
                        "rule_boundary": "user_home",
                        "user_home_rule_paths": [],
                        "above_home_markers": [],
                    }
                ),
                encoding="utf-8",
            )

            answers: list[str] = []
            rubric = load_rubric(fixture_root() / "rubric.json")
            for _category in rubric.categories:
                answers.extend(("2", "2,3,4", "Synthetic rationale."))
            answers.extend(("", "n"))
            output = io.StringIO()
            with (
                mock.patch.object(cli, "REPOSITORY", repository),
                mock.patch("builtins.input", side_effect=answers),
            ):
                self.assertEqual(
                    0,
                    cli.main(
                        ["score", "--suite-id", "synthetic-suite"],
                        output=output,
                        error=io.StringIO(),
                    ),
                )
                report_path = repository / "evaluation" / "reports" / "baseline.md"
                self.assertEqual(
                    0,
                    cli.main(
                        [
                            "report",
                            "--suite-id",
                            "synthetic-suite",
                            "--output",
                            str(report_path.relative_to(repository)),
                        ],
                        output=output,
                        error=io.StringIO(),
                    ),
                )
                self.assertEqual(
                    0,
                    cli.main(
                        ["validate-report", str(report_path.relative_to(repository))],
                        output=output,
                        error=io.StringIO(),
                    ),
                )
            self.assertIn("Semantic evaluation scoring completed.", output.getvalue())
            self.assertIn("Semantic baseline report written.", output.getvalue())
            self.assertIn("Semantic baseline report is valid.", output.getvalue())


if __name__ == "__main__":
    unittest.main()
