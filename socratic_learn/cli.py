from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from socratic_learn import __version__
from socratic_learn.__main__ import main as administrative_main
from socratic_learn.banner import write_banner
from socratic_learn.errors import LearningTutorError, SourceError, UsageError
from socratic_learn.launcher import LaunchOptions, run_learning
from socratic_learn.self_manage import uninstall, update_installation
from socratic_learn.sources.model import SourceRequest
from socratic_learn.workspace import launcher_home

_ADMIN_COMMANDS = {"build", "export", "install", "doctor"}
_SELF_COMMANDS = {"update", "uninstall"}
_AGENT_NAMES = frozenset({"pi", "claude", "antigravity"})


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(
            message,
            remediation=f"run '{self.prog} --help'",
        )


def parse_source_origin(
    origin: str,
    *,
    allow_private_network: bool = False,
) -> SourceRequest:
    lowered = origin.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return SourceRequest(origin, "url", allow_private_network=allow_private_network)
    if "://" in origin:
        scheme = origin.split("://", 1)[0].lower()
        raise SourceError(
            f"unsupported URL scheme '{scheme}'",
            remediation="use an http:// or https:// URL, or a local file path",
        )
    return SourceRequest(origin, "local_pdf", allow_private_network=allow_private_network)


def _first_non_option_command_token(arguments: list[str]) -> str | None:
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            index += 1
            break
        if argument == "--agent":
            index += 2
            continue
        if argument.startswith("--agent="):
            index += 1
            continue
        if argument in ("--here", "--allow-private-network"):
            index += 1
            continue
        if argument.startswith("-"):
            return None
        return argument
    return None


def _read_mode_requested(arguments: list[str]) -> bool:
    return _first_non_option_command_token(arguments) == "read"


def _reject_disallowed_options(arguments: list[str]) -> None:
    for argument in arguments:
        if argument == "--allow-private-network":
            raise UsageError(
                "unrecognized arguments: --allow-private-network",
                remediation="use '--allow-private-network' only with 'socratic read'",
            )


def parse_read_arguments(
    arguments: list[str],
    *,
    cwd: Path | None = None,
) -> LaunchOptions:
    working_directory = Path.cwd() if cwd is None else cwd
    agent: str | None = None
    here = False
    allow_private_network = False
    positionals: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "--":
            positionals.extend(arguments[index + 1 :])
            break
        if argument == "--agent":
            if index + 1 >= len(arguments):
                raise UsageError(
                    "argument --agent: expected one argument",
                    remediation="run 'socratic read --help'",
                )
            agent = arguments[index + 1]
            index += 2
            continue
        if argument.startswith("--agent="):
            agent = argument.partition("=")[2]
            index += 1
            continue
        if argument == "--here":
            here = True
            index += 1
            continue
        if argument == "--allow-private-network":
            allow_private_network = True
            index += 1
            continue
        if argument.startswith("-"):
            raise UsageError(
                f"unrecognized arguments: {argument}",
                remediation="run 'socratic --help'",
            )
        positionals.append(argument)
        index += 1

    if not positionals or positionals[0] != "read":
        raise UsageError(
            "read command was not found",
            remediation="use 'socratic read SOURCE [GOAL...]'",
        )

    remaining = positionals[1:]
    if not remaining:
        raise UsageError(
            "read requires a source",
            remediation="provide a URL or local PDF path after 'read'",
        )
    if agent is not None and agent not in _AGENT_NAMES:
        raise UsageError(
            f"invalid agent '{agent}'",
            remediation="choose one of: pi, claude, antigravity",
        )

    source_token = remaining[0]
    goal_words = remaining[1:]
    goal = " ".join(goal_words) if goal_words else None
    source = parse_source_origin(
        source_token,
        allow_private_network=allow_private_network,
    )
    return LaunchOptions(
        goal,
        agent,  # type: ignore[arg-type]
        here,
        working_directory,
        source,
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
            "Self-management commands:\n"
            "  update\n"
            "  uninstall [--delete-data [--yes]]\n"
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


def _run_self_command(arguments: list[str]) -> int:
    command = arguments[0]
    parser = _ArgumentParser(prog=f"socratic {command}", allow_abbrev=False)
    if command == "update":
        parser.parse_args(arguments[1:])
        return update_installation(launcher_home(), Path(sys.executable))

    parser.add_argument(
        "--delete-data",
        action="store_true",
        help="also delete learner profiles, progress, and sessions",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm deletion non-interactively (requires --delete-data)",
    )
    parsed = parser.parse_args(arguments[1:])
    if parsed.yes and not parsed.delete_data:
        raise UsageError(
            "--yes requires --delete-data",
            remediation="use 'socratic uninstall --delete-data --yes'",
        )
    return uninstall(
        launcher_home(),
        executable=Path(sys.executable),
        delete_data=parsed.delete_data,
        confirm=input,
        yes=parsed.yes,
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in _ADMIN_COMMANDS:
        return administrative_main(arguments)

    try:
        if arguments and arguments[0] in _SELF_COMMANDS:
            return _run_self_command(arguments)

        if _read_mode_requested(arguments):
            options = parse_read_arguments(arguments)
            write_banner(sys.stdout, os.environ)
            return run_learning(options)

        _reject_disallowed_options(arguments)

        parsed = _build_parser().parse_intermixed_args(arguments)
        goal_words = parsed.goal
        if goal_words and goal_words[0] == "learn":
            goal_words = goal_words[1:]
        goal = " ".join(goal_words) if goal_words else None
        write_banner(sys.stdout, os.environ)
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
