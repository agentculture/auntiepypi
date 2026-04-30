"""XDG state directory + filename slugifier for `command`-strategy logs.

The `command` strategy detaches via ``Popen`` and redirects stdio to a
log file. The path is ``$XDG_STATE_HOME/auntiepypi/<slug>.log`` (or
``~/.local/state/auntiepypi/<slug>.log`` when XDG is unset).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_SLUG_OK = re.compile(r"[a-z0-9._-]")


def state_root() -> Path:
    """Return the auntiepypi state directory, respecting `$XDG_STATE_HOME`."""
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".local" / "state") / "auntiepypi"


def slugify(name: str) -> str:
    """Lowercase + replace non-`[a-z0-9._-]` with `_`. Defends against unsafe `name` values."""
    return "".join(ch if _SLUG_OK.match(ch) else "_" for ch in name.lower())


def path_for(name: str) -> Path:
    """Log file path for a declared server `name`."""
    return state_root() / f"{slugify(name)}.log"
