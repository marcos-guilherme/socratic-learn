"""Command-line interface for the universal learning tutor package."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import TARGETS
from .errors import FilesystemError, IntegrityError, LearningTutorError, UsageError


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(
            message,
            remediation=f"run '{self.prog} --help'",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="learning-tutor", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("build", allow_abbrev=False)

    export_parser = commands.add_parser("export", allow_abbrev=False)
    export_formats = export_parser.add_subparsers(
        dest="export_format",
        required=True,
    )
    prompt_parser = export_formats.add_parser("prompt", allow_abbrev=False)
    prompt_parser.add_argument("--output", type=Path)

    install_parser = commands.add_parser("install", allow_abbrev=False)
    install_parser.add_argument("target", choices=TARGETS)
    install_parser.add_argument("project", type=Path)
    install_parser.add_argument("--update", action="store_true")

    doctor_parser = commands.add_parser("doctor", allow_abbrev=False)
    doctor_parser.add_argument("project", type=Path)

    return parser


def _dispatch_build() -> int:
    try:
        from .build import build
    except ModuleNotFoundError as error:
        if error.name != "learning_tutor.build":
            raise
        raise _unavailable("build") from error
    build()
    return 0


def _dispatch_export_prompt(output: Path | None) -> int:
    try:
        from .export import export_prompt
    except ModuleNotFoundError as error:
        if error.name != "learning_tutor.export":
            raise
        raise _unavailable("export prompt") from error
    export_prompt(output)
    return 0


def _dispatch_install(target: str, project: Path, *, update: bool) -> int:
    try:
        from .install import install
    except ModuleNotFoundError as error:
        if error.name != "learning_tutor.install":
            raise
        raise _unavailable("install") from error
    install(target, project, update=update)
    return 0


def _dispatch_doctor(project: Path) -> int:
    try:
        from .doctor import diagnose, format_diagnostics
    except ModuleNotFoundError as error:
        if error.name != "learning_tutor.doctor":
            raise
        raise _unavailable("doctor") from error
    diagnostics = diagnose(project)
    output = (
        format_diagnostics(diagnostics)
        if diagnostics
        else "Installation healthy.\n"
    )
    try:
        sys.stdout.write(output)
        sys.stdout.flush()
    except OSError as error:
        raise FilesystemError(
            "doctor output could not be written",
            path="<stdout>",
            remediation="check standard output and retry",
        ) from error
    return IntegrityError.exit_code if diagnostics else 0


def _unavailable(command: str) -> IntegrityError:
    return IntegrityError(
        f"{command} implementation is unavailable",
        remediation="install a complete learning-tutor package",
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _build_parser().parse_args(argv)
        if arguments.command == "build":
            return _dispatch_build()
        if arguments.command == "export":
            return _dispatch_export_prompt(arguments.output)
        if arguments.command == "install":
            return _dispatch_install(
                arguments.target,
                arguments.project,
                update=arguments.update,
            )
        return _dispatch_doctor(arguments.project)
    except LearningTutorError as error:
        print(f"error: {error}", file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
