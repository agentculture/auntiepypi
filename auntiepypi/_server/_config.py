"""Configuration for the first-party PEP 503 simple-index server.

``LocalConfig`` is a frozen dataclass with three core fields and three
optional v0.7.0 fields, all defaulted:

- ``host``: bind address. Loopback is always allowed; non-loopback
  binds require both TLS (``cert`` + ``key``) AND auth (``htpasswd``).
- ``port``: bind port. Default ``3141`` (the conventional private-index
  port). User overrides via ``[tool.auntiepypi.local].port`` if a
  declared devpi conflicts.
- ``root``: wheelhouse directory. Default
  ``$XDG_DATA_HOME/auntiepypi/wheels/`` (or ``~/.local/share/...`` when
  ``XDG_DATA_HOME`` is unset). User overrides via
  ``[tool.auntiepypi.local].root``.
- ``cert`` / ``key`` (v0.7.0): PEM paths for HTTPS termination via
  ``ssl.SSLContext.load_cert_chain``. Both must be set together.
  Operator-supplied; auntie does not auto-generate.
- ``htpasswd`` (v0.7.0): Apache htpasswd file (bcrypt-only entries) for
  HTTP Basic auth.

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
    cert: Path | None = None
    key: Path | None = None
    htpasswd: Path | None = None

    @property
    def tls_enabled(self) -> bool:
        """True iff both ``cert`` and ``key`` are set.

        Half-configured TLS (just one of the pair) is never True; the
        config-load validator rejects it before this property runs.
        """
        return self.cert is not None and self.key is not None

    @property
    def auth_enabled(self) -> bool:
        """True iff ``htpasswd`` is set."""
        return self.htpasswd is not None
