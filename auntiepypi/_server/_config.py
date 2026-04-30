"""Configuration for the first-party PEP 503 simple-index server.

``LocalConfig`` is a frozen dataclass with three fields, all defaulted:

- ``host``: bind address. v0.6.0 enforces loopback at config-load time.
- ``port``: bind port. Default ``3141`` (the conventional private-index
  port). User overrides via ``[tool.auntiepypi.local].port`` if a
  declared devpi conflicts.
- ``root``: wheelhouse directory. Default
  ``$XDG_DATA_HOME/auntiepypi/wheels/`` (or ``~/.local/share/...`` when
  ``XDG_DATA_HOME`` is unset). User overrides via
  ``[tool.auntiepypi.local].root``.

The loader (``auntiepypi._detect._config.load_local_config``) reads
``[tool.auntiepypi.local]`` from ``pyproject.toml`` if present and
returns a ``LocalConfig`` regardless — defaults apply when the table
is missing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_PORT = 3141
_DEFAULT_HOST = "127.0.0.1"


def default_root() -> Path:
    """Return ``$XDG_DATA_HOME/auntiepypi/wheels`` (or ``~/.local/share/...``)."""
    base = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return Path(base).expanduser() / "auntiepypi" / "wheels"


@dataclass(frozen=True)
class LocalConfig:
    """First-party server config (read from ``[tool.auntiepypi.local]``)."""

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    root: Path = field(default_factory=default_root)
