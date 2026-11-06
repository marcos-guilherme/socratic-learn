from __future__ import annotations

import copy
import re
import unittest

from learning_tutor import MANIFEST_SCHEMA_VERSION, PROTOCOL_VERSION, TARGETS
from learning_tutor.conformance import (
    CONFORMANCE_CONTRACT_VERSION,
    REQUIRED_DIAGNOSTIC_CODES,
)
from learning_tutor.errors import IntegrityError
from learning_tutor.manifest import serialize_json, sha256_bytes, validate_manifest


SESSION_HEADINGS = (
    "## Outcome",
    "## Diagnostic evidence",
    "## Approved dependency path",
    "## Concepts established",
    "## Application evidence",
    "## Remaining gaps",
    "## Next step",
    "## Sources",
)
CAPABILITY_FALLBACKS = {
    "cross_session_memory": "Ask for a prior summary and state what is unknown.",
    "diagram_rendering": "Use Mermaid if available or a textual edge list.",
    "filesystem": "Return the complete session record as Markdown.",
    "structured_quiz": "Ask one question at a time in conversation.",
    "subagents": "Research and teach sequentially.",
    "web": "Mark volatile claims unverified and prefer stable content.",
}


def valid_manifest() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "language": "en",
        "targets": list(TARGETS),
        "sources": [
            {"path": "core/pedagogy.md", "sha256": digest},
            {"path": "core/session-protocol.md", "sha256": "b" * 64},
        ],
        "bundle": {
            "path": "learning-tutor.prompt.md",
            "sha256": "c" * 64,
        },
        "capability_fallbacks": dict(CAPABILITY_FALLBACKS),
        "conformance": {
            "version": CONFORMANCE_CONTRACT_VERSION,
            "required_diagnostic_codes": list(REQUIRED_DIAGNOSTIC_CODES),
        },
        "session_headings": list(SESSION_HEADINGS),
    }


class ManifestTests(unittest.TestCase):
    def test_serialize_json_is_sorted_utf8_with_one_final_newline(self) -> None:
        result = serialize_json({"z": "café", "a": 1})

        self.assertEqual(b'{\n  "a": 1,\n  "z": "caf\xc3\xa9"\n}\n', result)
        self.assertFalse(result.endswith(b"\n\n"))

    def test_sha256_is_lowercase_hex(self) -> None:
        digest = sha256_bytes(b"learning tutor")

        self.assertRegex(digest, re.compile(r"^[0-9a-f]{64}$"))

    def test_sha256_matches_known_abc_vector(self) -> None:
        self.assertEqual(
            "ba7816bf8f01cfea414140de5dae2223"
            "b00361a396177a9cb410ff61f20015ad",
            sha256_bytes(b"abc"),
        )

    def test_valid_manifest_passes(self) -> None:
        validate_manifest(valid_manifest())

    def assert_invalid(self, mutation, expected: str) -> None:
        manifest = copy.deepcopy(valid_manifest())
        mutation(manifest)
        with self.assertRaisesRegex(IntegrityError, expected) as raised:
            validate_manifest(manifest)
        self.assertTrue(raised.exception.path)
        self.assertTrue(raised.exception.remediation)

    def test_rejects_unknown_schema_version(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("schema_version", 2),
            "schema_version",
        )

    def test_rejects_boolean_schema_version(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("schema_version", True),
            "schema_version",
        )

    def test_rejects_wrong_protocol_version(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("protocol_version", "2.0.0"),
            "protocol_version",
        )

    def test_rejects_wrong_language(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("language", "pt"),
            "language",
        )

    def test_rejects_target_drift(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("targets", ["generic"]),
            "targets",
        )

    def test_rejects_duplicate_source_paths(self) -> None:
        def duplicate(value: dict[str, object]) -> None:
            sources = value["sources"]
            assert isinstance(sources, list)
            sources[1]["path"] = sources[0]["path"]

        self.assert_invalid(duplicate, "duplicate source path")

    def test_rejects_absolute_source_paths_in_posix_or_windows_form(self) -> None:
        for path in ("/tmp/pedagogy.md", r"C:\repo\pedagogy.md", r"\\host\share\x"):
            with self.subTest(path=path):
                def make_absolute(value: dict[str, object], path: str = path) -> None:
                    sources = value["sources"]
                    assert isinstance(sources, list)
                    sources[0]["path"] = path

                self.assert_invalid(make_absolute, "relative")

    def test_rejects_malformed_source_and_bundle_hashes(self) -> None:
        def bad_source(value: dict[str, object]) -> None:
            sources = value["sources"]
            assert isinstance(sources, list)
            sources[0]["sha256"] = "A" * 64

        def bad_bundle(value: dict[str, object]) -> None:
            bundle = value["bundle"]
            assert isinstance(bundle, dict)
            bundle["sha256"] = "not-a-hash"

        self.assert_invalid(bad_source, "sha256")
        self.assert_invalid(bad_bundle, "sha256")

    def test_rejects_bundle_path_drift(self) -> None:
        def mutate(value: dict[str, object]) -> None:
            bundle = value["bundle"]
            assert isinstance(bundle, dict)
            bundle["path"] = "other.md"

        self.assert_invalid(mutate, "learning-tutor.prompt.md")

    def test_rejects_missing_or_empty_capability_fallback(self) -> None:
        def missing(value: dict[str, object]) -> None:
            fallbacks = value["capability_fallbacks"]
            assert isinstance(fallbacks, dict)
            del fallbacks["web"]

        def empty(value: dict[str, object]) -> None:
            fallbacks = value["capability_fallbacks"]
            assert isinstance(fallbacks, dict)
            fallbacks["web"] = ""

        self.assert_invalid(missing, "capability_fallbacks")
        self.assert_invalid(empty, "capability_fallbacks")

    def test_rejects_session_heading_sequence_drift(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__(
                "session_headings", list(reversed(SESSION_HEADINGS))
            ),
            "session_headings",
        )

    def test_rejects_unknown_top_level_key(self) -> None:
        self.assert_invalid(
            lambda value: value.__setitem__("unexpected", "value"),
            "unexpected",
        )

    def test_rejects_unknown_nested_keys(self) -> None:
        def source_extra(value: dict[str, object]) -> None:
            sources = value["sources"]
            assert isinstance(sources, list)
            sources[0]["size"] = 123

        def bundle_extra(value: dict[str, object]) -> None:
            bundle = value["bundle"]
            assert isinstance(bundle, dict)
            bundle["media_type"] = "text/markdown"

        self.assert_invalid(source_extra, r"sources\[0\]\.size")
        self.assert_invalid(bundle_extra, "bundle.media_type")

    def test_rejects_wrong_json_types(self) -> None:
        cases = (
            ("protocol_version", 100, "protocol_version"),
            ("language", ["en"], "language"),
            ("targets", tuple(TARGETS), "targets"),
            ("sources", {"path": "x"}, "sources"),
            ("bundle", [], "bundle"),
            ("capability_fallbacks", [], "capability_fallbacks"),
            ("conformance", [], "conformance"),
            ("session_headings", tuple(SESSION_HEADINGS), "session_headings"),
        )
        for field, replacement, expected in cases:
            with self.subTest(field=field):
                self.assert_invalid(
                    lambda value, field=field, replacement=replacement: (
                        value.__setitem__(field, replacement)
                    ),
                    expected,
                )

    def test_rejects_control_characters_in_manifest_strings(self) -> None:
        def control_path(value: dict[str, object]) -> None:
            sources = value["sources"]
            assert isinstance(sources, list)
            sources[0]["path"] = "core/\x00pedagogy.md"

        def control_fallback(value: dict[str, object]) -> None:
            fallbacks = value["capability_fallbacks"]
            assert isinstance(fallbacks, dict)
            fallbacks["web"] = "unsafe\x1ftext"

        self.assert_invalid(control_path, r"sources\[0\]\.path")
        self.assert_invalid(control_fallback, "capability_fallbacks.web")

    def test_every_integrity_error_identifies_field_and_remediation(self) -> None:
        manifest = valid_manifest()
        manifest["unexpected"] = "value"

        with self.assertRaises(IntegrityError) as raised:
            validate_manifest(manifest)

        self.assertEqual("manifest.unexpected", str(raised.exception.path))
        self.assertTrue(raised.exception.remediation)


if __name__ == "__main__":
    unittest.main()
