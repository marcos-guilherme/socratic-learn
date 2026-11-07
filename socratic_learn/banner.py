from __future__ import annotations

from collections.abc import Mapping
from typing import TextIO

BANNER = """  ███████╗ ██████╗  ██████╗██████╗  █████╗ ████████╗██╗ ██████╗
  ██╔════╝██╔═══██╗██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██║██╔════╝
  ███████╗██║   ██║██║     ██████╔╝███████║   ██║   ██║██║
  ╚════██║██║   ██║██║     ██╔══██╗██╔══██║   ██║   ██║██║
  ███████║╚██████╔╝╚██████╗██║  ██║██║  ██║   ██║   ██║╚██████╗
  ╚══════╝ ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚═╝ ╚═════╝
                              L E A R N

  objective → prerequisites → guided route → application → evidence"""


def write_banner(output: TextIO, environ: Mapping[str, str]) -> None:
    if (
        output.isatty()
        and "NO_COLOR" not in environ
        and environ.get("TERM") != "dumb"
    ):
        text = f"\x1b[32m{BANNER}\x1b[0m\n"
    else:
        text = f"{BANNER}\n"

    try:
        output.write(text)
    except UnicodeEncodeError:
        binary_output = getattr(output, "buffer", None)
        if binary_output is None:
            raise
        output.flush()
        binary_output.write(text.encode("utf-8"))
    output.flush()
