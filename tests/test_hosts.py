from __future__ import annotations

import unittest
from pathlib import Path

from socratic_learn.hosts import ADAPTERS, command_for, detect_hosts


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
