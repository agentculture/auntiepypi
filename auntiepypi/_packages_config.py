"""Read ``[tool.auntiepypi].packages`` from the nearest ``pyproject.toml``.

Walks up from a starting directory (default: CWD) until it finds a
``pyproject.toml`` containing the ``[tool.auntiepypi]`` table, or until it
hits ``$HOME``. No global fallback — the user's home directory is the
ceiling.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path


class ConfigError(Exception):
    """Raised when the configured package list is missing or malformed."""


def _has_auntiepypi_table(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return isinstance(data.get("tool", {}).get("auntiepypi"), dict)


def find_pyproject(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for a ``pyproject.toml`` with ``[tool.auntiepypi]``.

    Stops at ``$HOME``. Returns the first pyproject.toml whose ``[tool.auntiepypi]``
    table is present; otherwise the first pyproject.toml encountered (so the loader
    can produce a precise error about the missing key); otherwise ``None``.
    """
    cwd = Path(start) if start is not None else Path.cwd()
    home = Path(os.environ.get("HOME", "/")).resolve()
    cur = cwd.resolve()
    first_match: Path | None = None
    while True:
        candidate = cur / "pyproject.toml"
        if candidate.exists():
            if _has_auntiepypi_table(candidate):
                return candidate
            if first_match is None:
                first_match = candidate
        if cur == cur.parent or cur == home:
            return first_match
        cur = cur.parent


def load_package_names(start: Path | None = None) -> list[str]:
    """Return the configured list of package names.

    :raises ConfigError: when no ``pyproject.toml`` is found, the table is
        missing, the list is empty, or any entry is not a string.
    """
    found = find_pyproject(start)
    if found is None:
        raise ConfigError(
            "no [tool.auntiepypi].packages found: no pyproject.toml between "
            "the start path and $HOME"
        )
    with found.open("rb") as f:
        data = tomllib.load(f)
    table = data.get("tool", {}).get("auntiepypi", {})
    if "packages" not in table:
        raise ConfigError("no [tool.auntiepypi].packages key found in pyproject.toml")
    pkgs = table["packages"]
    if not isinstance(pkgs, list) or not pkgs:
        raise ConfigError("[tool.auntiepypi].packages is empty or not a list")
    bad = [p for p in pkgs if not isinstance(p, str)]
    if bad:
        raise ConfigError(f"non-string entry in [tool.auntiepypi].packages: {bad!r}")
    return list(pkgs)
