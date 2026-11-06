from __future__ import annotations

import copy
import json
import unittest
from dataclasses import replace

from evaluation.parser import (
    TutorTurn,
    collect_tutor_turn,
    is_completion,
    json_pointer_get,
    json_pointer_set,
    parse_ndjson,
    request_line,
)
from evaluation.schema import fixture_root, load_stream_contract


class JsonPointerTests(unittest.TestCase):
    def test_get_decodes_escaped_tokens_and_traverses_objects_and_arrays(self) -> None:
        document = {
            "a/b": {"~key": [{"": "value"}]},
            "~1": "escape-order",
            "0": "object-key",
        }
        self.assertEqual("value", json_pointer_get(document, "/a~1b/~0key/0/"))
        self.assertEqual("escape-order", json_pointer_get(document, "/~01"))
        self.assertEqual("object-key", json_pointer_get(document, "/0"))
        self.assertIs(document, json_pointer_get(document, ""))

    def test_rejects_malformed_pointer_syntax_and_escapes(self) -> None:
        for pointer in ("not/a/pointer", "/bad~", "/bad~2"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                json_pointer_get({"bad": 1}, pointer)

    def test_array_tokens_must_be_canonical_in_range_indexes(self) -> None:
        document = {"items": ["zero"]}
        for pointer in ("/items/00", "/items/-", "/items/-1", "/items/x"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                json_pointer_get(document, pointer)
        with self.assertRaises(IndexError):
            json_pointer_get(document, "/items/1")

    def test_get_rejects_missing_keys_and_scalar_traversal(self) -> None:
        with self.assertRaises(KeyError):
            json_pointer_get({}, "/missing")
        with self.assertRaises(TypeError):
            json_pointer_get({"value": 1}, "/value/child")

    def test_set_returns_deep_copy_without_mutating_or_aliasing_inputs(self) -> None:
        document = {"a/b": {"items": [{"text": "old"}]}, "untouched": [1]}
        replacement = {"nested": ["new"]}
        original = copy.deepcopy(document)

        updated = json_pointer_set(document, "/a~1b/items/0/text", replacement)
        replacement["nested"].append("later")
        updated["untouched"].append(2)  # type: ignore[union-attr]

        self.assertEqual(original, document)
        self.assertEqual({"nested": ["new"]}, json_pointer_get(updated, "/a~1b/items/0/text"))
        self.assertEqual([1], document["untouched"])

    def test_set_can_replace_root_without_aliasing_replacement(self) -> None:
        replacement = {"new": ["value"]}
        updated = json_pointer_set({"old": True}, "", replacement)
        replacement["new"].append("later")
        self.assertEqual({"new": ["value"]}, updated)

    def test_set_replaces_direct_child_of_root_object_or_array(self) -> None:
        self.assertEqual(
            {"child": "new"},
            json_pointer_set({"child": "old"}, "/child", "new"),
        )
        self.assertEqual(
            ["new"],
            json_pointer_set(["old"], "/0", "new"),
        )

    def test_set_requires_existing_object_key_and_array_index(self) -> None:
        with self.assertRaises(KeyError):
            json_pointer_set({}, "/missing", 1)
        with self.assertRaises(IndexError):
            json_pointer_set({"items": []}, "/items/0", 1)


class NdjsonTests(unittest.TestCase):
    def test_parses_utf8_objects_in_order_and_accepts_one_final_newline(self) -> None:
        data = '{"text":"café"}\n{"number":2}\n'.encode()
        self.assertEqual(
            ({"text": "café"}, {"number": 2}),
            parse_ndjson(data),
        )

    def test_empty_input_is_an_empty_stream(self) -> None:
        self.assertEqual((), parse_ndjson(b""))

    def test_rejects_blank_event_line_with_one_based_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_ndjson(b'{"ok":true}\n \n{"ok":false}\n')

    def test_rejects_non_object_event_with_one_based_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_ndjson(b'{"ok":true}\n[]\n')

    def test_rejects_malformed_json_with_one_based_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_ndjson(b'{"ok":true}\nnot-json\n')

    def test_rejects_malformed_utf8_with_one_based_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_ndjson(b'{"ok":true}\n{"text":"\xff"}\n')


class EvaluationParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_stream_contract(
            fixture_root() / "antigravity/stream-contract.json"
        )

    def test_request_replaces_only_observed_text_location_and_appends_newline(self) -> None:
        before = copy.deepcopy(self.contract.request_template)
        encoded = request_line(self.contract, "learner cafés")
        document = json.loads(encoded)

        self.assertEqual(
            "learner cafés",
            json_pointer_get(document, self.contract.request_text_pointer),
        )
        self.assertEqual(
            {"event": "user", "message": {"content": "learner cafés"}},
            document,
        )
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(1, encoded.count(b"\n"))
        self.assertIn("cafés".encode(), encoded)
        self.assertEqual(before, self.contract.request_template)

    def test_repeated_requests_never_mutate_contract_template(self) -> None:
        first = json.loads(request_line(self.contract, "first"))
        second = json.loads(request_line(self.contract, "second"))
        self.assertEqual("first", json_pointer_get(first, "/message/content"))
        self.assertEqual("second", json_pointer_get(second, "/message/content"))
        self.assertEqual(
            "STREAM_CONTRACT_OK",
            json_pointer_get(
                self.contract.request_template,
                self.contract.request_text_pointer,
            ),
        )

    def test_sample_events_replay_to_completed_tutor_turn(self) -> None:
        turn = collect_tutor_turn(
            self.contract.sample_output_events,
            self.contract,
        )
        self.assertEqual(
            TutorTurn(
                text=(
                    "STREAM_CONTRACT_OK\n\nYour message doesn't include a learning objective. "
                    "If you want a learning session, tell me what you want to be able to do at "
                    "the end, and I'll confirm that outcome with you before any diagnostic "
                    "questions.\n"
                ),
                event_count=5,
                completed=True,
            ),
            turn,
        )

    def test_collect_uses_only_captured_pointers_in_event_order(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/first", "/nested/second"),
            completion_pointer="/kind",
            completion_value="done",
        )
        events = (
            {"first": "A", "ignored": "X"},
            {"nested": {"second": "B"}, "other": {"text": "Y"}},
            {"kind": "done", "first": "C"},
        )
        self.assertEqual(
            TutorTurn(text="ABC", event_count=3, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_preserves_repeated_identical_deltas(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"text": "ha"},
            {"text": "ha"},
            {"done": True},
        )
        self.assertEqual(
            TutorTurn(text="haha", event_count=3, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_preserves_later_prefix_fragment(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"text": "The cat sat. "},
            {"text": "The"},
            {"done": True},
        )
        self.assertEqual(
            TutorTurn(text="The cat sat. The", event_count=3, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_replaces_strictly_extending_cumulative_snapshot(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"text": "Hel"},
            {"text": "Hello"},
            {"done": True},
        )
        self.assertEqual(
            TutorTurn(text="Hello", event_count=3, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_preserves_ambiguous_equal_completion_fragment(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"text": "answer"},
            {"text": "answer", "done": True},
        )
        self.assertEqual(
            TutorTurn(text="answeranswer", event_count=2, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_treats_output_pointer_path_shape_mismatch_as_absent(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/items/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"items": []},
            {"items": {"text": "kept"}},
            {"done": True},
        )
        self.assertEqual(
            TutorTurn(text="kept", event_count=3, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_requires_completion_value_and_type_to_match_exactly(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        for non_match in (1, "true", False, None):
            with self.subTest(non_match=non_match):
                turn = collect_tutor_turn(
                    ({"text": "answer"}, {"done": non_match}),
                    contract,
                )
                self.assertFalse(turn.completed)
                self.assertEqual(2, turn.event_count)

    def test_is_completion_uses_exact_match_and_absent_path_semantics(self) -> None:
        contract = replace(
            self.contract,
            completion_pointer="/items/done",
            completion_value=True,
        )
        self.assertTrue(is_completion({"items": {"done": True}}, contract))
        self.assertFalse(is_completion({"items": {"done": 1}}, contract))
        self.assertFalse(is_completion({"items": {}}, contract))
        self.assertFalse(is_completion({"items": []}, contract))

    def test_collect_rejects_non_string_extracted_text(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        for value in (None, True, 1, [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "text.*string"
            ):
                collect_tutor_turn(({"text": value},), contract)

    def test_collect_includes_text_on_completion_event_and_ignores_later_events(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        events = (
            {"text": "before"},
            {"done": True, "text": " complete"},
            {"text": " after"},
        )
        self.assertEqual(
            TutorTurn(text="before complete", event_count=2, completed=True),
            collect_tutor_turn(events, contract),
        )

    def test_collect_returns_incomplete_turn_when_completion_is_absent(self) -> None:
        contract = replace(
            self.contract,
            output_text_pointers=("/text",),
            completion_pointer="/done",
            completion_value=True,
        )
        self.assertEqual(
            TutorTurn(text="partial", event_count=1, completed=False),
            collect_tutor_turn(({"text": "partial"},), contract),
        )


if __name__ == "__main__":
    unittest.main()
