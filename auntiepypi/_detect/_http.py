"""TCP-then-HTTP probe primitive shared by ``_declared`` and ``_port``.

Two-stage by design (mirrors ``_probes/_runtime.probe_status``): TCP
first to distinguish "nothing listening" from "HTTP misbehaving"; then
HTTP GET with a small body read for flavor fingerprinting.

Stdlib only. No retries. Caller-supplied timeout enforced on both stages.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from auntiepypi import __version__

_MAX_BODY_BYTES = 4096
_USER_AGENT = f"auntie/{__version__}"


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of one TCP+HTTP probe."""

    url: str
    tcp_open: bool
    http_status: int | None  # None when TCP closed
    body: bytes | None  # first ~4 KiB of response body; None on error/timeout
    error: str | None  # populated on connection error or HTTP timeout


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_endpoint(
    host: str,
    port: int,
    *,
    path: str = "/",
    timeout: float = 1.0,
) -> ProbeOutcome:
    """Probe ``http://host:port<path>``.

    Returns a :class:`ProbeOutcome` with the TCP/HTTP results. Never
    raises — every failure mode maps onto a field.
    """
    # NOSONAR python:S5332 — probing localhost PyPI servers; HTTPS is not the
    # protocol these servers speak (`pypi-server`, `devpi-server` default to
    # plain HTTP for in-mesh use). We never dereference this for transport
    # outside the local box.
    url = f"http://{host}:{port}{path}"  # noqa: S310  # nosec B310
    if not _tcp_open(host, port, timeout):
        return ProbeOutcome(url=url, tcp_open=False, http_status=None, body=None, error=None)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    try:
        # URL is host+port-from-trusted-config + literal http:// scheme.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 # nosec B310
            return ProbeOutcome(
                url=url,
                tcp_open=True,
                http_status=resp.status,
                body=resp.read(_MAX_BODY_BYTES),
                error=None,
            )
    except urllib.error.HTTPError as err:
        try:
            body = err.read(_MAX_BODY_BYTES)
        except OSError:
            body = None
        return ProbeOutcome(
            url=url,
            tcp_open=True,
            http_status=err.code,
            body=body,
            error=None,
        )
    except OSError as err:  # URLError, timeout, etc.
        return ProbeOutcome(
            url=url,
            tcp_open=True,
            http_status=None,
            body=None,
            error=f"{err.__class__.__name__}: {err}",
        )
