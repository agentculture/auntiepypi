"""Post-spawn re-probe loop.

Polls a server at increasing intervals within a caller-supplied wall-clock
budget. Exits early when the observed status matches the caller's
``desired`` state (``"up"`` for start/restart; ``"down"`` for stop).
On budget exhaustion the final attempt's result is returned.

Poll offsets (seconds): 0.5, 1.0, 2.0, 3.5, 5.0
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import content_type, probe_endpoint
from auntiepypi._detect._port import fingerprint_flavor

# Relative offsets from the start of ``probe()`` at which attempts are made.
_OFFSETS: tuple[float, ...] = (0.5, 1.0, 2.0, 3.5, 5.0)
_TIMEOUT = 1.0


@dataclass(frozen=True)
class ReprobeResult:
    """Outcome of the post-spawn re-probe loop."""

    status: str  # "up" | "down" | "absent"
    detail: str | None = None


def _attempt(detection: Detection) -> ReprobeResult:
    """Run one TCP+HTTP probe against *detection* and classify the result.

    For ``source="local"`` (the first-party auntie server) the probe
    must mirror :func:`auntiepypi._detect._local.detect`'s semantics:
    HTTPS scheme when TLS is configured, and 401 counts as ``up`` when
    auth is configured. Otherwise ``command.start()`` /
    ``auntie restart`` would report failure for a healthy HTTPS-only
    or auth-gated server.
    """
    scheme = "http"
    ssl_ctx = None
    cfg_local = None
    if detection.source == "local":
        # Local import to avoid a circular ref between _actions/_reprobe
        # and _detect/_config (which imports LocalConfig).
        from auntiepypi._detect._config import load_local_config
        from auntiepypi._detect._local import local_probe_scheme_and_context

        cfg_local = load_local_config()
        scheme, ssl_ctx = local_probe_scheme_and_context(cfg_local)

    outcome = probe_endpoint(
        detection.host,
        detection.port,
        path="/",
        timeout=_TIMEOUT,
        scheme=scheme,
        ssl_context=ssl_ctx,
    )

    if not outcome.tcp_open:
        return ReprobeResult(status="absent")

    if outcome.http_status is None:
        return ReprobeResult(status="down", detail=outcome.error or "http error")

    if cfg_local is not None:
        # Defer the local-server semantics (2xx OR 401-with-auth) to
        # the shared classifier so this stays in lock-step with
        # _detect/_local.detect().
        from auntiepypi._detect._local import local_response_is_up

        if local_response_is_up(outcome.http_status, cfg_local):
            return ReprobeResult(status="up")
        return ReprobeResult(status="down", detail=f"http {outcome.http_status}")

    if not 200 <= outcome.http_status < 300:
        return ReprobeResult(status="down", detail=f"http {outcome.http_status}")

    # 2xx — verify flavor unless declared flavor is "unknown" or
    # "auntiepypi" (the first-party server's PEP 503 surface looks
    # identical to pypiserver via the HREF fingerprint, so the check
    # would always claim a flavor mismatch).
    if detection.flavor not in ("unknown", "auntiepypi"):
        observed = fingerprint_flavor(outcome.body, content_type(outcome))
        if observed != detection.flavor and observed != "unknown":
            return ReprobeResult(
                status="down",
                detail=f"flavor mismatch: expected {detection.flavor!r}, saw {observed!r}",
            )

    return ReprobeResult(status="up")


def _matches_desired(status: str, desired: Literal["up", "down"]) -> bool:
    """``desired="up"`` matches only "up"; ``desired="down"`` matches only "absent".

    "down" with TCP open (HTTP error / non-2xx / flavor mismatch) means the
    server is still listening — `stop` shouldn't claim victory. We require
    "absent" (TCP closed; port truly unbound) to confirm shutdown.
    """
    if desired == "up":
        return status == "up"
    return status == "absent"


def probe(
    detection: Detection,
    *,
    budget_seconds: float = 5.0,
    desired: Literal["up", "down"] = "up",
    _sleep: Callable[[float], None] = time.sleep,
    _now: Callable[[], float] = time.monotonic,
) -> ReprobeResult:
    """Poll *detection* until ``status`` matches ``desired`` or budget exhausted.

    Attempt offsets are 0.5 s, 1.0 s, 2.0 s, 3.5 s, 5.0 s from start.
    First match wins; the last attempt's result is returned on exhaustion.

    :param detection: Server description to probe.
    :param budget_seconds: Wall-clock ceiling; attempts past this are skipped.
    :param desired: Target state — ``"up"`` for start/restart (default;
        v0.4.0 behavior); ``"down"`` for stop. ``"down"`` matches both
        "down" and "absent".
    :param _sleep: Injectable sleep callable (for tests).
    :param _now: Injectable monotonic clock (for tests).
    """
    start = _now()
    result = ReprobeResult(status="absent")

    for offset in _OFFSETS:
        if offset > budget_seconds:
            break

        # Sleep until the scheduled offset, accounting for time already spent.
        elapsed = _now() - start
        wait = offset - elapsed
        if wait > 0:
            _sleep(wait)

        result = _attempt(detection)
        if _matches_desired(result.status, desired):
            return result

    return result
