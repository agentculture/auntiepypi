"""Runtime probe — TCP-then-HTTP check against one Probe.

Two-stage so we can distinguish:

* ``absent`` — nothing listening on the port (port closed)
* ``down``   — something is listening but it isn't a healthy PyPI server
* ``up``     — listening and HTTP responded 2xx

Both stages enforce the caller's ``timeout`` so a hung host doesn't stall
``overview``. No external deps; stdlib only.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from typing import TypedDict

from agentpypi._probes._probe import Probe


class ProbeResult(TypedDict, total=False):
    name: str
    port: int
    url: str
    status: str  # "up" | "down" | "absent"
    detail: str  # populated on "down" with the reason


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_status(
    probe: Probe,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    timeout: float = 1.0,
) -> ProbeResult:
    """Probe one server; return a structured status dict."""
    p = port if port is not None else probe.default_port
    url = probe.health_url(host=host, port=p)

    if not _tcp_open(host, p, timeout):
        return {"name": probe.name, "port": p, "url": url, "status": "absent"}

    try:
        # The URL is constructed from the Probe definition (literal `http://`
        # scheme + host:port + health_path) — no caller-controlled scheme.
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 # nosec B310
            if 200 <= resp.status < 300:
                return {"name": probe.name, "port": p, "url": url, "status": "up"}
            return {
                "name": probe.name,
                "port": p,
                "url": url,
                "status": "down",
                "detail": f"http {resp.status}",
            }
    except urllib.error.HTTPError as err:
        return {
            "name": probe.name,
            "port": p,
            "url": url,
            "status": "down",
            "detail": f"http {err.code}",
        }
    except OSError as err:
        # OSError is the umbrella class here:
        #   - urllib.error.URLError derives from OSError (covers DNS, refused, …)
        #   - TimeoutError derives from OSError (covers urllib timeout=…)
        # Catching just OSError keeps SonarRule python:S5713 happy and is
        # exactly equivalent to the prior tuple.
        return {
            "name": probe.name,
            "port": p,
            "url": url,
            "status": "down",
            "detail": str(err),
        }
