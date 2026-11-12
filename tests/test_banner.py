from __future__ import annotations

import io
import os
import unittest

from socratic_learn.banner import ASCII_BANNER, BANNER, write_banner


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
    def test_banner_keeps_product_identity_and_learning_flow(self) -> None:
        self.assertIn("L E A R N", BANNER)
        self.assertIn(
            "objective → prerequisites → guided route → application → evidence",
            BANNER,
        )

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

    def test_cp1252_stream_writes_readable_ascii_fallback(self) -> None:
        binary_output = io.BytesIO()
        output = io.TextIOWrapper(binary_output, encoding="cp1252")

        write_banner(output, {})

        self.assertEqual(
            f"{ASCII_BANNER}\n".replace("\n", os.linesep).encode("cp1252"),
            binary_output.getvalue(),
        )

    def test_cp1252_binary_fallback_is_flushed(self) -> None:
        binary_output = io.BytesIO()
        output = _TrackingTextWrapper(binary_output, encoding="cp1252")

        write_banner(output, {})

        self.assertEqual(1, output.flush_calls)
        self.assertEqual(
            f"{ASCII_BANNER}\n".replace("\n", os.linesep).encode("cp1252"),
            binary_output.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
