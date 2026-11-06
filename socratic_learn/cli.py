from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import __version__
from .__main__ import main as administrative_main
from .errors import LearningTutorError, UsageError
from .launcher import LaunchOptions, run_learning

_ADMIN_COMMANDS = {"build", "export", "install", "doctor"}
_SELF_COMMANDS = {"update", "uninstall"}


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(
            message,
            remediation=f"run '{self.prog} --help'",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="socratic",
        allow_abbrev=False,
        description="Start a Socratic learning session.",
        epilog=(
            "Administrative commands:\n"
            "  build\n"
            "  export\n"
            "  install\n"
            "  doctor\n"
            "\n"
            "Examples:\n"
            "  socratic linear algebra\n"
            "  socratic --agent pi --here linear algebra\n"
            "  socratic learn doctor"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--agent",
        choices=("pi", "claude", "antigravity"),
        help="select a compatible installed agent",
    )
    parser.add_argument(
        "--here",
        action="store_true",
        help="prepare learning files in the current directory",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"socratic-learn {__version__}",
    )
    parser.add_argument(
        "goal",
        nargs="*",
        help="learning goal words, optionally preceded by 'learn'",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in _ADMIN_COMMANDS:
        return administrative_main(arguments)

    try:
        if arguments and arguments[0] in _SELF_COMMANDS:
            command = arguments[0]
            raise UsageError(
                f"'{command}' is reserved for a future release",
                remediation=f"use 'socratic learn {command}' to learn about it",
            )

        parsed = _build_parser().parse_intermixed_args(arguments)
        goal_words = parsed.goal
        if goal_words and goal_words[0] == "learn":
            goal_words = goal_words[1:]
        goal = " ".join(goal_words) if goal_words else None
        return run_learning(
            LaunchOptions(goal, parsed.agent, parsed.here, Path.cwd())
        )
    except LearningTutorError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code


def entry_point() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    entry_point()
