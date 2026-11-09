from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from socratic_learn.errors import SourceError, UsageError
from socratic_learn.hosts import ADAPTERS, DetectedHost, command_for
from socratic_learn.launcher import LaunchOptions, run_learning
from socratic_learn.sources.model import BundleMetadata, IngestedSource, SourceRequest
from socratic_learn.sources.payload import build_source_study_payload


def _metadata() -> BundleMetadata:
    return BundleMetadata(
        schema_version=1,
        source_id="a" * 64,
        title="Article",
        display_origin="article.pdf",
        media_type="application/pdf",
        raw_sha256="b" * 64,
        extracted_at=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
        section_count=1,
        normalized_characters=200,
    )


def _ingested(bundle: Path) -> IngestedSource:
    return IngestedSource(
        bundle_path=bundle,
        source_id="a" * 64,
        metadata=_metadata(),
        reused=False,
    )


class ReadLauncherLifecycleTests(unittest.TestCase):
    def _run_read(
        self,
        *,
        agent: str = "pi",
        goal: str = "study evidence",
        home: str,
        which: dict[str, str] | None = None,
    ) -> tuple[list[str], list[list[str]]]:
        which = which or {"pi": "pi", "claude": "claude", "agy": "agy"}
        events: list[str] = []
        calls: list[list[str]] = []
        bundle = Path(home) / "records/sources/abc"

        def detect(which_fn):
            events.append("detect")
            detected: dict[str, DetectedHost] = {}
            for name in ("pi", "claude", "antigravity"):
                executable_name = ADAPTERS[name].executable_names[0]
                executable = which_fn(executable_name)
                if executable is not None:
                    detected[name] = DetectedHost(ADAPTERS[name], executable)
            return detected

        def workspace(*_args, **_kwargs):
            events.append("workspace")
            from socratic_learn.workspace import LearningWorkspace

            records = Path(home) / "records"
            records.mkdir(parents=True, exist_ok=True)
            protocol = Path(home) / "protocol.md"
            protocol.write_text("protocol\n", encoding="utf-8")
            return LearningWorkspace(Path(home), protocol, records)

        def ingest(records, request):
            events.append("ingest")
            bundle.mkdir(parents=True, exist_ok=True)
            (bundle / "index.md").write_text("# Index\n", encoding="utf-8")
            (bundle / "metadata.json").write_text("{}", encoding="utf-8")
            return _ingested(bundle.resolve())

        def spawn(argv, **kwargs):
            events.append("spawn")
            calls.append(argv)
            return CompletedProcess(argv, 0)

        with (
            mock.patch("socratic_learn.launcher.detect_hosts", side_effect=detect),
            mock.patch(
                "socratic_learn.launcher.prepare_personal_workspace",
                side_effect=workspace,
            ),
            mock.patch("socratic_learn.launcher.ingest_source", side_effect=ingest),
        ):
            options = LaunchOptions(
                goal,
                agent,  # type: ignore[arg-type]
                False,
                Path.cwd(),
                SourceRequest("article.pdf", "local_pdf"),
            )
            run_learning(
                options,
                input_fn=lambda prompt: self.fail("must not prompt"),
                output=io.StringIO(),
                which=which.get,
                run_process=spawn,
                environ={"SOCRATIC_LEARN_HOME": home},
            )
        events.insert(1, "goal")
        events.insert(2, "agent")
        return events, calls

    def test_lifecycle_order_is_detect_goal_agent_workspace_ingest_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            events, _calls = self._run_read(home=temporary)
            self.assertEqual(
                ["detect", "goal", "agent", "workspace", "ingest", "spawn"],
                events,
            )

    def test_missing_host_skips_prompt_workspace_and_ingest(self) -> None:
        prompts: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(UsageError, "compatible agent"):
                run_learning(
                    LaunchOptions(
                        "goal",
                        None,
                        False,
                        Path.cwd(),
                        SourceRequest("article.pdf", "local_pdf"),
                    ),
                    input_fn=lambda prompt: prompts.append(prompt) or "goal",
                    output=io.StringIO(),
                    which=lambda name: None,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )
        self.assertEqual([], prompts)

    def test_blank_goal_skips_ingest(self) -> None:
        ingested = mock.Mock()
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch("socratic_learn.launcher.ingest_source", ingested):
                with self.assertRaisesRegex(UsageError, "goal"):
                    run_learning(
                        LaunchOptions(
                            None,
                            "pi",
                            False,
                            Path.cwd(),
                            SourceRequest("article.pdf", "local_pdf"),
                        ),
                        input_fn=lambda prompt: "  ",
                        output=io.StringIO(),
                        which={"pi": "pi"}.get,
                        run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
                        environ={"SOCRATIC_LEARN_HOME": temporary},
                    )
        ingested.assert_not_called()

    def test_undetected_explicit_agent_skips_ingest(self) -> None:
        ingested = mock.Mock()

        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch("socratic_learn.launcher.ingest_source", ingested),
                self.assertRaisesRegex(UsageError, "claude"),
            ):
                run_learning(
                    LaunchOptions(
                        "goal",
                        "claude",
                        False,
                        Path.cwd(),
                        SourceRequest("article.pdf", "local_pdf"),
                    ),
                    output=io.StringIO(),
                    which={"pi": "pi"}.get,
                    environ={"SOCRATIC_LEARN_HOME": temporary},
                )
        ingested.assert_not_called()

    def test_source_specific_goal_prompt(self) -> None:
        prompts: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch(
                "socratic_learn.launcher.ingest_source",
                return_value=_ingested(Path(temporary) / "bundle"),
            ):
                with mock.patch(
                    "socratic_learn.launcher.prepare_personal_workspace",
                ) as workspace:
                    from socratic_learn.workspace import LearningWorkspace

                    records = Path(temporary) / "records"
                    records.mkdir()
                    protocol = Path(temporary) / "protocol.md"
                    protocol.write_text("x", encoding="utf-8")
                    workspace.return_value = LearningWorkspace(
                        Path(temporary),
                        protocol,
                        records,
                    )
                    run_learning(
                        LaunchOptions(
                            None,
                            "pi",
                            False,
                            Path.cwd(),
                            SourceRequest("article.pdf", "local_pdf"),
                        ),
                        input_fn=lambda prompt: prompts.append(prompt) or "goal",
                        output=io.StringIO(),
                        which={"pi": "pi"}.get,
                        run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
                        environ={"SOCRATIC_LEARN_HOME": temporary},
                    )
        self.assertEqual(
            ["What do you want to be able to do with this source?"],
            prompts,
        )

    def test_ingest_receives_workspace_records(self) -> None:
        records_seen: list[Path] = []
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch(
                "socratic_learn.launcher.ingest_source",
                side_effect=lambda records, request: (
                    records_seen.append(records) or _ingested(records / "sources/x")
                ),
            ):
                with mock.patch(
                    "socratic_learn.launcher.prepare_personal_workspace",
                ) as workspace:
                    from socratic_learn.workspace import LearningWorkspace

                    records = Path(temporary) / "records"
                    records.mkdir()
                    protocol = Path(temporary) / "protocol.md"
                    protocol.write_text("x", encoding="utf-8")
                    workspace.return_value = LearningWorkspace(
                        Path(temporary),
                        protocol,
                        records,
                    )
                    run_learning(
                        LaunchOptions(
                            "goal",
                            "pi",
                            False,
                            Path.cwd(),
                            SourceRequest("article.pdf", "local_pdf"),
                        ),
                        output=io.StringIO(),
                        which={"pi": "pi"}.get,
                        run_process=lambda argv, **kwargs: CompletedProcess(argv, 0),
                        environ={"SOCRATIC_LEARN_HOME": temporary},
                    )
        self.assertEqual([records.resolve()], records_seen)

    def test_ingestion_failure_prevents_spawn(self) -> None:
        spawned = False

        def ingest(*_args, **_kwargs):
            raise SourceError("ingestion failed")

        def spawn(*_args, **_kwargs):
            nonlocal spawned
            spawned = True
            return CompletedProcess([], 0)

        with tempfile.TemporaryDirectory() as temporary:
            with (
                mock.patch("socratic_learn.launcher.ingest_source", side_effect=ingest),
                mock.patch(
                    "socratic_learn.launcher.prepare_personal_workspace",
                ) as workspace,
            ):
                from socratic_learn.workspace import LearningWorkspace

                records = Path(temporary) / "records"
                records.mkdir()
                protocol = Path(temporary) / "protocol.md"
                protocol.write_text("x", encoding="utf-8")
                workspace.return_value = LearningWorkspace(
                    Path(temporary),
                    protocol,
                    records,
                )
                with self.assertRaises(SourceError):
                    run_learning(
                        LaunchOptions(
                            "goal",
                            "pi",
                            False,
                            Path.cwd(),
                            SourceRequest("article.pdf", "local_pdf"),
                        ),
                        output=io.StringIO(),
                        which={"pi": "pi"}.get,
                        run_process=spawn,
                        environ={"SOCRATIC_LEARN_HOME": temporary},
                    )
        self.assertFalse(spawned)

    def test_normal_session_argv_matches_baseline_without_payload(self) -> None:
        captured: list[tuple[str, ...]] = []
        with tempfile.TemporaryDirectory() as temporary:
            run_learning(
                LaunchOptions("logic", "pi", False, Path.cwd()),
                output=io.StringIO(),
                which={"pi": "pi"}.get,
                run_process=lambda argv, **kwargs: (
                    captured.append(tuple(argv)) or CompletedProcess(argv, 0)
                ),
                environ={"SOCRATIC_LEARN_HOME": temporary},
            )
        self.assertEqual(
            ("pi", "--append-system-prompt", mock.ANY, "logic"),
            captured[0],
        )

    def test_read_flow_uses_absolute_paths_in_payload_for_each_host(self) -> None:
        for agent, executable in (
            ("pi", "pi"),
            ("claude", "claude"),
            ("antigravity", "agy"),
        ):
            with self.subTest(agent=agent):
                captured: list[tuple[str, ...]] = []
                with tempfile.TemporaryDirectory() as temporary:
                    bundle = Path(temporary) / "records/sources/x"
                    workspace_protocol = Path(temporary) / "protocol.md"
                    with mock.patch(
                        "socratic_learn.launcher.ingest_source",
                        return_value=_ingested(bundle),
                    ):
                        with mock.patch(
                            "socratic_learn.launcher.prepare_personal_workspace",
                        ) as workspace:
                            from socratic_learn.workspace import LearningWorkspace

                            records = Path(temporary) / "records"
                            records.mkdir(parents=True)
                            workspace_protocol.write_text("x", encoding="utf-8")
                            workspace.return_value = LearningWorkspace(
                                Path(temporary),
                                workspace_protocol,
                                records,
                            )
                            run_learning(
                                LaunchOptions(
                                    "study",
                                    agent,  # type: ignore[arg-type]
                                    False,
                                    Path.cwd(),
                                    SourceRequest("article.pdf", "local_pdf"),
                                ),
                                output=io.StringIO(),
                                which={executable: executable}.get,
                                run_process=lambda argv, **kwargs: (
                                    captured.append(tuple(argv))
                                    or CompletedProcess(argv, 0)
                                ),
                                environ={"SOCRATIC_LEARN_HOME": temporary},
                            )
                index_path = bundle.resolve() / "index.md"
                metadata_path = bundle.resolve() / "metadata.json"
                payload = build_source_study_payload(
                    learner_goal="study",
                    index_path=index_path,
                    metadata_path=metadata_path,
                )
                expected = command_for(
                    ADAPTERS[agent],
                    executable,
                    workspace_protocol,
                    "study",
                    source_study_payload=payload,
                )
                self.assertEqual(expected, captured[0])
                self.assertIn(str(index_path), payload)
                self.assertIn(str(metadata_path), payload)


if __name__ == "__main__":
    unittest.main()
