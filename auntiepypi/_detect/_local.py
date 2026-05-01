"""First-party server detector.

Always emits exactly one :class:`Detection` for the auntie-managed
PEP 503 simple-index server (``[tool.auntiepypi.local]``), regardless
of whether the server is currently running. When the server is not
running, the Detection has ``status="absent"``; this lets ``auntie
overview`` always show a "your local index" section.

The Detection's ``source`` is ``"local"`` so callers can distinguish
it from the user-declared / port-scanned / proc-walked surfaces.

Runs **first** in :func:`auntiepypi._detect._runtime.detect_all` so
its ``(host, port)`` enters the ``covered`` set and the default-port
scanner doesn't double-report the local server as ``devpi`` on 3141.

v0.7.0: when ``cfg.tls_enabled``, the probe runs over HTTPS with an
unverified SSL context (this is a self-probe of our own listener, not
a trust decision; the cert is often self-signed in mesh-internal use).
When ``cfg.auth_enabled``, a ``401`` response counts as ``up`` — a
working auth gate is a stronger liveness signal than an open 200, and
the detector deliberately does not read htpasswd to extract creds.

The helpers :func:`local_probe_scheme_and_context` and
:func:`local_response_is_up` are reused by
:mod:`auntiepypi._actions._reprobe` so ``command.start()`` /
``auntie restart`` agree with this detector on what "up" means for the
local server (otherwise an HTTPS-only or auth-on first-party server
would always reprobe as down even when healthy).
"""

from __future__ import annotations

import ssl

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import probe_endpoint
from auntiepypi._server._config import LocalConfig

_TIMEOUT = 1.0


def _unverified_self_probe_context() -> ssl.SSLContext:
    """Build an SSL context that skips cert verification.

    Used for self-probes of our own first-party listener — the
    ``(host, port)`` came from our own pyproject, so this is not a
    trust decision. The cert may be self-signed in mesh-internal use;
    verifying would force operators to plumb their internal CA into
    auntie for no upside.
    """
    return ssl._create_unverified_context()  # noqa: S323  # nosec B323  # NOSONAR python:S4830


def local_probe_scheme_and_context(cfg: LocalConfig) -> tuple[str, ssl.SSLContext | None]:
    """Return ``(scheme, ssl_context)`` for a probe against the local server."""
    if cfg.tls_enabled:
        return "https", _unverified_self_probe_context()
    return "http", None


def local_response_is_up(http_status: int, cfg: LocalConfig) -> bool:
    """Classify a probe response against the local-server semantics.

    A 2xx is always up. With ``cfg.auth_enabled``, a 401 also counts
    as up — a working auth gate is a stronger liveness signal than an
    open 200, and we deliberately don't read htpasswd to send creds.
    """
    if 200 <= http_status < 300:
        return True
    return bool(cfg.auth_enabled) and http_status == 401


def detect() -> Detection:
    """Return one Detection for the first-party server."""
    # Local import so module load doesn't reach for pyproject if the
    # caller never invokes detection.
    from auntiepypi._detect._config import load_local_config

    cfg = load_local_config()
    scheme, ssl_ctx = local_probe_scheme_and_context(cfg)
    outcome = probe_endpoint(
        cfg.host,
        cfg.port,
        timeout=_TIMEOUT,
        scheme=scheme,
        ssl_context=ssl_ctx,
    )
    common = {
        "name": "auntie",
        "flavor": "auntiepypi",
        "host": cfg.host,
        "port": cfg.port,
        "url": outcome.url,
        "source": "local",
        "managed_by": "auntie",
    }
    if not outcome.tcp_open:
        return Detection(status="absent", **common)
    if outcome.http_status is None:
        return Detection(status="down", detail=outcome.error or "http error", **common)
    if local_response_is_up(outcome.http_status, cfg):
        return Detection(status="up", **common)
    return Detection(status="down", detail=f"http {outcome.http_status}", **common)
