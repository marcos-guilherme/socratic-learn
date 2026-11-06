from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dataclasses import FrozenInstanceError

from evaluation.schema import (
    canonical_json,
    fixture_root,
    load_rubric,
    load_run_record,
    load_scenario,
    load_stream_contract,
)

SHA256 = "a" * 64


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
        "learner_response_count": 1,
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
        for key, value in (("max_learner_responses", 14), ("schema_version", 2)):
            with self.subTest(key=key):
                document = _scenario_document()
                document[key] = value
                with tempfile.TemporaryDirectory() as temporary:
                    with self.assertRaisesRegex(ValueError, key):
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
