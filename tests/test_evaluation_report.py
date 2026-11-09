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
from evaluation.scoring import (
    ARTICLE_CATEGORY_IDS,
    ARTICLE_REQUIRED_AT_TWO,
    article_reading_passes,
    article_release_status,
)
from evaluation.schema import (
    CategoryScore,
    Finding,
    RUN_SCHEMA_V1,
    RUN_SCHEMA_V2,
    RunRecord,
    Scorecard,
    TurnRecord,
    fixture_root,
    identities_for_scenario,
    load_rubric,
    load_run_record,
    load_suite_manifest,
    manifest_fixture_identities,
)
from evaluation.scoring import interactive_score, scorecard_from_mapping, validate_scorecard


def baseline_suite():
    return load_suite_manifest(fixture_root() / "suites/baseline-v1.json")


def baseline_rubric():
    return load_rubric(fixture_root() / "rubric.json")


def with_fixture_identities(record, suite, *, suite_id: str | None = None):
    suite_hash, rubric_hash, scenario_hashes = manifest_fixture_identities(suite)
    scenario_hash = scenario_hashes[suite.scenario_ids.index(record.scenario_id)]
    return replace(
        record,
        schema_version=RUN_SCHEMA_V2,
        suite_id=suite_id or suite.identifier,
        scenario_sha256=scenario_hash,
        rubric_sha256=rubric_hash,
        suite_sha256=suite_hash,
    )


def disclosure(
    user_home_rule_paths: tuple[str, ...] = (),
    above_home_markers: tuple[AboveHomeMarker, ...] = (),
    *,
    passed: bool = True,
) -> dict[str, ScenarioRuntimeDisclosure]:
    return {
        scenario_id: ScenarioRuntimeDisclosure(
            scenario_id=scenario_id,
            local_rule_check_passed=passed,
            rule_disclosure=RuleDisclosure(
                boundary="user_home",
                user_home_rule_paths=user_home_rule_paths,
                above_home_markers=above_home_markers,
            ),
        )
        for scenario_id in (
            "conceptual-physics",
            "practical-programming",
            "communication-writing",
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

    def report_triplet(self):
        _rubric, record, scorecard = self.scorecard()
        suite = baseline_suite()
        records = [
            with_fixture_identities(
                replace(
                    record,
                    run_id=f"run-{scenario_id}",
                    scenario_id=scenario_id,
                    turns=(
                        record.turns
                        if scenario_id == "conceptual-physics"
                        else tuple(
                            replace(
                                turn,
                                learner=f"{scenario_id}: {turn.learner}",
                                tutor=f"{scenario_id}: {turn.tutor}",
                            )
                            for turn in record.turns
                        )
                    ),
                ),
                suite,
            )
            for scenario_id in suite.scenario_ids
        ]
        scorecards = [
            replace(scorecard, scenario_id=scenario_id)
            for scenario_id in suite.scenario_ids
        ]
        runtime_disclosures = {
            scenario_id: ScenarioRuntimeDisclosure(
                scenario_id=scenario_id,
                local_rule_check_passed=True,
                rule_disclosure=RuleDisclosure(
                    boundary="user_home",
                    user_home_rule_paths=(),
                    above_home_markers=(),
                ),
            )
            for scenario_id in suite.scenario_ids
        }
        return suite, records, scorecards, runtime_disclosures

    def render(self, runtime_disclosures: dict[str, ScenarioRuntimeDisclosure]) -> str:
        suite, records, scorecards, _default_disclosures = self.report_triplet()
        return render_baseline_report(
            suite,
            baseline_rubric(),
            records,
            scorecards,
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

    def test_report_accepts_exact_scenario_model_and_protocol_triplet(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()

        report = render_baseline_report(
            suite,
            baseline_rubric(),
            records,
            scorecards,
            [],
            runtime_disclosures=runtime_disclosures,
            rules=(),
        )

        self.assertEqual(set(suite.scenario_ids), {record.scenario_id for record in records})
        self.assertEqual(1, len({record.model_identifier for record in records}))
        self.assertIn("### communication-writing", report)
        self.assertIn("- Suite SHA-256:", report)

    def test_report_rejects_invalid_scenario_or_identity_triplet(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        cases = {
            "duplicate scenario": [
                records[0],
                replace(records[1], scenario_id=records[0].scenario_id),
                records[2],
            ],
            "missing scenario": records[:-1],
            "differing model identifier": [
                records[0],
                replace(records[1], model_identifier="different-model"),
                records[2],
            ],
            "differing suite ID": [
                records[0],
                replace(records[1], suite_id="different-suite"),
                records[2],
            ],
            "differing repository commit": [
                records[0],
                replace(records[1], repository_commit="f" * 40),
                records[2],
            ],
            "differing protocol version": [
                records[0],
                replace(records[1], protocol_version="different-version"),
                records[2],
            ],
            "differing protocol hash": [
                records[0],
                replace(records[1], protocol_sha256="0" * 64),
                records[2],
            ],
            "differing runtime": [
                records[0],
                replace(records[1], runtime="other"),  # type: ignore[arg-type]
                records[2],
            ],
            "differing runtime version": [
                records[0],
                replace(records[1], runtime_version="different-runtime"),
                records[2],
            ],
        }
        for label, invalid_records in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                render_baseline_report(
                    suite,
                    baseline_rubric(),
                    invalid_records,
                    scorecards[: len(invalid_records)],
                    [],
                    runtime_disclosures=runtime_disclosures,
                    rules=(),
                )

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

        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        scorecards[0] = replace(
            scorecards[0],
            categories=(
                replace(scorecards[0].categories[0], rationale="Private literal."),
                *scorecards[0].categories[1:],
            ),
        )
        report = render_baseline_report(
            suite,
            baseline_rubric(),
            records,
            scorecards,
            [],
            runtime_disclosures=runtime_disclosures,
            rules=(RedactionRule("Private literal", "Sanitized rationale"),),
        )
        self.assertNotIn("Private literal", report)
        self.assertIn("Sanitized rationale", report)

    def test_render_rejects_invalid_findings_and_long_quotations(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        record = records[0]
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
                suite,
                baseline_rubric(),
                records,
                scorecards,
                [invalid_finding],
                runtime_disclosures=runtime_disclosures,
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
            scorecards[0],
            categories=tuple(
                replace(category, evidence_turns=(1,))
                for category in scorecards[0].categories
            ),
        )
        with self.assertRaisesRegex(ValueError, "600"):
            render_baseline_report(
                suite,
                baseline_rubric(),
                [long_record, *records[1:]],
                [long_scorecard, *scorecards[1:]],
                [],
                runtime_disclosures=runtime_disclosures,
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

    def test_validator_rejects_deleted_required_section_bodies(self) -> None:
        report = self.render(disclosure())

        def delete_body(text: str, heading: str, next_heading: str) -> str:
            prefix, remainder = text.split(f"{heading}\n", 1)
            _body, suffix = remainder.split(next_heading, 1)
            return f"{prefix}{heading}\n{next_heading}{suffix}"

        cases = {
            "scenario results": delete_body(
                report,
                "## Scenario results",
                "## General findings",
            ),
            "general findings": delete_body(
                report,
                "## General findings",
                "## Scenario-specific findings",
            ),
            "scenario-specific findings": delete_body(
                report,
                "## Scenario-specific findings",
                "## Infrastructure results",
            ),
        }
        for label, malformed in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                validate_baseline_report(malformed)

    def test_private_cli_scores_renders_and_validates_report(self) -> None:
        from evaluation import cli

        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            runtime_root = (
                repository.parent / "fictitious-semantic-runtime"
            ).resolve()
            fixtures = repository / "evaluation" / "fixtures"
            fixtures.mkdir(parents=True)
            shutil.copytree(fixture_root() / "suites", fixtures / "suites")
            shutil.copy2(fixture_root() / "rubric.json", fixtures / "rubric.json")
            source_record = json.loads(
                (fixture_root() / "synthetic" / "session.json").read_text(
                    encoding="utf-8"
                )
            )
            suite = baseline_suite()
            suite_hash, rubric_hash, scenario_hashes = manifest_fixture_identities(
                suite
            )
            for scenario_id, scenario_hash in zip(
                suite.scenario_ids,
                scenario_hashes,
                strict=True,
            ):
                run_dir = (
                    repository
                    / ".semantic-runs"
                    / "baseline-v1"
                    / scenario_id
                )
                run_dir.mkdir(parents=True)
                run_record = dict(source_record)
                run_record["schema_version"] = RUN_SCHEMA_V2
                run_record["suite_id"] = suite.identifier
                run_record["run_id"] = f"run-{scenario_id}"
                run_record["scenario_id"] = scenario_id
                run_record["scenario_sha256"] = scenario_hash
                run_record["rubric_sha256"] = rubric_hash
                run_record["suite_sha256"] = suite_hash
                run_record["source_fixture_id"] = None
                run_record["source_fixture_sha256"] = None
                (run_dir / "run-record.json").write_text(
                    json.dumps(run_record),
                    encoding="utf-8",
                )
                (run_dir / "runtime-context.json").write_text(
                    json.dumps(
                        {
                            "runtime_root": str(runtime_root),
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
            for _scenario in range(3):
                for _category in rubric.categories:
                    answers.extend(("2", "2,3,4", "Synthetic rationale."))
                answers.append("")
            answers.append("n")
            output = io.StringIO()
            with (
                mock.patch.object(cli, "REPOSITORY", repository),
                mock.patch("builtins.input", side_effect=answers),
            ):
                self.assertEqual(
                    0,
                    cli.main(
                        ["score", "--suite-id", "baseline-v1"],
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
                            "baseline-v1",
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


    def test_report_rejects_mixed_schema_identities(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        mixed = [
            replace(
                records[0],
                schema_version=RUN_SCHEMA_V1,
                scenario_sha256=None,
                rubric_sha256=None,
                suite_sha256=None,
            ),
            records[1],
            records[2],
        ]
        with self.assertRaisesRegex(ValueError, "schema 2"):
            render_baseline_report(
                suite,
                baseline_rubric(),
                mixed,
                scorecards,
                [],
                runtime_disclosures=runtime_disclosures,
                rules=(),
            )

    def test_report_rejects_wrong_fixture_hashes_independently(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        cases = {
            "suite hash": (
                tuple(replace(record, suite_sha256="f" * 64) for record in records),
                "unexpected suite hash",
            ),
            "rubric hash": (
                tuple(replace(record, rubric_sha256="f" * 64) for record in records),
                "unexpected rubric hash",
            ),
            "conceptual-physics scenario hash": (
                (
                    replace(records[0], scenario_sha256="f" * 64),
                    records[1],
                    records[2],
                ),
                "unexpected scenario hash",
            ),
            "practical-programming scenario hash": (
                (
                    records[0],
                    replace(records[1], scenario_sha256="f" * 64),
                    records[2],
                ),
                "unexpected scenario hash",
            ),
            "communication-writing scenario hash": (
                (
                    records[0],
                    records[1],
                    replace(records[2], scenario_sha256="f" * 64),
                ),
                "unexpected scenario hash",
            ),
        }
        for label, (invalid, pattern) in cases.items():
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, pattern):
                render_baseline_report(
                    suite,
                    baseline_rubric(),
                    invalid,
                    scorecards,
                    [],
                    runtime_disclosures=runtime_disclosures,
                    rules=(),
                )

    def test_report_rejects_wrong_category_maximum(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        rubric = baseline_rubric()
        short_rubric = replace(rubric, categories=rubric.categories[:-1])
        with self.assertRaisesRegex(ValueError, "category"):
            render_baseline_report(
                suite,
                short_rubric,
                records,
                scorecards,
                [],
                runtime_disclosures=runtime_disclosures,
                rules=(),
            )

    def test_report_scenario_sections_follow_manifest_order(self) -> None:
        suite, records, scorecards, runtime_disclosures = self.report_triplet()
        reversed_records = list(reversed(records))
        report = render_baseline_report(
            suite,
            baseline_rubric(),
            reversed_records,
            scorecards,
            [],
            runtime_disclosures=runtime_disclosures,
            rules=(),
        )
        positions = [
            report.index(f"### {scenario_id}") for scenario_id in suite.scenario_ids
        ]
        self.assertEqual(sorted(positions), positions)

    def test_historical_tracked_baseline_report_still_validates(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "evaluation/reports/2026-11-06-antigravity-baseline.md"
        )
        validate_baseline_report(path.read_text(encoding="utf-8"))


    def test_article_report_renders_release_gate_labels(self) -> None:
        manifest = load_suite_manifest(fixture_root() / "suites/article-reading-v1.json")
        rubric = load_rubric(fixture_root() / "rubric.json")
        identities = identities_for_scenario(manifest, "article-reading")
        record = RunRecord(
            schema_version=RUN_SCHEMA_V2,
            run_id="article-reading-v1-article-reading",
            suite_id="article-reading-v1",
            scenario_id="article-reading",
            repository_commit="0" * 40,
            protocol_version="1.2.0",
            protocol_sha256="a" * 64,
            runtime="antigravity",
            runtime_version="1.0",
            model_identifier="model",
            learner_response_count=0,
            stop_reason="infrastructure_failure",
            infrastructure_failure="timeout",
            turns=(TurnRecord(1, "bootstrap", "tutor"),),
            scenario_sha256=identities.scenario_sha256,
            rubric_sha256=identities.rubric_sha256,
            suite_sha256=identities.suite_sha256,
            source_fixture_id="article-reading-v1",
            source_fixture_sha256="457b959a517b25beed4e2b986d9814e3beca89db94f4a52fe1c2de47909fd1da",
        )
        passing = RunRecord(
            schema_version=record.schema_version,
            run_id=record.run_id,
            suite_id=record.suite_id,
            scenario_id=record.scenario_id,
            repository_commit=record.repository_commit,
            protocol_version=record.protocol_version,
            protocol_sha256=record.protocol_sha256,
            runtime=record.runtime,
            runtime_version=record.runtime_version,
            model_identifier=record.model_identifier,
            learner_response_count=1,
            stop_reason="observable_outcome",
            infrastructure_failure=None,
            turns=(
                TurnRecord(1, "bootstrap", "tutor"),
                TurnRecord(2, "learner", "tutor"),
            ),
            scenario_sha256=record.scenario_sha256,
            rubric_sha256=record.rubric_sha256,
            suite_sha256=record.suite_sha256,
            source_fixture_id=record.source_fixture_id,
            source_fixture_sha256=record.source_fixture_sha256,
        )
        scorecard = Scorecard(
            1,
            "article-reading",
            tuple(
                CategoryScore(identifier, 2, (2,), "ok")
                for identifier in (
                    "observable-outcome",
                    "relevant-diagnosis",
                    "calibrated-questioning",
                    "adaptive-support",
                    "retrieval-after-support",
                    "application-transfer",
                    "corrective-feedback",
                    "evidence-closure",
                )
            ),
            (),
        )
        disclosure = {
            "article-reading": ScenarioRuntimeDisclosure(
                "article-reading",
                True,
                RuleDisclosure("user_home", (), ()),
            )
        }
        infra_report = render_baseline_report(
            manifest,
            rubric,
            [record],
            [],
            [],
            runtime_disclosures=disclosure,
            rules=(),
        )
        self.assertIn("- Release gate: inconclusive", infra_report)
        self.assertNotIn("Release gate: passed", infra_report)
        passing_report = render_baseline_report(
            manifest,
            rubric,
            [passing],
            [scorecard],
            [],
            runtime_disclosures=disclosure,
            rules=(),
        )
        self.assertIn("- Release gate: passed", passing_report)
        validate_baseline_report(passing_report)


class ArticleReleaseGateTests(unittest.TestCase):
    def _record(self, *, stop_reason="observable_outcome", infrastructure_failure=None):
        return RunRecord(
            schema_version=RUN_SCHEMA_V2,
            run_id="article-reading-v1-article-reading",
            suite_id="article-reading-v1",
            scenario_id="article-reading",
            repository_commit="0" * 40,
            protocol_version="1.2.0",
            protocol_sha256="a" * 64,
            runtime="antigravity",
            runtime_version="1.0",
            model_identifier="model",
            learner_response_count=1,
            stop_reason=stop_reason,
            infrastructure_failure=infrastructure_failure,
            turns=(
                TurnRecord(1, "bootstrap", "tutor"),
                TurnRecord(2, "learner", "tutor"),
            ),
            scenario_sha256="a" * 64,
            rubric_sha256="b" * 64,
            suite_sha256="c" * 64,
            source_fixture_id="article-reading-v1",
            source_fixture_sha256="d" * 64,
        )

    def _scorecard(self, **overrides):
        scores = {identifier: 2 for identifier in ARTICLE_CATEGORY_IDS}
        scores.update(overrides)
        return Scorecard(
            schema_version=1,
            scenario_id="article-reading",
            categories=tuple(
                CategoryScore(identifier, scores[identifier], (2,), "ok")
                for identifier in sorted(ARTICLE_CATEGORY_IDS)
            ),
            critical_failures=(),
        )

    def test_boundary_pass_at_fourteen_points(self) -> None:
        scores = {identifier: 1 for identifier in ARTICLE_CATEGORY_IDS}
        for identifier in ARTICLE_REQUIRED_AT_TWO:
            scores[identifier] = 2
        scores["relevant-diagnosis"] = 2
        scores["adaptive-support"] = 2
        record = self._record()
        scorecard = Scorecard(
            1,
            "article-reading",
            tuple(
                CategoryScore(identifier, scores[identifier], (2,), "ok")
                for identifier in sorted(ARTICLE_CATEGORY_IDS)
            ),
            (),
        )
        self.assertEqual(14, scorecard.total)
        self.assertTrue(article_reading_passes(scorecard, record))

    def test_fail_at_thirteen_points(self) -> None:
        scores = {identifier: 1 for identifier in ARTICLE_CATEGORY_IDS}
        for identifier in ARTICLE_REQUIRED_AT_TWO:
            scores[identifier] = 2
        scores["relevant-diagnosis"] = 2
        record = self._record()
        scorecard = Scorecard(
            1,
            "article-reading",
            tuple(
                CategoryScore(identifier, scores[identifier], (2,), "ok")
                for identifier in sorted(ARTICLE_CATEGORY_IDS)
            ),
            (),
        )
        self.assertEqual(13, scorecard.total)
        self.assertFalse(article_reading_passes(scorecard, record))

    def test_required_category_at_one_fails(self) -> None:
        scorecard = self._scorecard(**{"observable-outcome": 1})
        self.assertFalse(article_reading_passes(scorecard, self._record()))

    def test_critical_failure_fails(self) -> None:
        scorecard = Scorecard(
            1,
            "article-reading",
            self._scorecard().categories,
            ("source-claim-presented-as-externally-verified",),
        )
        self.assertFalse(article_reading_passes(scorecard, self._record()))

    def test_infrastructure_is_inconclusive_not_pass(self) -> None:
        record = self._record(
            stop_reason="infrastructure_failure",
            infrastructure_failure="timeout",
        )
        self.assertEqual("inconclusive", article_release_status(record, self._scorecard()))
        self.assertFalse(article_reading_passes(self._scorecard(), record))

    def test_non_observable_outcome_fails(self) -> None:
        record = self._record(stop_reason="completion_without_evidence")
        self.assertEqual("failed", article_release_status(record, self._scorecard()))


    def test_wrong_suite_id_fails_gate(self) -> None:
        record = replace(self._record(), suite_id="baseline-v1")
        self.assertFalse(article_reading_passes(self._scorecard(), record))

    def test_missing_rubric_category_fails_gate(self) -> None:
        categories = tuple(
            category
            for category in self._scorecard().categories
            if category.identifier != "relevant-diagnosis"
        )
        scorecard = Scorecard(1, "article-reading", categories, ())
        self.assertFalse(article_reading_passes(scorecard, self._record()))

    def test_duplicate_rubric_category_fails_gate(self) -> None:
        categories = self._scorecard().categories + (self._scorecard().categories[0],)
        scorecard = Scorecard(1, "article-reading", categories, ())
        self.assertFalse(article_reading_passes(scorecard, self._record()))

    def test_rubric_contains_new_critical_failures(self) -> None:
        rubric = load_rubric(fixture_root() / "rubric.json")
        self.assertIn("source-claim-presented-as-externally-verified", rubric.critical_failures)
        self.assertIn("batched-independent-learner-tasks", rubric.critical_failures)


if __name__ == "__main__":
    unittest.main()
