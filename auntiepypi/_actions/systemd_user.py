"""Strategy for `managed_by = "systemd-user"`: `systemctl --user start <unit>`.

systemctl returns 0 once the unit is `active` per its `Type=`; for
`Type=simple` units that means "process spawned," not "port bound and
serving." So we *also* run the re-probe and require ``up`` to claim
success.
"""

from __future__ import annotations

import subprocess
from typing import Callable

from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

# Indirection for tests.
RUN: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run


def start(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Run `systemctl --user start <unit>`, then re-probe."""
    if not declaration.unit:
        return ActionResult(ok=False, detail="managed_by=systemd-user but `unit` not set")

    try:
        completed = RUN(
            ["systemctl", "--user", "start", declaration.unit],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return ActionResult(
            ok=False,
            detail="systemctl not found; install systemd-user or use managed_by=command",
        )
    except subprocess.TimeoutExpired:
        return ActionResult(ok=False, detail="systemctl timed out")
    except (OSError, subprocess.SubprocessError) as err:
        return ActionResult(ok=False, detail=f"{type(err).__name__}: {err}")

    if completed.returncode != 0:
        first_line = (completed.stderr or completed.stdout or "").strip().splitlines()
        snippet = first_line[0] if first_line else ""
        if snippet:
            detail = f"systemctl exit {completed.returncode}: {snippet}"
        else:
            detail = f"systemctl exit {completed.returncode}"
        return ActionResult(ok=False, detail=detail)

    result = probe(detection)
    if result.status == "up":
        return ActionResult(ok=True, detail="started")
    return ActionResult(
        ok=False,
        detail=(
            "systemctl ok but server not responding "
            f"(check unit logs: journalctl --user -u {declaration.unit})"
        ),
    )


def _run_systemctl(unit: str, verb: str) -> ActionResult | subprocess.CompletedProcess[str]:
    """Wrap `systemctl --user <verb> <unit>`; map exec-time errors to ActionResult."""
    try:
        completed = RUN(
            ["systemctl", "--user", verb, unit],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return ActionResult(
            ok=False,
            detail="systemctl not found; install systemd-user or use managed_by=command",
        )
    except subprocess.TimeoutExpired:
        return ActionResult(ok=False, detail="systemctl timed out")
    except (OSError, subprocess.SubprocessError) as err:
        return ActionResult(ok=False, detail=f"{type(err).__name__}: {err}")
    return completed


def _systemctl_failure_detail(completed: subprocess.CompletedProcess[str]) -> str:
    """Format a non-zero systemctl exit into a one-line detail."""
    first_line = (completed.stderr or completed.stdout or "").strip().splitlines()
    snippet = first_line[0] if first_line else ""
    if snippet:
        return f"systemctl exit {completed.returncode}: {snippet}"
    return f"systemctl exit {completed.returncode}"


def stop(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Run `systemctl --user stop <unit>`, then re-probe with desired=down."""
    if not declaration.unit:
        return ActionResult(ok=False, detail="managed_by=systemd-user but `unit` not set")

    completed = _run_systemctl(declaration.unit, "stop")
    if isinstance(completed, ActionResult):
        return completed
    if completed.returncode != 0:
        return ActionResult(ok=False, detail=_systemctl_failure_detail(completed))

    result = probe(detection, desired="down")
    if result.status in ("down", "absent"):
        return ActionResult(ok=True, detail="stopped")
    return ActionResult(
        ok=False,
        detail=(
            "systemctl ok but server still responding "
            f"(check unit logs: journalctl --user -u {declaration.unit})"
        ),
    )


def restart(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Run `systemctl --user restart <unit>` (atomic), then re-probe with desired=up."""
    if not declaration.unit:
        return ActionResult(ok=False, detail="managed_by=systemd-user but `unit` not set")

    completed = _run_systemctl(declaration.unit, "restart")
    if isinstance(completed, ActionResult):
        return completed
    if completed.returncode != 0:
        return ActionResult(ok=False, detail=_systemctl_failure_detail(completed))

    result = probe(detection)
    if result.status == "up":
        return ActionResult(ok=True, detail="restarted")
    return ActionResult(
        ok=False,
        detail=(
            "systemctl ok but server not responding after restart "
            f"(check unit logs: journalctl --user -u {declaration.unit})"
        ),
    )
