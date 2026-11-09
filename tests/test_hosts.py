from __future__ import annotations

import unittest
from pathlib import Path

from socratic_learn.hosts import ADAPTERS, command_for, detect_hosts
from socratic_learn.sources.payload import build_source_study_payload


class HostAdapterTests(unittest.TestCase):
    def test_public_adapter_registry_cannot_be_mutated(self) -> None:
        with self.assertRaises(TypeError):
            ADAPTERS["pi"] = ADAPTERS["claude"]  # type: ignore[index]

    def test_detection_uses_supported_executable_names(self) -> None:
        found = {
            "pi": "C:/bin/pi.exe",
            "claude": "C:/bin/claude.exe",
            "agy": "C:/bin/agy.exe",
        }
        detected = detect_hosts(found.get)
        self.assertEqual(["pi", "claude", "antigravity"], list(detected))

    def test_commands_are_argument_arrays_with_protocol_and_goal(self) -> None:
        protocol = Path("C:/Learning Home/protocol.md")
        goal = "learn cafés and probability"
        for name, executable in (
            ("pi", "pi"),
            ("claude", "claude"),
            ("antigravity", "agy"),
        ):
            with self.subTest(name=name):
                argv = command_for(ADAPTERS[name], executable, protocol, goal)
                self.assertEqual(executable, argv[0])
                self.assertTrue(any(str(protocol) in value for value in argv[1:]))
                self.assertTrue(any(goal in value for value in argv[1:]))

    def test_commands_match_each_host_contract(self) -> None:
        protocol = Path("C:/Learning Home/protocol.md")
        goal = "learn probability"
        self.assertEqual(
            ("pi", "--append-system-prompt", str(protocol), goal),
            command_for(ADAPTERS["pi"], "pi", protocol, goal),
        )
        self.assertEqual(
            ("claude", "--append-system-prompt-file", str(protocol), goal),
            command_for(ADAPTERS["claude"], "claude", protocol, goal),
        )
        self.assertEqual(
            (
                "agy",
                "--prompt-interactive",
                "Before responding, read and follow the Socratic Learn protocol at "
                f"{protocol}. The learner's initial objective is: {goal}",
            ),
            command_for(ADAPTERS["antigravity"], "agy", protocol, goal),
        )
        antigravity = command_for(
            ADAPTERS["antigravity"], "agy", protocol, goal
        )
        self.assertEqual(3, len(antigravity))
        self.assertNotIn(goal, antigravity)
        self.assertIn(goal, antigravity[2])

    def test_detection_uses_first_resolved_executable_per_adapter(self) -> None:
        looked_up: list[str] = []

        def which(name: str) -> str | None:
            looked_up.append(name)
            return {
                "pi": "C:/bin/pi.exe",
                "claude": "C:/bin/claude.exe",
                "agy": "C:/bin/agy.exe",
            }.get(name)

        detected = detect_hosts(which)

        self.assertEqual(["pi", "claude", "agy"], looked_up)
        self.assertEqual("C:/bin/agy.exe", detected["antigravity"].executable)
        self.assertIs(ADAPTERS["antigravity"], detected["antigravity"].adapter)

    def test_none_payload_preserves_normal_argv_byte_for_byte(self) -> None:
        protocol = Path("C:/Learning Home/protocol.md")
        goal = "learn probability"
        baseline_pi = command_for(ADAPTERS["pi"], "pi", protocol, goal)
        baseline_claude = command_for(
            ADAPTERS["claude"], "claude", protocol, goal
        )
        baseline_agy = command_for(ADAPTERS["antigravity"], "agy", protocol, goal)
        self.assertEqual(
            baseline_pi,
            command_for(
                ADAPTERS["pi"],
                "pi",
                protocol,
                goal,
                source_study_payload=None,
            ),
        )
        self.assertEqual(
            baseline_claude,
            command_for(
                ADAPTERS["claude"],
                "claude",
                protocol,
                goal,
                source_study_payload=None,
            ),
        )
        self.assertEqual(
            baseline_agy,
            command_for(
                ADAPTERS["antigravity"],
                "agy",
                protocol,
                goal,
                source_study_payload=None,
            ),
        )

    def test_read_mode_envelopes_use_exact_payload_and_delimiter(self) -> None:
        protocol = Path("C:/Learning Home/protocol.md")
        goal = "read critically"
        index = Path("C:/home/.socratic-learn/sources/x/index.md")
        metadata = Path("C:/home/.socratic-learn/sources/x/metadata.json")
        payload = build_source_study_payload(
            learner_goal=goal,
            index_path=index,
            metadata_path=metadata,
        )
        self.assertEqual(
            ("pi", "--append-system-prompt", str(protocol), payload),
            command_for(
                ADAPTERS["pi"],
                "pi",
                protocol,
                goal,
                source_study_payload=payload,
            ),
        )
        self.assertEqual(
            ("claude", "--append-system-prompt-file", str(protocol), payload),
            command_for(
                ADAPTERS["claude"],
                "claude",
                protocol,
                goal,
                source_study_payload=payload,
            ),
        )
        read_prefix = (
            "Before responding, read and follow the Socratic Learn protocol at "
            f"{protocol}."
        )
        delimiter = "\n\n--- SOCRATIC LEARN SOURCE STUDY ---\n"
        read_bootstrap = f"{read_prefix}{delimiter}{payload}"
        agy_argv = command_for(
            ADAPTERS["antigravity"],
            "agy",
            protocol,
            goal,
            source_study_payload=payload,
        )
        self.assertEqual(
            ("agy", "--prompt-interactive", read_bootstrap),
            agy_argv,
        )
        self.assertEqual(1, agy_argv[2].count(delimiter))
        self.assertEqual(1, agy_argv[2].count(payload))
        self.assertNotIn(
            f"The learner's initial objective is: {goal}",
            agy_argv[2],
        )
