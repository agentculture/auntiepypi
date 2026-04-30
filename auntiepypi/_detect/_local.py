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
"""

from __future__ import annotations

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import probe_endpoint

_TIMEOUT = 1.0


def detect() -> Detection:
    """Return one Detection for the first-party server."""
    # Local import so module load doesn't reach for pyproject if the
    # caller never invokes detection.
    from auntiepypi._detect._config import load_local_config

    cfg = load_local_config()
    outcome = probe_endpoint(cfg.host, cfg.port, timeout=_TIMEOUT)
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
    if not 200 <= outcome.http_status < 300:
        return Detection(status="down", detail=f"http {outcome.http_status}", **common)
    return Detection(status="up", **common)
