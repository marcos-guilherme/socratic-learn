from __future__ import annotations

import io
import unittest
from pathlib import Path

from socratic_learn.banner import BANNER, write_banner


class _TerminalStream(io.StringIO):
    def __init__(self, interactive: bool) -> None:
        super().__init__()
        self._interactive = interactive

    def isatty(self) -> bool:
        return self._interactive


class BannerTests(unittest.TestCase):
    def test_banner_matches_first_readme_text_block(self) -> None:
        readme = Path(__file__).resolve().parents[1] / "README.md"
        fenced_block = readme.read_text(encoding="utf-8").split(
            "```text\n", 1
        )[1].split("\n```", 1)[0]

        self.assertEqual(fenced_block, BANNER)

    def test_interactive_stream_gets_green_banner(self) -> None:
        output = _TerminalStream(interactive=True)

        write_banner(output, {})

        self.assertEqual(f"\x1b[32m{BANNER}\x1b[0m\n", output.getvalue())

    def test_no_color_gives_plain_banner(self) -> None:
        output = _TerminalStream(interactive=True)

        write_banner(output, {"NO_COLOR": ""})

        self.assertEqual(f"{BANNER}\n", output.getvalue())

    def test_dumb_terminal_gives_plain_banner(self) -> None:
        output = _TerminalStream(interactive=True)

        write_banner(output, {"TERM": "dumb"})

        self.assertEqual(f"{BANNER}\n", output.getvalue())

    def test_non_interactive_stream_gives_plain_banner(self) -> None:
        output = _TerminalStream(interactive=False)

        write_banner(output, {})

        self.assertEqual(f"{BANNER}\n", output.getvalue())


if __name__ == "__main__":
    unittest.main()
