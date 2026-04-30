"""Declared-inventory detector.

Probes each ``ServerSpec`` from ``[[tool.auntiepypi.servers]]`` and
emits one :class:`Detection`. Propagates declaration metadata
(``managed_by``, ``unit``, …) through unchanged. Validates the
declared flavor against the fingerprint and reports a flavor mismatch
as ``status="down"``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import ProbeOutcome, content_type, probe_endpoint
from auntiepypi._detect._port import fingerprint_flavor

_TIMEOUT = 1.0


def _common_kwargs(spec: ServerSpec, outcome: ProbeOutcome) -> dict:
    return {
        "name": spec.name,
        "flavor": spec.flavor,
        "host": spec.host,
        "port": spec.port,
        "url": outcome.url,
        "source": "declared",
        "managed_by": spec.managed_by,
        "unit": spec.unit,
        "dockerfile": spec.dockerfile,
        "compose": spec.compose,
        "service": spec.service,
        "command": spec.command,
    }


def _detection_for(spec: ServerSpec, outcome: ProbeOutcome) -> Detection:
    common = _common_kwargs(spec, outcome)
    if not outcome.tcp_open:
        return Detection(status="absent", **common)
    if outcome.http_status is None:
        return Detection(status="down", detail=outcome.error or "http error", **common)
    if not 200 <= outcome.http_status < 300:
        return Detection(status="down", detail=f"http {outcome.http_status}", **common)
    # 2xx — verify flavor (skip when declared flavor is "unknown")
    if spec.flavor != "unknown":
        observed = fingerprint_flavor(outcome.body, content_type(outcome))
        if observed != spec.flavor and observed != "unknown":
            return Detection(
                status="down",
                detail=f"flavor mismatch: expected {spec.flavor!r}, saw {observed!r}",
                **common,
            )
    return Detection(status="up", **common)


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
) -> list[Detection]:
    """Probe each declared spec; emit one Detection per spec."""
    del scan_processes  # not relevant to this detector
    specs = list(declared)
    if not specs:
        return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        outcomes = list(
            ex.map(
                lambda s: probe_endpoint(s.host, s.port, timeout=_TIMEOUT),
                specs,
            )
        )
    return [_detection_for(s, o) for s, o in zip(specs, outcomes)]
