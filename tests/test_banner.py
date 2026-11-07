from __future__ import annotations

import io
import unittest
from pathlib import Path

from socratic_learn.banner import BANNER, write_banner


class _TerminalStream(io.StringIO):
    def __init__(self, interactive: bool) -> None:
        super().__init__()
        self._interactive = interactive
        self.flush_calls = 0

    def isatty(self) -> bool:
        return self._interactive

    def flush(self) -> None:
        self.flush_calls += 1
        super().flush()


class _TrackingTextWrapper(io.TextIOWrapper):
    def __init__(self, buffer: io.BytesIO, encoding: str) -> None:
        super().__init__(buffer, encoding=encoding)
        self.flush_calls = 0

    def flush(self) -> None:
        self.flush_calls += 1
        super().flush()


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

    def test_normal_text_output_is_flushed(self) -> None:
        output = _TerminalStream(interactive=False)

        write_banner(output, {})

        self.assertEqual(1, output.flush_calls)

    def test_cp1252_stream_writes_complete_utf8_banner(self) -> None:
        binary_output = io.BytesIO()
        output = io.TextIOWrapper(binary_output, encoding="cp1252")

        try:
            write_banner(output, {})
        except UnicodeEncodeError as error:
            self.fail(f"banner aborted on a CP1252 stream: {error}")

        self.assertEqual(f"{BANNER}\n".encode("utf-8"), binary_output.getvalue())

    def test_cp1252_binary_fallback_is_flushed(self) -> None:
        binary_output = io.BytesIO()
        output = _TrackingTextWrapper(binary_output, encoding="cp1252")

        write_banner(output, {})

        self.assertEqual(2, output.flush_calls)


if __name__ == "__main__":
    unittest.main()
