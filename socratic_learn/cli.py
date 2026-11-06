from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn

from .__main__ import main as administrative_main


def main(argv: Sequence[str] | None = None) -> int:
    return administrative_main(argv)


def entry_point() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    entry_point()
