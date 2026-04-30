"""AfiError and exit-code policy (stable-contract — copy verbatim).

Re-exports the canonical definitions from :mod:`auntiepypi._errors` so
that callers can use either import path. The actual definitions live at
the package level to avoid circular imports between ``_actions`` and
``cli`` subpackages.
"""

from __future__ import annotations

# Re-export everything from the package-level module so all existing
# `from auntiepypi.cli._errors import …` statements keep working.
from auntiepypi._errors import (  # noqa: F401
    EXIT_ENV_ERROR,
    EXIT_SUCCESS,
    EXIT_USER_ERROR,
    AfiError,
)

__all__ = ["EXIT_ENV_ERROR", "EXIT_SUCCESS", "EXIT_USER_ERROR", "AfiError"]
