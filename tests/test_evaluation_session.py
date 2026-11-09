from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from evaluation.antigravity import InfrastructureFailure, ProcessCleanupError
from evaluation.isolation import (
    ProtocolIdentity,
    create_run_layout,
    remove_runtime_root,
)
from evaluation.parser import TutorTurn
from evaluation.schema import (
    FixtureIdentities,
    RUN_SCHEMA_V2,
    RunRecord,
    Scenario,
    SuiteManifest,
    canonical_json,
    fixture_root,
    identities_for_scenario,
    load_run_record,
    load_suite_manifest,
)


CLI_SUITE_MANIFEST = SuiteManifest(
    1,
    "suite",
    ("synthetic",),
    "rubric.json",
    "baseline-v1",
)
from evaluation.session import (
    ConsoleEvaluator,
    EvaluatorDecision,
    RuntimeCleanupError,
    SessionProgress,
    execute_isolated_run,
    infrastructure_record,
    run_session,
    verify_run_isolation,
)


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
        source_fixture_id=None,
    )


def fixture_identities() -> FixtureIdentities:
    return FixtureIdentities("a" * 64, "b" * 64, "c" * 64)


def baseline_identities(scenario_id: str) -> FixtureIdentities:
    manifest = load_suite_manifest(fixture_root() / "suites/baseline-v1.json")
    return identities_for_scenario(manifest, scenario_id)


def identity() -> ProtocolIdentity:
    return ProtocolIdentity(
        repository_commit="0" * 40,
        protocol_version="1.0.0",
        bundle_sha256="a" * 64,
    )


class FakeTutor:
    model = "synthetic-model"
    runtime_version = "synthetic-runtime"

    def __init__(
        self,
        *,
        failure_at: int | None = None,
        failure: BaseException | None = None,
        close_failure: BaseException | None = None,
        start_failure: BaseException | None = None,
        turn_texts: list[str] | None = None,
    ) -> None:
        self.messages: list[str] = []
        self.events: list[str] = []
        self.failure_at = failure_at
        self.failure = failure
        self.close_failure = close_failure
        self.start_failure = start_failure
        self.turn_texts = list(turn_texts or [])
        self.close_calls = 0

    def start(self) -> None:
        self.events.append("start")
        if self.start_failure is not None:
            raise self.start_failure

    def send(self, text: str) -> TutorTurn:
        self.messages.append(text)
        self.events.append(f"send-{len(self.messages)}")
        if self.failure_at == len(self.messages) and self.failure is not None:
            raise self.failure
        text = (
            self.turn_texts[len(self.messages) - 1]
            if len(self.messages) <= len(self.turn_texts)
            else f"tutor-{len(self.messages)}"
        )
        return TutorTurn(
            text=text,
            event_count=1,
            completed=True,
        )

    def close(self) -> int:
        self.close_calls += 1
        self.events.append("close")
        if self.close_failure is not None:
            raise self.close_failure
        return 0


class ScriptedEvaluator:
    def __init__(self, decisions: list[EvaluatorDecision]) -> None:
        self.decisions = list(decisions)
        self.contexts: list[object] = []

    def decide(self, context: object) -> EvaluatorDecision:
        self.contexts.append(context)
        if not self.decisions:
            raise AssertionError("unexpected evaluator call")
        return self.decisions.pop(0)


class ExplodingEvaluator:
    def decide(self, context: object) -> EvaluatorDecision:
        raise AssertionError("infrastructure failure must stop before evaluator input")


def respond(number: int) -> EvaluatorDecision:
    return EvaluatorDecision("respond", f"learner-{number}", None)


def stop(reason: str = "observable_outcome") -> EvaluatorDecision:
    return EvaluatorDecision("stop", None, reason)  # type: ignore[arg-type]


class EvaluationSessionLoopTests(unittest.TestCase):
    def test_bootstrap_does_not_consume_response_budget(self) -> None:
        tutor = FakeTutor()
        evaluator = ScriptedEvaluator([respond(number) for number in range(1, 17)])

        record = run_session(
            scenario(),
            tutor,
            evaluator,  # type: ignore[arg-type]
            identity(),
            "Synthetic public-launcher bootstrap.",
            "cap-test",
            fixture_identities=fixture_identities(),
        )

        self.assertEqual(15, record.learner_response_count)
        self.assertEqual("maximum_learner_responses", record.stop_reason)
        self.assertEqual(16, len(tutor.messages))
        self.assertEqual("Synthetic public-launcher bootstrap.", tutor.messages[0])
        self.assertEqual(16, len(record.turns))
        self.assertEqual(len(record.turns) - 1, record.learner_response_count)

    def test_evaluator_stop_precedes_cap_after_fifteenth_response(self) -> None:
        evaluator = ScriptedEvaluator(
            [respond(number) for number in range(1, 16)]
            + [stop("observable_outcome")]
        )

        record = run_session(
            scenario(),
            FakeTutor(),
            evaluator,  # type: ignore[arg-type]
            identity(),
            "bootstrap",
            "precedence-test",
            fixture_identities=fixture_identities(),
        )

        self.assertEqual(15, record.learner_response_count)
        self.assertEqual("observable_outcome", record.stop_reason)

    def test_all_manual_stop_reasons_are_preserved(self) -> None:
        for reason in (
            "observable_outcome",
            "completion_without_evidence",
            "critical_pedagogical_failure",
        ):
            with self.subTest(reason=reason):
                record = run_session(
                    scenario(),
                    FakeTutor(),
                    ScriptedEvaluator([stop(reason)]),  # type: ignore[arg-type]
                    identity(),
                    "bootstrap",
                    "stop-test",
                    fixture_identities=fixture_identities(),
                )
                self.assertEqual(reason, record.stop_reason)

    def test_progress_is_updated_before_each_evaluator_call(self) -> None:
        progress = SessionProgress([], 0)

        class InspectingEvaluator:
            calls = 0

            def decide(self, context: object) -> EvaluatorDecision:
                self.calls += 1
                self_outer.assertEqual(self.calls, len(progress.turns))
                self_outer.assertEqual(
                    progress.learner_response_count,
                    len(context.learner_responses),  # type: ignore[attr-defined]
                )
                return respond(1) if self.calls == 1 else stop()

        self_outer = self
        record = run_session(
            scenario(),
            FakeTutor(),
            InspectingEvaluator(),  # type: ignore[arg-type]
            identity(),
            "bootstrap",
            "progress-test",
            fixture_identities=fixture_identities(),
            progress=progress,
        )

        self.assertEqual(2, len(progress.turns))
        self.assertEqual(1, progress.learner_response_count)
        self.assertEqual(progress.turns, list(record.turns))

    def test_infrastructure_failure_stops_before_evaluator(self) -> None:
        failure = InfrastructureFailure("quota", "synthetic quota failure")
        record = run_session(
            scenario(),
            FakeTutor(failure_at=1, failure=failure),
            ExplodingEvaluator(),  # type: ignore[arg-type]
            identity(),
            "bootstrap",
            "infrastructure-test",
            fixture_identities=fixture_identities(),
        )

        self.assertEqual("infrastructure_failure", record.stop_reason)
        self.assertEqual("quota", record.infrastructure_failure)
        self.assertEqual(0, record.learner_response_count)
        self.assertEqual((), record.turns)

    def test_only_completed_turns_are_retained_when_later_send_fails(self) -> None:
        progress = SessionProgress([], 0)
        failure = InfrastructureFailure("network", "synthetic")
        record = run_session(
            scenario(),
            FakeTutor(failure_at=3, failure=failure),
            ScriptedEvaluator([respond(1), respond(2)]),  # type: ignore[arg-type]
            identity(),
            "bootstrap",
            "partial-test",
            fixture_identities=fixture_identities(),
            progress=progress,
        )

        self.assertEqual(1, record.learner_response_count)
        self.assertEqual(2, len(record.turns))
        self.assertEqual("network", record.infrastructure_failure)
        self.assertEqual(len(record.turns) - 1, record.learner_response_count)

    def test_empty_completed_tutor_turn_is_runtime_infrastructure(self) -> None:
        record = run_session(
            scenario(),
            FakeTutor(turn_texts=[" \t\r\n"]),
            ExplodingEvaluator(),  # type: ignore[arg-type]
            identity(),
            "bootstrap",
            "empty-turn",
            fixture_identities=fixture_identities(),
        )

        self.assertEqual("infrastructure_failure", record.stop_reason)
        self.assertEqual("runtime", record.infrastructure_failure)
        self.assertEqual(0, record.learner_response_count)
        self.assertEqual((), record.turns)

    def test_empty_completed_turn_private_record_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / ".semantic-runs" / "suite-a" / "synthetic"
            run_dir.mkdir(parents=True)
            path = run_dir / "run-record.json"

            record = run_session(
                scenario(),
                FakeTutor(turn_texts=[""]),
                ExplodingEvaluator(),  # type: ignore[arg-type]
                identity(),
                "bootstrap",
                "empty-record",
                fixture_identities=fixture_identities(),
                record_path=path,
            )

            self.assertEqual(record, load_run_record(path))
            self.assertEqual("runtime", record.infrastructure_failure)
            self.assertEqual((), record.turns)

    def test_record_path_must_be_private_and_must_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "record.json"
            with self.assertRaisesRegex(ValueError, "semantic-runs"):
                run_session(
                    scenario(),
                    FakeTutor(),
                    ScriptedEvaluator([stop()]),  # type: ignore[arg-type]
                    identity(),
                    "bootstrap",
                    "path-test",
                    fixture_identities=fixture_identities(),
                    record_path=outside,
                )

            private = root / ".semantic-runs" / "suite" / "synthetic"
            private.mkdir(parents=True)
            record_path = private / "run-record.json"
            record_path.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(FileExistsError, "already exists"):
                run_session(
                    scenario(),
                    FakeTutor(),
                    ScriptedEvaluator([stop()]),  # type: ignore[arg-type]
                    identity(),
                    "bootstrap",
                    "path-test",
                    fixture_identities=fixture_identities(),
                    record_path=record_path,
                )
            self.assertEqual("sentinel", record_path.read_text(encoding="utf-8"))

    def test_private_record_round_trips_through_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / ".semantic-runs" / "suite-a" / "synthetic"
            run_dir.mkdir(parents=True)
            path = run_dir / "run-record.json"
            expected = run_session(
                scenario(),
                FakeTutor(),
                ScriptedEvaluator([stop()]),  # type: ignore[arg-type]
                identity(),
                "bootstrap",
                "roundtrip",
                fixture_identities=fixture_identities(),
                record_path=path,
            )

            self.assertEqual(expected, load_run_record(path))
            self.assertEqual(RUN_SCHEMA_V2, expected.schema_version)
            self.assertEqual("suite-a", expected.suite_id)


class ConsoleEvaluatorTests(unittest.TestCase):
    def test_display_contains_full_persona_and_rejects_empty_response(self) -> None:
        answers = iter(["respond", "  ", "learner answer"])
        output = io.StringIO()
        evaluator = ConsoleEvaluator(
            input_fn=lambda prompt: next(answers),
            output=output,
        )
        tutor = TutorTurn("latest tutor prose", 1, True)
        context = type(
            "Context",
            (),
            {
                "scenario": scenario(),
                "tutor_turns": (tutor,),
                "learner_responses": (),
            },
        )()

        decision = evaluator.decide(context)

        self.assertEqual(EvaluatorDecision("respond", "learner answer", None), decision)
        displayed = output.getvalue()
        for expected in (
            "Synthetic knowledge.",
            "Synthetic misconception.",
            "May revise after evidence.",
            "Must not reveal hidden answers.",
            "Respond to the latest tutor turn.",
            "latest tutor prose",
            "Learner responses used: 0/15",
        ):
            self.assertIn(expected, displayed)
        self.assertNotIn("learner answer", displayed)

    def test_stop_choices_map_to_exact_reasons(self) -> None:
        choices = {
            "outcome": "observable_outcome",
            "completion-without-evidence": "completion_without_evidence",
            "critical-failure": "critical_pedagogical_failure",
        }
        for choice, expected in choices.items():
            with self.subTest(choice=choice):
                evaluator = ConsoleEvaluator(
                    input_fn=lambda prompt, value=choice: value,
                    output=io.StringIO(),
                )
                context = type(
                    "Context",
                    (),
                    {
                        "scenario": scenario(),
                        "tutor_turns": (TutorTurn("turn", 1, True),),
                        "learner_responses": (),
                    },
                )()
                self.assertEqual(expected, evaluator.decide(context).stop_reason)


class InfrastructureRecordTests(unittest.TestCase):
    def test_record_is_plain_exact_schema_valid_json(self) -> None:
        from evaluation.schema import TurnRecord

        progress = SessionProgress(
            [TurnRecord(1, "bootstrap", "completed")],
            0,
        )
        document = infrastructure_record(
            scenario=scenario(),
            identity=identity(),
            run_id="run",
            suite_id="suite",
            runtime_version="1.5.2",
            model_identifier="model",
            kind="runtime",
            progress=progress,
            fixture_identities=fixture_identities(),
        )

        self.assertIs(type(document), dict)
        self.assertEqual(RUN_SCHEMA_V2, document["schema_version"])
        self.assertEqual(
            {
                "schema_version",
                "run_id",
                "suite_id",
                "scenario_id",
                "repository_commit",
                "protocol_version",
                "protocol_sha256",
                "runtime",
                "runtime_version",
                "model_identifier",
                "learner_response_count",
                "stop_reason",
                "infrastructure_failure",
                "turns",
                "scenario_sha256",
                "rubric_sha256",
                "suite_sha256",
            },
            set(document),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            path.write_bytes(canonical_json(document))
            loaded = load_run_record(path)
        self.assertEqual("runtime", loaded.infrastructure_failure)
        self.assertEqual("completed", loaded.turns[0].tutor)

    def test_record_never_accepts_exception_provider_or_path_text(self) -> None:
        document = infrastructure_record(
            scenario=scenario(),
            identity=identity(),
            run_id="run",
            suite_id="suite",
            runtime_version="1.5.2",
            model_identifier="model",
            kind="authentication",
            progress=SessionProgress([], 0),
            fixture_identities=fixture_identities(),
        )
        encoded = canonical_json(document).decode("utf-8")
        self.assertNotIn("exception", encoded.lower())
        self.assertNotIn("provider", encoded.lower())
        self.assertNotIn("C:\\", encoded)


class IsolatedRunTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.user_home = self.root / "home"
        self.repository = self.user_home / "repo"
        self.runtime_base = self.user_home / "runtime"
        self.repository.mkdir(parents=True)
        self.runtime_base.mkdir()
        self.raw_root = self.repository / ".semantic-runs"

    def layout(self):
        return create_run_layout(
            self.repository,
            "suite",
            "synthetic",
            raw_root=self.raw_root,
            runtime_base=self.runtime_base,
            user_home=self.user_home,
        )

    def execute(self, layout, tutor: FakeTutor, evaluator=None) -> RunRecord:
        return execute_isolated_run(
            layout,
            self.repository,
            "suite",
            scenario(),
            lambda _: tutor,
            evaluator or ScriptedEvaluator([stop()]),  # type: ignore[arg-type]
            identity(),
            "run",
            fixture_identities=fixture_identities(),
            model_identifier="validated-model",
            runtime_version="1.5.2",
        )

    def test_success_saves_record_snapshots_and_removes_runtime(self) -> None:
        layout = self.layout()
        tutor = FakeTutor()

        record = self.execute(layout, tutor)

        self.assertEqual("observable_outcome", record.stop_reason)
        self.assertTrue((layout.run_dir / "run-record.json").is_file())
        self.assertTrue((layout.run_dir / "learner-records").is_dir())
        self.assertTrue((layout.run_dir / "skipped-links.json").is_file())
        self.assertFalse(layout.runtime_root.exists())
        self.assertTrue(layout.run_dir.exists())
        verify_run_isolation(layout.run_dir, self.repository)

    def test_infrastructure_send_failure_returns_record_and_cleans(self) -> None:
        layout = self.layout()
        tutor = FakeTutor(
            failure_at=1,
            failure=InfrastructureFailure("quota", "private provider prose"),
        )

        record = self.execute(layout, tutor, ExplodingEvaluator())

        self.assertEqual("quota", record.infrastructure_failure)
        self.assertFalse(layout.runtime_root.exists())
        self.assertEqual(record, load_run_record(layout.run_dir / "run-record.json"))

    def test_unexpected_failure_preserves_object_and_completed_turns(self) -> None:
        layout = self.layout()
        original = RuntimeError("private C:\\Users\\name provider prose")
        tutor = FakeTutor(failure_at=3, failure=original)

        with self.assertRaises(RuntimeError) as raised:
            self.execute(
                layout,
                tutor,
                ScriptedEvaluator([respond(1), respond(2)]),
            )

        self.assertIs(original, raised.exception)
        record = load_run_record(layout.run_dir / "run-record.json")
        self.assertEqual("runtime", record.infrastructure_failure)
        self.assertEqual(2, len(record.turns))
        self.assertEqual(1, record.learner_response_count)
        failure = json.loads((layout.run_dir / "failure.json").read_text("utf-8"))
        self.assertEqual(
            {"exception_type": "RuntimeError", "phase": "session"},
            failure,
        )
        self.assertNotIn("private", json.dumps(failure))
        self.assertFalse(layout.runtime_root.exists())

    def test_keyboard_interrupt_is_recorded_cleaned_and_reraised(self) -> None:
        layout = self.layout()
        interrupt = KeyboardInterrupt()
        tutor = FakeTutor(failure_at=1, failure=interrupt)

        with self.assertRaises(KeyboardInterrupt) as raised:
            self.execute(layout, tutor, ExplodingEvaluator())

        self.assertIs(interrupt, raised.exception)
        self.assertEqual(
            "runtime",
            load_run_record(layout.run_dir / "run-record.json").infrastructure_failure,
        )
        self.assertFalse(layout.runtime_root.exists())

    def test_start_failure_still_closes_and_records_start_phase(self) -> None:
        layout = self.layout()
        original = RuntimeError("start secret")
        tutor = FakeTutor(start_failure=original)

        with self.assertRaises(RuntimeError) as raised:
            self.execute(layout, tutor)

        self.assertIs(original, raised.exception)
        self.assertEqual(1, tutor.close_calls)
        self.assertEqual(
            {"exception_type": "RuntimeError", "phase": "start"},
            json.loads((layout.run_dir / "failure.json").read_text("utf-8")),
        )
        self.assertFalse(layout.runtime_root.exists())

    def test_factory_failure_records_without_tutor_and_cleans(self) -> None:
        layout = self.layout()
        original = RuntimeError("factory secret")

        with self.assertRaises(RuntimeError) as raised:
            execute_isolated_run(
                layout,
                self.repository,
                "suite",
                scenario(),
                lambda _: (_ for _ in ()).throw(original),
                ScriptedEvaluator([stop()]),  # type: ignore[arg-type]
                identity(),
                "run",
                fixture_identities=fixture_identities(),
                model_identifier="validated-model",
                runtime_version="1.5.2",
            )

        self.assertIs(original, raised.exception)
        self.assertFalse(layout.runtime_root.exists())
        self.assertTrue((layout.run_dir / "run-record.json").is_file())

    def test_close_failure_after_success_does_not_skip_snapshot_or_removal(self) -> None:
        layout = self.layout()
        tutor = FakeTutor(close_failure=RuntimeError("private close detail"))

        with self.assertRaises(RuntimeCleanupError) as raised:
            self.execute(layout, tutor)

        self.assertEqual(("close",), raised.exception.failed_steps)
        self.assertTrue((layout.run_dir / "learner-records").is_dir())
        self.assertFalse(layout.runtime_root.exists())

    def test_unconfirmed_process_cleanup_preserves_runtime_for_retry(self) -> None:
        layout = self.layout()
        tutor = FakeTutor(close_failure=ProcessCleanupError())

        with self.assertRaises(RuntimeCleanupError) as raised:
            self.execute(layout, tutor)

        self.assertEqual(("close",), raised.exception.failed_steps)
        self.assertTrue(raised.exception.preserve_runtime)
        self.assertTrue(layout.runtime_root.exists())
        self.assertFalse((layout.run_dir / "learner-records").exists())

    def test_close_failure_after_session_error_adds_fixed_note(self) -> None:
        layout = self.layout()
        original = RuntimeError("session secret")
        tutor = FakeTutor(
            failure_at=1,
            failure=original,
            close_failure=RuntimeError("cleanup secret"),
        )

        with self.assertRaises(RuntimeError) as raised:
            self.execute(layout, tutor, ExplodingEvaluator())

        self.assertIs(original, raised.exception)
        self.assertTrue(
            any(
                note == "cleanup step close failed: RuntimeError"
                for note in getattr(original, "__notes__", ())
            )
        )
        self.assertFalse(layout.runtime_root.exists())

    def test_snapshot_failure_still_removes_runtime(self) -> None:
        layout = self.layout()
        with mock.patch(
            "evaluation.session.snapshot_learner_records",
            side_effect=RuntimeError("private snapshot path"),
        ):
            with self.assertRaises(RuntimeCleanupError) as raised:
                self.execute(layout, FakeTutor())

        self.assertEqual(("snapshot",), raised.exception.failed_steps)
        self.assertFalse(layout.runtime_root.exists())

    def test_base_exception_cleanup_failure_still_runs_later_steps(self) -> None:
        layout = self.layout()
        interrupt = KeyboardInterrupt()
        tutor = FakeTutor(close_failure=interrupt)
        events: list[str] = []
        real_remove = remove_runtime_root

        def fail_snapshot(value):
            events.append("snapshot")
            raise RuntimeError("private snapshot detail")

        def remove(value, repository):
            events.append("remove-runtime")
            real_remove(value, repository)

        with (
            mock.patch("evaluation.session.snapshot_learner_records", fail_snapshot),
            mock.patch("evaluation.session.remove_runtime_root", remove),
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                self.execute(layout, tutor)

        self.assertIs(interrupt, raised.exception)
        self.assertEqual(["snapshot", "remove-runtime"], events)
        self.assertIn(
            "cleanup step snapshot failed: RuntimeError",
            getattr(interrupt, "__notes__", ()),
        )
        self.assertFalse(layout.runtime_root.exists())

    def test_system_exit_cleanup_failure_is_preserved_after_removal(self) -> None:
        layout = self.layout()
        interrupt = SystemExit(17)
        events: list[str] = []
        real_remove = remove_runtime_root

        def fail_snapshot(value):
            events.append("snapshot")
            raise interrupt

        def remove(value, repository):
            events.append("remove-runtime")
            real_remove(value, repository)

        with (
            mock.patch("evaluation.session.snapshot_learner_records", fail_snapshot),
            mock.patch("evaluation.session.remove_runtime_root", remove),
        ):
            with self.assertRaises(SystemExit) as raised:
                self.execute(layout, FakeTutor())

        self.assertIs(interrupt, raised.exception)
        self.assertEqual(["snapshot", "remove-runtime"], events)
        self.assertFalse(layout.runtime_root.exists())

    def test_all_cleanup_steps_are_attempted_in_fixed_order(self) -> None:
        layout = self.layout()
        events: list[str] = []
        tutor = FakeTutor(close_failure=RuntimeError("close"))
        real_snapshot = __import__(
            "evaluation.isolation", fromlist=["snapshot_learner_records"]
        ).snapshot_learner_records
        real_remove = remove_runtime_root

        def snapshot(value):
            events.append("snapshot")
            real_snapshot(value)
            raise RuntimeError("snapshot")

        def remove(value, repository):
            events.append("remove-runtime")
            real_remove(value, repository)
            raise RuntimeError("remove")

        original_close = tutor.close

        def close():
            events.append("close")
            return original_close()

        tutor.close = close  # type: ignore[method-assign]
        with (
            mock.patch("evaluation.session.snapshot_learner_records", snapshot),
            mock.patch("evaluation.session.remove_runtime_root", remove),
        ):
            with self.assertRaises(RuntimeCleanupError) as raised:
                self.execute(layout, tutor)

        self.assertEqual(["close", "snapshot", "remove-runtime"], events)
        self.assertEqual(
            ("close", "snapshot", "remove-runtime"),
            raised.exception.failed_steps,
        )
        self.assertFalse(layout.runtime_root.exists())

    def test_failure_evidence_never_overwrites_existing_record(self) -> None:
        layout = self.layout()
        path = layout.run_dir / "run-record.json"
        sentinel = b"existing private record"
        path.write_bytes(sentinel)

        with self.assertRaises(FileExistsError):
            self.execute(layout, FakeTutor())

        self.assertEqual(sentinel, path.read_bytes())
        self.assertFalse(layout.runtime_root.exists())

    def test_verify_rejects_live_or_tampered_runtime_context(self) -> None:
        layout = self.layout()
        with self.assertRaisesRegex(ValueError, "still exists"):
            verify_run_isolation(layout.run_dir, self.repository)

        self.execute(layout, FakeTutor())
        context_path = layout.run_dir / "runtime-context.json"
        original = json.loads(context_path.read_text("utf-8"))
        for key, value in (
            ("runtime_outside_repository", False),
            ("local_rule_check_passed", False),
            ("rule_boundary", "invalid"),
            ("user_home_rule_paths", ["private/path"]),
            (
                "above_home_markers",
                [{"levels_above_home": 0, "marker": "AGENTS.md"}],
            ),
        ):
            with self.subTest(key=key):
                document = dict(original)
                document[key] = value
                context_path.write_bytes(canonical_json(document))
                with self.assertRaises(ValueError):
                    verify_run_isolation(layout.run_dir, self.repository)
        context_path.write_bytes(canonical_json(original))
        verify_run_isolation(layout.run_dir, self.repository)

    def test_verify_rejects_repository_runtime_and_missing_record(self) -> None:
        layout = self.layout()
        remove_runtime_root(layout, self.repository)
        context_path = layout.run_dir / "runtime-context.json"
        document = json.loads(context_path.read_text("utf-8"))
        document["runtime_root"] = str(self.repository / "inside")
        context_path.write_bytes(canonical_json(document))
        with self.assertRaisesRegex(ValueError, "outside"):
            verify_run_isolation(layout.run_dir, self.repository)

    def test_verify_rejects_runtime_root_that_contains_repository(self) -> None:
        layout = self.layout()
        remove_runtime_root(layout, self.repository)
        context_path = layout.run_dir / "runtime-context.json"
        document = json.loads(context_path.read_text("utf-8"))
        document["runtime_root"] = str(self.user_home)
        context_path.write_bytes(canonical_json(document))

        with self.assertRaisesRegex(ValueError, "outside"):
            verify_run_isolation(layout.run_dir, self.repository)


class EvaluationCliTests(unittest.TestCase):
    def test_run_prechecks_complete_before_layout_creation(self) -> None:
        from evaluation import cli

        events: list[str] = []
        preflight = type(
            "Preflight",
            (),
            {
                "model": "validated-model",
                "runtime_version": "1.5.2",
                "contract": object(),
                "identity": identity(),
            },
        )()
        fake_layout = type(
            "Layout",
            (),
            {"run_dir": Path(".semantic-runs/suite/synthetic")},
        )()
        record = RunRecord(
            RUN_SCHEMA_V2,
            "suite-synthetic",
            "suite",
            "synthetic",
            "0" * 40,
            "1.0.0",
            "a" * 64,
            "antigravity",
            "1.5.2",
            "validated-model",
            0,
            "observable_outcome",
            None,
            (),
            "a" * 64,
            "b" * 64,
            "c" * 64,
        )

        with (
            mock.patch.object(
                cli,
                "_preflight",
                side_effect=lambda *args, **kwargs: events.append("preflight")
                or preflight,
            ),
            mock.patch.object(
                cli,
                "create_run_layout",
                side_effect=lambda *args, **kwargs: events.append("layout")
                or fake_layout,
            ),
            mock.patch.object(
                cli,
                "execute_isolated_run",
                side_effect=lambda *args, **kwargs: events.append("execute")
                or record,
            ),
            mock.patch.object(
                cli,
                "verify_run_isolation",
                side_effect=lambda *args, **kwargs: events.append("verify"),
            ),
            mock.patch.object(cli, "load_scenario", return_value=scenario()),
            mock.patch.object(cli, "_suite_manifest", return_value=CLI_SUITE_MANIFEST),
            mock.patch.object(
                cli,
                "identities_for_scenario",
                return_value=fixture_identities(),
            ),
        ):
            result = cli.main(
                [
                    "run",
                    "--suite-id",
                    "suite",
                    "--scenario",
                    "synthetic",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=io.StringIO(),
            )

        self.assertEqual(0, result)
        self.assertEqual(["preflight", "layout", "execute", "verify"], events)

    def test_run_removes_runtime_if_handoff_raises_after_layout(self) -> None:
        from evaluation import cli

        layout = type("Layout", (), {"run_dir": Path("run")})()
        events: list[str] = []
        error = io.StringIO()
        preflight = type(
            "Preflight",
            (),
            {
                "model": "validated-model",
                "runtime_version": "1.5.2",
                "contract": object(),
                "identity": identity(),
            },
        )()
        with (
            mock.patch.object(cli, "_preflight", return_value=preflight),
            mock.patch.object(cli, "load_scenario", return_value=scenario()),
            mock.patch.object(cli, "_suite_manifest", return_value=CLI_SUITE_MANIFEST),
            mock.patch.object(
                cli,
                "identities_for_scenario",
                return_value=fixture_identities(),
            ),
            mock.patch.object(cli, "create_run_layout", return_value=layout),
            mock.patch.object(
                cli,
                "execute_isolated_run",
                side_effect=RuntimeError(
                    "API_KEY=secret C:\\Users\\private provider prose"
                ),
            ),
            mock.patch.object(
                cli,
                "remove_runtime_root",
                side_effect=lambda *args: events.append("remove"),
            ),
        ):
            result = cli.main(
                [
                    "run",
                    "--suite-id",
                    "suite",
                    "--scenario",
                    "synthetic",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=error,
            )
        self.assertEqual(2, result)
        self.assertEqual(["remove"], events)
        self.assertEqual(
            "BLOCKED: Semantic evaluation run failed.\n",
            error.getvalue(),
        )
        self.assertNotIn("secret", error.getvalue())
        self.assertNotIn("Users", error.getvalue())
        self.assertNotIn("provider prose", error.getvalue())

    def test_preflight_uses_fresh_exact_model_version_branch_and_git_checks(self) -> None:
        from evaluation import cli

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            model_file = repository / ".semantic-runs" / "contract" / "model.txt"
            model_file.parent.mkdir(parents=True)
            model_file.write_text("captured-model\n", encoding="utf-8")
            calls: list[tuple[str, ...]] = []

            def fake_run(argv, **kwargs):
                command = tuple(argv)
                calls.append(command)
                if command == ("git", "branch", "--show-current"):
                    return CompletedProcess(argv, 0, "feat/semantic-evaluation-runtime-ux\n", "")
                if command == ("agy", "models"):
                    return CompletedProcess(argv, 0, "captured-model\tName\n", "")
                if command == ("agy", "--version"):
                    return CompletedProcess(argv, 0, "1.5.2\n", "")
                return CompletedProcess(argv, 0, "", "")

            contract = type(
                "Contract",
                (),
                {
                    "model_identifier": "captured-model",
                    "antigravity_version": "1.5.2",
                },
            )()
            with (
                mock.patch.object(cli, "validate_fixture"),
                mock.patch.object(cli, "load_stream_contract", return_value=contract),
                mock.patch.object(cli, "capture_protocol_identity", return_value=identity()),
                mock.patch.object(cli, "assert_protocol_unchanged"),
            ):
                result = cli._preflight(repository, model_file, run_process=fake_run)

        self.assertEqual("captured-model", result.model)
        self.assertEqual("1.5.2", result.runtime_version)
        self.assertIn(("agy", "models"), calls)
        self.assertIn(("agy", "--version"), calls)
        self.assertIn(("git", "diff", "--exit-code", "--", "core", "dist"), calls)
        self.assertIn(("git", "check-ignore", "--quiet", ".semantic-runs/"), calls)
        self.assertIn(("git", "ls-files", "--", ".semantic-runs"), calls)

    def test_preflight_refuses_before_layout_without_leaking_process_output(self) -> None:
        from evaluation import cli

        secret = "API_KEY=secret C:\\Users\\private provider transcript"

        def fail_run(argv, **kwargs):
            return CompletedProcess(argv, 1, secret, secret)

        error = io.StringIO()
        with mock.patch.object(cli, "create_run_layout") as create:
            result = cli.main(
                [
                    "preflight",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=error,
                run_process=fail_run,
            )

        self.assertEqual(2, result)
        create.assert_not_called()
        self.assertEqual(
            "BLOCKED: Semantic evaluation precheck refused.\n",
            error.getvalue(),
        )
        self.assertNotIn("secret", error.getvalue())
        self.assertNotIn("Users", error.getvalue())
        self.assertNotIn("provider transcript", error.getvalue())

    def test_unknown_scenario_and_existing_run_refuse_before_creation(self) -> None:
        from evaluation import cli

        for load_error in (
            FileNotFoundError("private path"),
            ValueError("private fixture prose"),
        ):
            with self.subTest(load_error=type(load_error).__name__):
                with (
                    mock.patch.object(cli, "load_scenario", side_effect=load_error),
                    mock.patch.object(
                        cli,
                        "_suite_manifest",
                        return_value=CLI_SUITE_MANIFEST,
                    ),
                    mock.patch.object(cli, "create_run_layout") as create,
                ):
                    error = io.StringIO()
                    result = cli.main(
                        [
                            "run",
                            "--suite-id",
                            "suite",
                            "--scenario",
                            "unknown",
                            "--model-file",
                            ".semantic-runs/contract/model.txt",
                        ],
                        output=io.StringIO(),
                        error=error,
                    )
                self.assertEqual(2, result)
                create.assert_not_called()
                self.assertNotIn("private", error.getvalue())

    def test_existing_run_refuses_before_layout_creation(self) -> None:
        from evaluation import cli

        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            existing = repository / ".semantic-runs" / "suite" / "synthetic"
            existing.mkdir(parents=True)
            process_calls = 0

            def forbidden_process(argv, **kwargs):
                nonlocal process_calls
                process_calls += 1
                raise AssertionError("existing run must refuse before subprocess")

            error = io.StringIO()
            with (
                mock.patch.object(cli, "REPOSITORY", repository),
                mock.patch.object(cli, "load_scenario", return_value=scenario()),
                mock.patch.object(cli, "_suite_manifest", return_value=CLI_SUITE_MANIFEST),
                mock.patch.object(
                    cli,
                    "identities_for_scenario",
                    return_value=fixture_identities(),
                ),
                mock.patch.object(cli, "create_run_layout") as create,
            ):
                result = cli.main(
                    [
                        "run",
                        "--suite-id",
                        "suite",
                        "--scenario",
                        "synthetic",
                        "--model-file",
                        ".semantic-runs/contract/model.txt",
                    ],
                    output=io.StringIO(),
                    error=error,
                    run_process=forbidden_process,
                )

        self.assertEqual(2, result)
        self.assertEqual(0, process_calls)
        create.assert_not_called()
        self.assertEqual(
            "BLOCKED: Semantic evaluation precheck refused.\n",
            error.getvalue(),
        )

    def test_invoke_has_bounded_timeout_and_classifies_timeout(self) -> None:
        from evaluation import cli

        observed: dict[str, object] = {}

        def time_out(argv, **kwargs):
            observed.update(kwargs)
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

        with self.assertRaisesRegex(
            cli.CliRefusal,
            "^Required preflight command timed out[.]$",
        ):
            cli._invoke(time_out, ("agy", "models"), Path.cwd())

        self.assertEqual(cli.PREFLIGHT_TIMEOUT_SECONDS, observed["timeout"])

    def test_verify_command_uses_fixed_isolation_failure_message(self) -> None:
        from evaluation import cli

        error = io.StringIO()
        with mock.patch.object(
            cli,
            "verify_run_isolation",
            side_effect=ValueError("C:\\Users\\private runtime path"),
        ):
            result = cli.main(
                [
                    "verify-isolation",
                    "--suite-id",
                    "suite",
                    "--scenario",
                    "synthetic",
                ],
                output=io.StringIO(),
                error=error,
            )

        self.assertEqual(2, result)
        self.assertEqual(
            "BLOCKED: Post-run isolation verification failed.\n",
            error.getvalue(),
        )
        self.assertNotIn("Users", error.getvalue())

    def test_run_uses_fixed_post_run_isolation_failure_message(self) -> None:
        from evaluation import cli

        preflight = type(
            "Preflight",
            (),
            {
                "model": "validated-model",
                "runtime_version": "1.5.2",
                "contract": object(),
                "identity": identity(),
            },
        )()
        fake_layout = type(
            "Layout",
            (),
            {"run_dir": Path(".semantic-runs/suite/synthetic")},
        )()
        error = io.StringIO()
        with (
            mock.patch.object(cli, "_preflight", return_value=preflight),
            mock.patch.object(cli, "load_scenario", return_value=scenario()),
            mock.patch.object(cli, "_suite_manifest", return_value=CLI_SUITE_MANIFEST),
            mock.patch.object(
                cli,
                "identities_for_scenario",
                return_value=fixture_identities(),
            ),
            mock.patch.object(cli, "create_run_layout", return_value=fake_layout),
            mock.patch.object(cli, "execute_isolated_run"),
            mock.patch.object(
                cli,
                "verify_run_isolation",
                side_effect=ValueError("private isolation path"),
            ),
        ):
            result = cli.main(
                [
                    "run",
                    "--suite-id",
                    "suite",
                    "--scenario",
                    "synthetic",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=error,
            )

        self.assertEqual(2, result)
        self.assertEqual(
            "BLOCKED: Post-run isolation verification failed.\n",
            error.getvalue(),
        )

    def test_run_refuses_scenario_outside_suite_before_mutation(self) -> None:
        from evaluation import cli

        process_calls = 0

        def forbidden_process(argv, **kwargs):
            nonlocal process_calls
            process_calls += 1
            raise AssertionError("out-of-suite run must refuse before subprocess")

        error = io.StringIO()
        with (
            mock.patch.object(cli, "load_scenario", return_value=scenario()),
            mock.patch.object(cli, "_preflight") as preflight,
            mock.patch.object(cli, "create_run_layout") as create,
            mock.patch.object(cli, "identities_for_scenario") as identities,
        ):
            result = cli.main(
                [
                    "run",
                    "--suite-id",
                    "baseline-v1",
                    "--scenario",
                    "synthetic",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=error,
                run_process=forbidden_process,
            )

        self.assertEqual(2, result)
        self.assertEqual(0, process_calls)
        preflight.assert_not_called()
        create.assert_not_called()
        identities.assert_not_called()
        self.assertEqual(
            "BLOCKED: Semantic evaluation precheck refused.\n",
            error.getvalue(),
        )

    def test_identifier_refuses_leading_digit_before_suite_lookup(self) -> None:
        from evaluation import cli

        error = io.StringIO()
        with mock.patch.object(cli, "load_scenario") as load_scenario:
            result = cli.main(
                [
                    "run",
                    "--suite-id",
                    "1illegal-suite",
                    "--scenario",
                    "synthetic",
                    "--model-file",
                    ".semantic-runs/contract/model.txt",
                ],
                output=io.StringIO(),
                error=error,
            )

        self.assertEqual(2, result)
        load_scenario.assert_not_called()
        self.assertEqual(
            "BLOCKED: Semantic evaluation precheck refused.\n",
            error.getvalue(),
        )

    def test_usage_errors_do_not_echo_unsafe_arguments(self) -> None:
        from evaluation import cli

        unsafe = "API_KEY=secret-C:\\Users\\private"
        error = io.StringIO()

        result = cli.main(
            ["run", "--suite-id", unsafe],
            output=io.StringIO(),
            error=error,
        )

        self.assertEqual(2, result)
        self.assertNotIn("secret", error.getvalue())
        self.assertNotIn("Users", error.getvalue())

    def test_verify_isolation_prints_only_fixed_message(self) -> None:
        from evaluation import cli

        output = io.StringIO()
        with mock.patch.object(cli, "verify_run_isolation") as verify:
            result = cli.main(
                [
                    "verify-isolation",
                    "--suite-id",
                    "suite",
                    "--scenario",
                    "synthetic",
                ],
                output=output,
                error=io.StringIO(),
            )

        self.assertEqual(0, result)
        verify.assert_called_once()
        self.assertEqual("Runtime isolation verified.\n", output.getvalue())
        self.assertNotIn(str(Path.cwd()), output.getvalue())

    def test_private_report_commands_refuse_missing_arguments_safely(self) -> None:
        from evaluation import cli

        for command in ("score", "report", "validate-report"):
            with self.subTest(command=command):
                error = io.StringIO()
                result = cli.main([command], output=io.StringIO(), error=error)
                self.assertEqual(2, result)
                self.assertEqual(cli.PRECHECK_REFUSAL_MESSAGE, error.getvalue())
                self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
