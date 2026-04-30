"""Uniform return value for any lifecycle strategy.

Strategies live in `auntiepypi/_actions/<managed_by>.py`. Each exposes
``start(detection, declaration)``, ``stop(detection, declaration)``,
``restart(detection, declaration)`` — all returning ``ActionResult``.
`dispatch()` in ``_actions/__init__.py`` routes on (action, managed_by).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionResult:
    """Result of one strategy attempt.

    :param ok: True iff the post-action re-probe (or strategy-internal
        success criterion) confirms the server reached the desired
        state ("up" for start/restart, "down" for stop).
    :param detail: One-line human-readable summary; merged into JSON
        envelope as ``fix_detail``.
    :param log_path: Where the strategy wrote logs (``command`` only;
        ``systemd-user`` is None — journald owns its logs).
    :param pid: Spawned PID, when known. ``systemd-user`` is None.
    """

    ok: bool
    detail: str
    log_path: str | None = None
    pid: int | None = None
