"""Strategy for `managed_by = "command"`: detached Popen + sync re-probe.

Spawns the configured argv with `start_new_session=True` (new process
group, immune to doctor's exit), redirects stdio to
``$XDG_STATE_HOME/auntiepypi/<slug>.log``, and returns once the
re-probe loop confirms ``up`` or the 5 s budget is exhausted.

Doctor does NOT track the child past spawn. ``auntie down`` (v0.5.0)
will own process-tracking.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._logs import path_for
from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

# Indirection for tests: monkey-patch this to a FakePopen.
POPEN = subprocess.Popen


def apply(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Spawn the command, re-probe, return result. See module docstring."""
    if not declaration.command:
        return ActionResult(ok=False, detail="managed_by=command but `command` not set")

    log_path = path_for(declaration.name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(log_path, "ab") as logf:
            logf.write(
                f"\n=== {datetime.now(timezone.utc).isoformat()}: starting "
                f"{list(declaration.command)} ===\n".encode()
            )
            logf.flush()
            try:
                proc = POPEN(
                    list(declaration.command),
                    start_new_session=True,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                )
            except FileNotFoundError as err:
                return ActionResult(
                    ok=False,
                    detail=f"command not found: {err.filename or declaration.command[0]}",
                    log_path=str(log_path),
                )
            except PermissionError as err:
                return ActionResult(
                    ok=False,
                    detail=f"permission denied: {err.filename or declaration.command[0]}",
                    log_path=str(log_path),
                )
            except OSError as err:
                return ActionResult(
                    ok=False,
                    detail=f"{type(err).__name__}: {err}",
                    log_path=str(log_path),
                )
    except OSError as err:  # opening the log file itself
        return ActionResult(ok=False, detail=f"could not open log: {err}")

    # Early-exit check: did the child die before we even started polling?
    if proc.poll() is not None:
        return ActionResult(
            ok=False,
            detail=f"command exited immediately (rc={proc.returncode}); see {log_path}",
            log_path=str(log_path),
            pid=None,
        )

    pid = proc.pid
    result = probe(detection)
    if result.status == "up":
        return ActionResult(
            ok=True,
            detail="started",
            log_path=str(log_path),
            pid=pid,
        )

    # Spawned, still alive, but didn't bind/respond
    if proc.poll() is None:
        return ActionResult(
            ok=False,
            detail=f"spawned but not responding after 5s (pid={pid}, log: {log_path})",
            log_path=str(log_path),
            pid=pid,
        )
    # Child exited during the re-probe window — treat as immediate exit
    return ActionResult(
        ok=False,
        detail=f"command exited immediately (rc={proc.returncode}); see {log_path}",
        log_path=str(log_path),
        pid=None,
    )
