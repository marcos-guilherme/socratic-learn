"""Deprecated module entry point for Socratic Learn."""

from __future__ import annotations

import sys

from socratic_learn.__main__ import main


if __name__ == "__main__":
    sys.stderr.write(
        "warning: 'python -m learning_tutor' is deprecated; "
        "use 'python -m socratic_learn'\n"
    )
    raise SystemExit(main())
