"""auntiepypi detection layer.

Parallels ``_probes/`` but produces a richer, declaration-driven inventory
of running PyPI servers. ``_probes/`` is the *raise* path (used by
``doctor --fix``); ``_detect/`` is the *display* path (used by
``auntie overview``'s servers section).

Public surface:

* :class:`Detection` — frozen dataclass; one running/declared server.
* :func:`detect_all` — runs every detector, merges results.
* :class:`ServerSpec` / :class:`ServersConfig` / :func:`load_servers` —
  TOML loader for ``[[tool.auntiepypi.servers]]``.
"""

from __future__ import annotations

from auntiepypi._detect._config import (
    ServerConfigError,
    ServerSpec,
    ServersConfig,
    load_servers,
)
from auntiepypi._detect._detection import Detection

__all__ = [
    "Detection",
    "ServerConfigError",
    "ServerSpec",
    "ServersConfig",
    "load_servers",
]
