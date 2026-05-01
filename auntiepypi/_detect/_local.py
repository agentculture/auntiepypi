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
"""

from __future__ import annotations

import ssl

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import probe_endpoint

_TIMEOUT = 1.0


def _unverified_self_probe_context() -> ssl.SSLContext:
    """Build an SSL context that skips cert verification.

    Used only by ``detect()`` for the self-probe of our own first-party
    listener — the ``(host, port)`` came from our own pyproject, so this
    is not a trust decision. The cert may be self-signed in mesh-internal
    use; verifying would force operators to plumb their internal CA
    into auntie for no upside.
    """
    return ssl._create_unverified_context()  # noqa: S323  # nosec B323  # NOSONAR python:S4830


def detect() -> Detection:
    """Return one Detection for the first-party server."""
    # Local import so module load doesn't reach for pyproject if the
    # caller never invokes detection.
    from auntiepypi._detect._config import load_local_config

    cfg = load_local_config()
    if cfg.tls_enabled:
        scheme = "https"
        ssl_ctx = _unverified_self_probe_context()
    else:
        scheme = "http"
        ssl_ctx = None
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
    if 200 <= outcome.http_status < 300:
        return Detection(status="up", **common)
    if cfg.auth_enabled and outcome.http_status == 401:
        # 401 from our own server with auth on means the auth gate is
        # working — strong liveness signal.
        return Detection(status="up", **common)
    return Detection(status="down", detail=f"http {outcome.http_status}", **common)
