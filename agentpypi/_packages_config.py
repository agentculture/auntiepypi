"""Read ``[tool.agentpypi].packages`` from the nearest ``pyproject.toml``.

Walks up from a starting directory (default: CWD) until it finds a
``pyproject.toml`` containing the ``[tool.agentpypi]`` table, or until it
hits ``$HOME``. No global fallback — the user's home directory is the
ceiling.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


class ConfigError(Exception):
    """Raised when the configured package list is missing or malformed."""


def find_pyproject(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for the nearest ``pyproject.toml``.

    Stops at ``$HOME``. Returns the path to the first ``pyproject.toml``
    found, or ``None`` if nothing is found within the ceiling.
    """
    cwd = Path(start) if start is not None else Path.cwd()
    home = Path(os.environ.get("HOME", "/"))
    cur = cwd.resolve()
    while True:
        candidate = cur / "pyproject.toml"
        if candidate.exists():
            return candidate
        if cur == cur.parent or cur == home:
            return None
        cur = cur.parent


def load_package_names(start: Path | None = None) -> list[str]:
    """Return the configured list of package names.

    :raises ConfigError: when no ``pyproject.toml`` is found, the table is
        missing, the list is empty, or any entry is not a string.
    """
    found = find_pyproject(start)
    if found is None:
        raise ConfigError("no pyproject.toml found within the $HOME ceiling")
    with found.open("rb") as f:
        data = tomllib.load(f)
    table = data.get("tool", {}).get("agentpypi", {})
    if "packages" not in table:
        raise ConfigError("no [tool.agentpypi].packages key found in pyproject.toml")
    pkgs = table["packages"]
    if not isinstance(pkgs, list) or not pkgs:
        raise ConfigError("[tool.agentpypi].packages is empty or not a list")
    bad = [p for p in pkgs if not isinstance(p, str)]
    if bad:
        raise ConfigError(f"non-string entry in [tool.agentpypi].packages: {bad!r}")
    return list(pkgs)
