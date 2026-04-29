"""Default-port scanner.

Probes a small fixed set of well-known PyPI server ports on localhost.
Each probe emits a :class:`Detection` regardless of outcome (absent
detections matter for the overview report, except when declarations
exist — see :mod:`auntiepypi._detect._runtime`).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import ProbeOutcome, probe_endpoint

DEFAULT_PORTS: tuple[int, ...] = (3141, 8080)
# Conventional flavor for each default port — used as the *expected* flavor when
# nothing is listening, so the report says "pypiserver:8080 absent" rather than
# "unknown:8080 absent" for ports we recognise.
_PORT_FLAVOR: dict[int, str] = {3141: "devpi", 8080: "pypiserver"}
_DEFAULT_HOST = "127.0.0.1"
_TIMEOUT = 1.0
_HREF_DIR = re.compile(rb'<a\s+href=["\'][^"\']+/["\']', re.IGNORECASE)


def fingerprint_flavor(body: bytes | None, content_type: str | None) -> str:
    """Return ``"devpi"`` | ``"pypiserver"`` | ``"unknown"`` for one HTTP body."""
    if body is None:
        return "unknown"
    if content_type and "json" in content_type.lower():
        try:
            data = json.loads(body)
        except ValueError:
            # ValueError covers both JSONDecodeError and UnicodeDecodeError here.
            data = None
        if isinstance(data, dict) and "resources" in data:
            return "devpi"
        return "unknown"
    matches = _HREF_DIR.findall(body)
    if matches:
        return "pypiserver"
    return "unknown"


def _content_type(outcome: ProbeOutcome) -> str | None:
    if outcome.body is None:
        return None
    head = outcome.body.lstrip()[:1]
    if head == b"{":
        return "application/json"
    if head == b"<":
        return "text/html"
    return None


def _detection_for(host: str, port: int, outcome: ProbeOutcome) -> Detection:
    if not outcome.tcp_open:
        expected = _PORT_FLAVOR.get(port, "unknown")
        return Detection(
            name=f"{expected}:{port}",
            flavor=expected,
            host=host,
            port=port,
            url=outcome.url,
            status="absent",
            source="port",
        )
    flavor = fingerprint_flavor(outcome.body, _content_type(outcome))
    if outcome.http_status is None:
        return Detection(
            name=f"{flavor}:{port}",
            flavor=flavor,
            host=host,
            port=port,
            url=outcome.url,
            status="down",
            source="port",
            detail=outcome.error or "http error",
        )
    if 200 <= outcome.http_status < 300:
        return Detection(
            name=f"{flavor}:{port}",
            flavor=flavor,
            host=host,
            port=port,
            url=outcome.url,
            status="up",
            source="port",
        )
    return Detection(
        name=f"{flavor}:{port}",
        flavor=flavor,
        host=host,
        port=port,
        url=outcome.url,
        status="down",
        source="port",
        detail=f"http {outcome.http_status}",
    )


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
    covered: set[tuple[str, int]] | None = None,
) -> list[Detection]:
    """Probe ``DEFAULT_PORTS`` on localhost; skip any ``(host, port)`` in ``covered``."""
    del declared, scan_processes  # signature parity; not used here
    skip = covered or set()
    targets = [(_DEFAULT_HOST, p) for p in DEFAULT_PORTS if (_DEFAULT_HOST, p) not in skip]
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        outcomes = list(ex.map(lambda hp: probe_endpoint(hp[0], hp[1], timeout=_TIMEOUT), targets))
    return [_detection_for(host, port, o) for (host, port), o in zip(targets, outcomes)]
