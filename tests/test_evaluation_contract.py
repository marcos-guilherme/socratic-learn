from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess

from evaluation.contract_capture import (
    ContractCaptureError,
    capture_contract,
    main,
    publish_contract_fixture,
    select_model,
    validate_fixture,
)
from evaluation.schema import canonical_json, load_stream_contract
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

    def test_capture_runs_exact_argv_and_keeps_raw_material_private(self) -> None:
        request = b'{"observed_request":{"text":"STREAM_CONTRACT_OK"}}\n'
        output = b'{"observed_event":"complete","payload":"STREAM_CONTRACT_OK"}\n'
        seen: list[list[str]] = []

        def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[bytes]:
            seen.append(list(argv))
            return CompletedProcess(argv, 0, output, b"diagnostic")

        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "raw"
            captured = capture_contract(
                "agy",
                "captured-model-id",
                request,
                raw,
                completion_pointer="/observed_event",
                completion_value="complete",
                run=fake_run,
            )
            self.assertEqual(request, (raw / "request.ndjson").read_bytes())
            self.assertEqual(output, (raw / "stdout.ndjson").read_bytes())
            self.assertEqual(b"diagnostic", (raw / "stderr.txt").read_bytes())
            self.assertEqual(seen[0], json.loads((raw / "argv.json").read_text("utf-8")))
            expected_argv = [
                "agy",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--model",
                "captured-model-id",
                "--sandbox",
                "--disable-slash-commands",
                "--print-timeout",
                "300s",
                "--log-file",
                str(raw / "antigravity.log"),
            ]

        self.assertEqual([expected_argv], seen)
        for forbidden in ("--print", "-p", "--prompt", "--mode", "--dangerously-skip-permissions"):
            self.assertNotIn(forbidden, seen[0])
        self.assertEqual("/observed_request/text", captured["request_text_pointer"])
        self.assertEqual(["/payload"], captured["output_text_pointers"])
        self.assertEqual(
            {"observed_request": {"text": "STREAM_CONTRACT_OK"}}, captured["request_template"]
        )

    def test_capture_uses_operator_output_pointers_verified_against_data(self) -> None:
        request = b'{"observed_request":{"text":"STREAM_CONTRACT_OK"}}\n'
        output = (
            b'{"observed_event":"delta","delta":"STREAM_CONTRACT_OK"}\n'
            b'{"observed_event":"complete","final":{"text":"STREAM_CONTRACT_OK"}}\n'
        )

        def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[bytes]:
            return CompletedProcess(argv, 0, output, b"")

        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "raw"
            captured = capture_contract(
                "agy",
                "captured-model-id",
                request,
                raw,
                completion_pointer="/observed_event",
                completion_value="complete",
                output_text_pointers=("/final/text",),
                run=fake_run,
            )
            self.assertEqual(["/final/text"], captured["output_text_pointers"])
            with self.assertRaises(ContractCaptureError):
                capture_contract(
                    "agy",
                    "captured-model-id",
                    request,
                    raw,
                    completion_pointer="/observed_event",
                    completion_value="complete",
                    output_text_pointers=("/final/missing",),
                    run=fake_run,
                )

    def test_capture_rejects_unusable_probes(self) -> None:
        request = b'{"observed_request":{"text":"STREAM_CONTRACT_OK"}}\n'
        good_complete = b'{"observed_event":"complete","payload":"STREAM_CONTRACT_OK"}\n'
        cases = {
            "non-zero exit": (3, good_complete),
            "non-JSON line": (0, b"not json\n" + good_complete),
            "absent marker": (0, b'{"observed_event":"complete","payload":"other"}\n'),
            "missing completion": (0, b'{"observed_event":"delta","payload":"STREAM_CONTRACT_OK"}\n'),
            "empty stdout": (0, b""),
        }
        for label, (code, output) in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as temporary:

                def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[bytes]:
                    return CompletedProcess(argv, code, output, b"")

                with self.assertRaises(ContractCaptureError):
                    capture_contract(
                        "agy",
                        "captured-model-id",
                        request,
                        Path(temporary) / "raw",
                        completion_pointer="/observed_event",
                        completion_value="complete",
                        run=fake_run,
                    )

    def test_capture_rejects_request_without_exact_marker(self) -> None:
        def fake_run(argv: list[str], **kwargs: object) -> CompletedProcess[bytes]:
            raise AssertionError("probe must not run")

        for request in (
            b'{"observed_request":{"text":"say STREAM_CONTRACT_OK"}}\n',
            b'{"a":"STREAM_CONTRACT_OK","b":"STREAM_CONTRACT_OK"}\n',
            b'{"a":"STREAM_CONTRACT_OK"}\n{"a":"STREAM_CONTRACT_OK"}\n',
            b'["STREAM_CONTRACT_OK"]\n',
        ):
            with self.subTest(request), tempfile.TemporaryDirectory() as temporary:
                with self.assertRaises(ContractCaptureError):
                    capture_contract(
                        "agy",
                        "captured-model-id",
                        request,
                        Path(temporary) / "raw",
                        completion_pointer="/observed_event",
                        completion_value="complete",
                        run=fake_run,
                    )

    def test_publish_rejects_unsafe_fixture_without_writing(self) -> None:
        captured = {
            "antigravity_version": "1.0.0",
            "model_identifier": "captured-model-id",
            "request_text_pointer": "/text",
            "output_text_pointers": ["/payload"],
            "completion_pointer": "/observed_event",
            "completion_value": "complete",
            "request_template": {"text": "STREAM_CONTRACT_OK"},
            "sample_output_events": [
                {
                    "observed_event": "complete",
                    "payload": "STREAM_CONTRACT_OK",
                    "where": "C:\\Users\\someone\\project",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "stream-contract.json"
            with self.assertRaises(ValueError):
                publish_contract_fixture(captured, destination, rules=())
            self.assertFalse(destination.exists())

    def test_select_model_accepts_only_listed_first_column(self) -> None:
        listing = "Fetching available models...\nmodel-a\tModel A\nmodel-b\tModel B\n"
        self.assertEqual("model-b", select_model(listing, "model-b"))
        for rejected in ("Model B", "model-c", "Fetching", ""):
            with self.subTest(rejected), self.assertRaises(ContractCaptureError):
                select_model(listing, rejected)

    def test_cli_writes_private_files_at_relative_paths(self) -> None:
        answers = iter(
            [
                "claude-sonnet-5-5-high",
                "first-party example",
                '{"observed_request":{"text":"STREAM_CONTRACT_OK"}}',
                "/observed_request/text",
                "/payload",
                "/observed_event",
                '"complete"',
            ]
        )
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary:
            os.chdir(temporary)
            try:
                raw = Path("private") / "contract"
                raw.mkdir(parents=True)
                (raw / "models.txt").write_text("claude-sonnet-5-5-high\tName\n", "utf-8")
                with contextlib.redirect_stdout(io.StringIO()):
                    selected = main(
                        [
                            "select-model",
                            "--models-file",
                            str(raw / "models.txt"),
                            "--output",
                            str(raw / "model.txt"),
                        ],
                        prompt=lambda _: next(answers),
                    )
                    discovered = main(
                        ["discover", "--raw-root", str(raw)], prompt=lambda _: next(answers)
                    )
                self.assertEqual((0, 0), (selected, discovered))
                self.assertEqual("claude-sonnet-5-5-high\n", (raw / "model.txt").read_text("utf-8"))
                discovery = json.loads((raw / "discovery.json").read_text("utf-8"))
                self.assertEqual(["/payload"], discovery["output_text_pointers"])
                self.assertEqual("complete", discovery["completion_value"])
            finally:
                os.chdir(original)

    def test_validate_fixture_checks_pointers_against_samples(self) -> None:
        valid = {
            "schema_version": 1,
            "antigravity_version": "1.0.0",
            "model_identifier": "captured-model-id",
            "request_text_pointer": "/text",
            "output_text_pointers": ["/payload"],
            "completion_pointer": "/observed_event",
            "completion_value": "complete",
            "request_template": {"text": "STREAM_CONTRACT_OK"},
            "sample_output_events": [
                {"observed_event": "complete", "payload": "STREAM_CONTRACT_OK"}
            ],
        }
        broken = {
            "wrong request pointer": {"request_text_pointer": "/missing"},
            "no completion sample": {"completion_value": "done"},
            "output pointer without marker": {"output_text_pointers": ["/observed_event"]},
            "unversioned": {"antigravity_version": "unknown"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stream-contract.json"
            path.write_bytes(canonical_json(valid))
            validate_fixture(path)
            for label, change in broken.items():
                with self.subTest(label):
                    path.write_bytes(canonical_json({**valid, **change}))
                    with self.assertRaises(ContractCaptureError):
                        validate_fixture(path)


if __name__ == "__main__":
    unittest.main()
