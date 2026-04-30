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
from pathlib import Path

from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._logs import path_for
from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

# Indirection for tests: monkey-patch this to a FakePopen.
POPEN = subprocess.Popen


def start(detection: Detection, declaration: ServerSpec) -> ActionResult:
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
                    cwd=str(Path.cwd()),
                )
            except OSError as err:
                return _spawn_error(err, declaration, log_path)
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


def _spawn_error(err: OSError, declaration: ServerSpec, log_path: Path) -> ActionResult:
    """Map a Popen-time OSError to an ActionResult.

    `FileNotFoundError` and `PermissionError` are subclasses of OSError and get
    distinguished phrasing here; the catch-all OSError branch is for everything
    else (ENOEXEC, EMFILE, etc.) and surfaces the type name + str(err).
    """
    argv0 = err.filename or declaration.command[0] if declaration.command else "<unset>"
    if isinstance(err, FileNotFoundError):
        detail = f"command not found: {argv0}"
    elif isinstance(err, PermissionError):
        detail = f"permission denied: {argv0}"
    else:
        detail = f"{type(err).__name__}: {err}"
    return ActionResult(ok=False, detail=detail, log_path=str(log_path))


def stop(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Stop a `managed_by=command` server. Implementation lands in task 6."""
    _ = (detection, declaration)
    return ActionResult(ok=False, detail="command.stop not yet implemented")


def restart(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Restart a `managed_by=command` server. Implementation lands in task 7."""
    _ = (detection, declaration)
    return ActionResult(ok=False, detail="command.restart not yet implemented")
