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


def apply(detection: Detection, declaration: ServerSpec) -> ActionResult:
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
