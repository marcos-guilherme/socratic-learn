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
        output.write(f"\x1b[32m{BANNER}\x1b[0m\n")
        return
    output.write(f"{BANNER}\n")
