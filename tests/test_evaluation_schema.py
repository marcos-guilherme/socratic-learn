from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataclasses import FrozenInstanceError

from evaluation.schema import (
    RUN_SCHEMA_V1,
    RUN_SCHEMA_V2,
    SCENARIO_SCHEMA_V1,
    SCENARIO_SCHEMA_V2,
    canonical_json,
    fixture_root,
    fixture_sha256,
    load_rubric,
    load_run_record,
    load_scenario,
    load_stream_contract,
    identities_for_scenario,
    load_suite_manifest,
    manifest_fixture_identities,
    validate_run_record,
)

SHA256 = "a" * 64


class EvaluationSchemaTests(unittest.TestCase):
    def test_three_scenarios_have_distinct_domains_and_hard_cap(self) -> None:
        baseline_ids = (
            "communication-writing",
            "conceptual-physics",
            "practical-programming",
        )
        scenarios = [
            load_scenario(fixture_root() / "scenarios" / f"{identifier}.json")
            for identifier in baseline_ids
        ]
        self.assertTrue(all(scenario.source_fixture_id is None for scenario in scenarios))
        self.assertEqual(sorted(baseline_ids), sorted(scenario.identifier for scenario in scenarios))
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


def _write(directory: str, name: str, document: object) -> Path:
    path = Path(directory) / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _scenario_document() -> dict[str, object]:
    source = fixture_root() / "scenarios/conceptual-physics.json"
    return json.loads(source.read_text(encoding="utf-8"))


def _stream_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "antigravity_version": "1.0.0",
        "model_identifier": "model-a",
        "request_text_pointer": "/request/text",
        "output_text_pointers": ["/chunk/text"],
        "completion_pointer": "/chunk/done",
        "completion_value": True,
        "request_template": {"request": {"text": ""}},
        "sample_output_events": [{"chunk": {"text": "hi", "done": False}}],
    }


def _run_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": "run-1",
        "suite_id": "suite-1",
        "scenario_id": "conceptual-physics",
        "repository_commit": "b" * 40,
        "protocol_version": "1",
        "protocol_sha256": SHA256,
        "runtime": "antigravity",
        "runtime_version": "1.0.0",
        "model_identifier": "model-a",
        "learner_response_count": 0,
        "stop_reason": "observable_outcome",
        "infrastructure_failure": None,
        "turns": [{"number": 1, "learner": "Hello", "tutor": "Hi"}],
    }


class EvaluationSchemaStrictnessTests(unittest.TestCase):
    def test_canonical_json_is_sorted_indented_utf8_with_trailing_newline(self) -> None:
        self.assertEqual(
            '{\n  "a": "\u00e9",\n  "b": 1\n}\n'.encode("utf-8"),
            canonical_json({"b": 1, "a": "\u00e9"}),
        )

    def test_loaded_scenario_is_frozen(self) -> None:
        scenario = load_scenario(fixture_root() / "scenarios/conceptual-physics.json")
        with self.assertRaises(FrozenInstanceError):
            scenario.title = "changed"  # type: ignore[misc]

    def test_scenario_rejects_missing_key(self) -> None:
        document = _scenario_document()
        del document["title"]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "title"):
                load_scenario(_write(temporary, "s.json", document))

    def test_scenario_rejects_boolean_where_integer_expected(self) -> None:
        for key in ("schema_version", "max_learner_responses"):
            with self.subTest(key=key):
                document = _scenario_document()
                document[key] = True
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaisesRegex(ValueError, key):
                        load_scenario(_write(temporary, "s.json", document))

    def test_scenario_rejects_wrong_cap_and_version(self) -> None:
        document = _scenario_document()
        document["max_learner_responses"] = 14
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "max_learner_responses"):
                load_scenario(_write(temporary, "s.json", document))
        document = _scenario_document()
        document["schema_version"] = 99
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "schema_version"):
                load_scenario(_write(temporary, "s.json", document))

    def test_scenario_rejects_bad_identifier_and_empty_arrays(self) -> None:
        cases = (
            ("identifier", "Bad_Id"),
            ("identifier", "trailing-"),
            ("title", "  "),
            ("domain", "unknown"),
            ("observable_outcome", []),
            ("response_policy", []),
            ("response_policy", ["ok", ""]),
        )
        for key, value in cases:
            with self.subTest(key=key, value=value):
                document = _scenario_document()
                document[key] = value
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaisesRegex(ValueError, key):
                        load_scenario(_write(temporary, "s.json", document))

    def test_scenario_rejects_unknown_persona_key(self) -> None:
        document = _scenario_document()
        document["persona"]["extra"] = "x"  # type: ignore[index]
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "extra"):
                load_scenario(_write(temporary, "s.json", document))

    def test_json_with_duplicate_keys_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "s.json"
            path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_scenario(path)

    def test_rubric_rejects_unknown_and_incomplete_anchor_keys(self) -> None:
        source = json.loads((fixture_root() / "rubric.json").read_text(encoding="utf-8"))
        unknown = json.loads(json.dumps(source))
        unknown["extra"] = 1
        incomplete = json.loads(json.dumps(source))
        del incomplete["categories"][0]["anchors"]["2"]
        for name, document, pattern in (
            ("unknown", unknown, "extra"),
            ("incomplete", incomplete, "anchors"),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, pattern):
                    load_rubric(_write(temporary, "r.json", document))

    def test_rubric_anchors_use_integer_scores(self) -> None:
        rubric = load_rubric(fixture_root() / "rubric.json")
        self.assertEqual({0, 1, 2}, set(rubric.categories[0].anchors))

    def test_stream_contract_loads_and_rejects_unknown_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            contract = load_stream_contract(_write(temporary, "c.json", _stream_document()))
            self.assertEqual(("/chunk/text",), contract.output_text_pointers)
            self.assertIs(True, contract.completion_value)
            document = _stream_document()
            document["extra"] = 1
            with self.assertRaisesRegex(ValueError, "extra"):
                load_stream_contract(_write(temporary, "d.json", document))
            document = _stream_document()
            document["request_text_pointer"] = "request/text"
            with self.assertRaisesRegex(ValueError, "request_text_pointer"):
                load_stream_contract(_write(temporary, "e.json", document))

    def test_run_record_loads_and_validates_exact_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = load_run_record(_write(temporary, "r.json", _run_document()))
            self.assertEqual("antigravity", record.runtime)
            self.assertEqual(1, record.turns[0].number)
            self.assertIsNone(record.infrastructure_failure)
            cases = (
                ("extra", 1, "extra"),
                ("runtime", "other", "runtime"),
                ("learner_response_count", True, "learner_response_count"),
                ("stop_reason", "unknown", "stop_reason"),
                ("protocol_sha256", "ABC", "protocol_sha256"),
                ("turns", [{"number": 1, "learner": "a"}], "tutor"),
            )
            for key, value, pattern in cases:
                with self.subTest(key=key):
                    document = _run_document()
                    document[key] = value
                    with self.assertRaisesRegex(ValueError, pattern):
                        load_run_record(_write(temporary, "bad.json", document))

    def test_run_record_rejects_response_count_and_turn_sequence_mutations(self) -> None:
        cases = {
            "response count above cap": {
                "learner_response_count": 16,
                "turns": [
                    {"number": number, "learner": "a", "tutor": "b"}
                    for number in range(1, 18)
                ],
            },
            "response count does not match bootstrap turns": {
                "learner_response_count": 1,
            },
            "duplicate turn number": {
                "turns": [
                    {"number": 1, "learner": "a", "tutor": "b"},
                    {"number": 1, "learner": "c", "tutor": "d"},
                ],
                "learner_response_count": 1,
            },
            "nonsequential turn number": {
                "turns": [
                    {"number": 1, "learner": "a", "tutor": "b"},
                    {"number": 3, "learner": "c", "tutor": "d"},
                ],
                "learner_response_count": 1,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            for label, changes in cases.items():
                with self.subTest(label):
                    document = {**_run_document(), **changes}
                    with self.assertRaises(ValueError):
                        load_run_record(_write(temporary, f"{label}.json", document))

    def test_run_record_requires_infrastructure_failure_iff_stop_reason(self) -> None:
        cases = (
            {
                "stop_reason": "infrastructure_failure",
                "infrastructure_failure": None,
            },
            {
                "stop_reason": "observable_outcome",
                "infrastructure_failure": "runtime",
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            for index, changes in enumerate(cases):
                with self.subTest(changes=changes):
                    document = {**_run_document(), **changes}
                    with self.assertRaisesRegex(ValueError, "infrastructure"):
                        load_run_record(_write(temporary, f"failure-{index}.json", document))

    def test_run_record_infrastructure_class_is_checked_with_rubric(self) -> None:
        rubric = load_rubric(fixture_root() / "rubric.json")
        document = {
            **_run_document(),
            "stop_reason": "infrastructure_failure",
            "infrastructure_failure": "unknown-class",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = _write(temporary, "record.json", document)
            record = load_run_record(path)
            with self.assertRaisesRegex(ValueError, "infrastructure"):
                validate_run_record(record, rubric)


class EvaluationSchemaVersionTwoTests(unittest.TestCase):
    def test_schema_v1_scenario_and_run_fixtures_load_unchanged(self) -> None:
        scenario = load_scenario(fixture_root() / "scenarios/conceptual-physics.json")
        self.assertEqual(SCENARIO_SCHEMA_V1, scenario.schema_version)
        self.assertIsNone(scenario.source_fixture_id)
        record = load_run_record(fixture_root() / "synthetic/session.json")
        self.assertEqual(RUN_SCHEMA_V1, record.schema_version)
        self.assertIsNone(record.scenario_sha256)

    def test_schema_v2_scenario_requires_source_fixture_id(self) -> None:
        document = _scenario_document()
        document["schema_version"] = SCENARIO_SCHEMA_V2
        document["source_fixture_id"] = None
        with tempfile.TemporaryDirectory() as temporary:
            loaded = load_scenario(_write(temporary, "s.json", document))
        self.assertEqual(SCENARIO_SCHEMA_V2, loaded.schema_version)
        self.assertIsNone(loaded.source_fixture_id)

    def test_schema_v2_run_requires_exact_hash_fields(self) -> None:
        document = _run_document()
        document.update(
            {
                "schema_version": RUN_SCHEMA_V2,
                "scenario_sha256": SHA256,
                "rubric_sha256": SHA256,
                "suite_sha256": SHA256,
                "source_fixture_id": None,
                "source_fixture_sha256": None,
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            record = load_run_record(_write(temporary, "r.json", document))
        self.assertEqual(RUN_SCHEMA_V2, record.schema_version)
        self.assertEqual(SHA256, record.scenario_sha256)

    def test_suite_manifests_are_immutable_and_canonical(self) -> None:
        baseline = load_suite_manifest(fixture_root() / "suites/baseline-v1.json")
        article = load_suite_manifest(fixture_root() / "suites/article-reading-v1.json")
        with self.assertRaises(FrozenInstanceError):
            baseline.identifier = "changed"  # type: ignore[misc]
        self.assertEqual(
            (
                "conceptual-physics",
                "practical-programming",
                "communication-writing",
            ),
            baseline.scenario_ids,
        )
        self.assertEqual(("article-reading",), article.scenario_ids)

    def test_suite_manifest_rejects_invalid_scenarios_paths_and_contracts(self) -> None:
        base = {
            "schema_version": 1,
            "identifier": "baseline-v1",
            "scenario_ids": ["conceptual-physics"],
            "rubric_path": "rubric.json",
            "report_contract": "baseline-v1",
        }
        cases = {
            "duplicate scenario": {
                **base,
                "scenario_ids": ["conceptual-physics", "conceptual-physics"],
            },
            "unknown scenario": {**base, "scenario_ids": ["missing-scenario"]},
            "traversal rubric path": {**base, "rubric_path": "../rubric.json"},
            "unknown report contract": {**base, "report_contract": "unknown"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            for label, document in cases.items():
                with self.subTest(label=label), self.assertRaises(ValueError):
                    load_suite_manifest(_write(temporary, f"{label}.json", document))

    def test_fixture_sha256_matches_file_bytes(self) -> None:
        path = fixture_root() / "rubric.json"
        self.assertEqual(len(fixture_sha256(path)), 64)
        suite_hash, rubric_hash, scenario_hashes = manifest_fixture_identities(
            load_suite_manifest(fixture_root() / "suites/baseline-v1.json")
        )
        self.assertEqual(fixture_sha256(path), rubric_hash)
        self.assertEqual(3, len(scenario_hashes))
        self.assertEqual(
            fixture_sha256(fixture_root() / "suites/baseline-v1.json"),
            suite_hash,
        )

    def test_identities_for_scenario_resolves_article_reading_fixture(
        self,
    ) -> None:
        manifest = load_suite_manifest(
            fixture_root() / "suites/article-reading-v1.json"
        )
        identities = identities_for_scenario(manifest, "article-reading")
        self.assertEqual(len(identities.scenario_sha256), 64)

    def test_article_reading_scenario_schema_two_contract(self) -> None:
        scenario = load_scenario(fixture_root() / "scenarios/article-reading.json")
        self.assertEqual(2, scenario.schema_version)
        self.assertEqual("article-reading-v1", scenario.source_fixture_id)
        self.assertEqual("communication", scenario.domain)
        misconception = scenario.persona["misconception"]
        self.assertIsInstance(misconception, str)
        self.assertIn("longevity", misconception.lower())
        style = scenario.persona["communication_style"]
        style_text = "\n".join(style) if isinstance(style, tuple) else str(style)
        self.assertIn("overload", style_text.lower())
        self.assertIn("weak evidence", style_text.lower())
        policy_text = "\n".join(scenario.response_policy)
        self.assertIn("transfer", policy_text.lower())
        self.assertIn("external verification", " ".join(scenario.observable_outcome).lower())

    def test_article_source_fixture_hash_is_stable(self) -> None:
        path = fixture_root() / "sources/article-reading-v1/source.pdf"
        self.assertEqual(
            "457b959a517b25beed4e2b986d9814e3beca89db94f4a52fe1c2de47909fd1da",
            fixture_sha256(path),
        )

