"""``detect_all`` — single entry point for callers.

Order of operations:

1. ``_declared.detect`` first. Build ``covered = {(host, port) ...}``.
2. ``_port.detect`` over default ports minus ``covered``. If declarations
   exist, drop ``status="absent"`` from the port detector's output
   (the augment + suppress-absent rule).
3. If ``scan_processes``: ``_proc.detect``. Merge by ``(host, port)`` —
   proc-found pids enrich existing detections; proc-only detections are
   appended.
"""

from __future__ import annotations

from dataclasses import replace

from auntiepypi._detect._config import ServersConfig
from auntiepypi._detect._declared import detect as _declared_detect
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._port import detect as _port_detect
from auntiepypi._detect._proc import detect as _proc_detect


def detect_all(config: ServersConfig) -> list[Detection]:
    """Run all detectors and merge results."""
    declared_results = _declared_detect(config.specs, scan_processes=config.scan_processes)
    covered: set[tuple[str, int]] = {(d.host, d.port) for d in declared_results}

    port_results = _port_detect(
        config.specs,
        scan_processes=config.scan_processes,
        covered=covered,
    )
    if declared_results:
        port_results = [d for d in port_results if d.status != "absent"]

    detections = list(declared_results) + list(port_results)

    if not config.scan_processes:
        return detections

    proc_results = _proc_detect(
        config.specs,
        scan_processes=config.scan_processes,
    )
    return _merge_proc(detections, proc_results)


def _merge_proc(base: list[Detection], proc_results: list[Detection]) -> list[Detection]:
    """Enrich ``base`` with PIDs from ``proc_results``; append proc-only finds."""
    by_endpoint: dict[tuple[str, int], int] = {(d.host, d.port): i for i, d in enumerate(base)}
    appended: list[Detection] = []
    for p in proc_results:
        key = (p.host, p.port)
        if key in by_endpoint:
            i = by_endpoint[key]
            existing = base[i]
            base[i] = replace(
                existing,
                pid=existing.pid if existing.pid is not None else p.pid,
                cmdline=existing.cmdline if existing.cmdline is not None else p.cmdline,
            )
        else:
            appended.append(p)
    return base + appended
