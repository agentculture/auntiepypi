"""Strategy for `managed_by = "command"`: detached Popen + sync re-probe.

`start` spawns the configured argv with `start_new_session=True` (new
process group, immune to doctor's exit), redirects stdio to
``$XDG_STATE_HOME/auntiepypi/<slug>.log``, and returns once the
re-probe loop confirms ``up`` or the 5 s budget is exhausted. On
success it writes a PID file + sidecar via :mod:`_pid`.

`stop` reads the PID file (or falls back to a port-walk + argv-match
lookup), sends SIGTERM with a 5 s grace, escalates to SIGKILL if the
port is still bound, then clears the PID file. Idempotent: a missing
PID file with no listener on the declared port is treated as
"already stopped."

`restart` is `stop` then `start`. The new spawn re-uses the **current**
``declaration.command`` from pyproject (not the sidecar argv); drift
is logged for diagnostics but never blocks the action.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from auntiepypi._actions import _pid
from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._logs import path_for
from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

# Indirection for tests: monkey-patch this to a FakePopen.
POPEN = subprocess.Popen
# Indirection for tests: monkey-patch to capture signal calls without
# affecting real processes.
KILL = os.kill


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
        # Port-conflict false-success guard: a 200 from the probe could
        # come from a *different* process that already owned the port if
        # our spawn lost the bind race (or failed to bind because the
        # port was taken). Verify our spawned child is still alive
        # before claiming success — and on Linux, that the actual port
        # listener is our PID. Without these checks, we'd persist a
        # PID file pointing at a dead/wrong process.
        if proc.poll() is not None:
            return ActionResult(
                ok=False,
                detail=(
                    f"port {declaration.port} already serves a 200 response, "
                    f"but our spawn exited (rc={proc.returncode}); see {log_path}"
                ),
                log_path=str(log_path),
                pid=None,
            )
        if sys.platform == "linux":
            owner_pid = _pid.find_by_port(
                declaration.port,
                expected_argv=list(declaration.command),
            )
            if owner_pid is not None and owner_pid != pid:
                # Our spawn is alive but isn't the listener — a foreign
                # process owns the port. Reap and fail.
                _terminate_orphan(proc)
                return ActionResult(
                    ok=False,
                    detail=(
                        f"port {declaration.port} already bound by pid {owner_pid} "
                        f"(our spawn pid={pid} terminated); see {log_path}"
                    ),
                    log_path=str(log_path),
                    pid=None,
                )
        # Persist PID + sidecar for future `auntie down` / `restart`.
        try:
            _pid.write(
                declaration.name,
                pid=pid,
                argv=list(declaration.command),
                port=declaration.port,
            )
        except OSError:
            # PID file write failed; the start itself succeeded so we keep
            # ok=True. The fallback path-walk in `command.stop` will still
            # find the process by port + argv match.
            pass
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


def _terminate_orphan(proc: subprocess.Popen) -> None:
    """Reap a spawned process that lost the bind race. Best effort — the
    caller already returned ok=False, so a stuck child here just leaks
    a small amount of state into XDG.
    """
    try:
        KILL(proc.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            KILL(proc.pid, signal.SIGKILL)
        except OSError:
            pass


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


def _resolve_target_pid(declaration: ServerSpec) -> tuple[int | None, str]:
    """Find the PID to signal. Returns (pid, source) where source is
    "pid-file" or "port-walk", or (None, "") when no target is found.

    PID-file path: cross-check on Linux that the recorded PID is the
    listener on the declared port. PID reuse can leave a live-but-stale
    PID in the file; signaling it would kill an unrelated process.
    When the cross-check fails, clear the PID file and fall through to
    the port-walk fallback.
    """
    record = _pid.read(declaration.name, declaration.port)
    if record is not None and declaration.command:
        verified = _pid.find_by_port(
            declaration.port,
            expected_argv=list(declaration.command),
        )
        # If find_by_port returns None on non-Linux, trust the PID
        # file (best we can do without /proc). On Linux, require the
        # PID file's PID to match the actual listener.
        if sys.platform == "linux" and verified is not None and verified != record.pid:
            # Stale-but-live PID in the file; the actual listener is a
            # different process. Clear and fall through.
            _pid.clear(declaration.name, declaration.port)
        else:
            return record.pid, "pid-file"
    elif record is not None:
        # No declared command to verify against; trust the record.
        return record.pid, "pid-file"
    if declaration.command:
        pid = _pid.find_by_port(
            declaration.port,
            expected_argv=list(declaration.command),
        )
        if pid is not None:
            return pid, "port-walk"
    return None, ""


def stop(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """SIGTERM the tracked process; SIGKILL escalation; clear PID file."""
    target_pid, source = _resolve_target_pid(declaration)

    if target_pid is None:
        # No PID file AND port-walk found no argv-matching listener.
        # Distinguish "nothing listening" from "something listening but
        # wrong argv": if the port is currently up, refuse to kill (a
        # different process owns it); otherwise treat as already-stopped.
        liveness = probe(detection, desired="up", budget_seconds=0.5)
        if liveness.status == "up":
            return ActionResult(
                ok=False,
                detail=(
                    f"port {declaration.port} listener argv does not match "
                    f"declaration; refusing to kill"
                ),
            )
        _pid.clear(declaration.name, declaration.port)
        return ActionResult(ok=True, detail="already stopped")

    # Send SIGTERM, then poll for the port to unbind.
    try:
        KILL(target_pid, signal.SIGTERM)
    except ProcessLookupError:
        # Process died between read() and kill() — treat as success
        _pid.clear(declaration.name, declaration.port)
        return ActionResult(ok=True, detail="already stopped (race)")
    except OSError as err:
        return ActionResult(
            ok=False,
            detail=f"SIGTERM failed (pid={target_pid}): {err}",
        )

    result = probe(detection, desired="down", budget_seconds=5.0)
    if result.status == "absent":
        _pid.clear(declaration.name, declaration.port)
        suffix = "" if source == "pid-file" else f" (found via {source})"
        return ActionResult(ok=True, detail=f"stopped (SIGTERM){suffix}", pid=target_pid)

    # Still up after 5s grace — escalate to SIGKILL.
    try:
        KILL(target_pid, signal.SIGKILL)
    except ProcessLookupError:
        _pid.clear(declaration.name, declaration.port)
        return ActionResult(ok=True, detail="stopped (SIGTERM, race on SIGKILL)", pid=target_pid)
    except OSError as err:
        return ActionResult(ok=False, detail=f"SIGKILL failed (pid={target_pid}): {err}")

    result = probe(detection, desired="down", budget_seconds=2.0)
    if result.status == "absent":
        _pid.clear(declaration.name, declaration.port)
        return ActionResult(
            ok=True,
            detail="stopped (SIGKILL after timeout)",
            pid=target_pid,
        )
    return ActionResult(
        ok=False,
        detail=f"SIGKILL sent but port still bound after 2s (pid={target_pid})",
        pid=target_pid,
    )


def restart(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """`stop` then `start`. New spawn uses current `declaration.command`."""
    # Detect drift before stop (so we can log against the existing log file).
    record = _pid.read(declaration.name, declaration.port)
    if record is not None and tuple(record.argv) != tuple(declaration.command or ()):
        try:
            log_path = path_for(declaration.name)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "ab") as logf:
                logf.write(
                    (
                        f"\n=== {datetime.now(timezone.utc).isoformat()}: "
                        f"argv changed since last start ===\n"
                        f"prev: {list(record.argv)}\n"
                        f"cur:  {list(declaration.command or [])}\n"
                    ).encode()
                )
        except OSError:
            pass

    stop_result = stop(detection, declaration)
    if not stop_result.ok:
        # Couldn't stop — surface that error; don't try to start on top.
        return stop_result

    # Stop succeeded (or was a no-op). Pause briefly to let the OS reclaim
    # the port before we start a fresh listener.
    time.sleep(0.05)
    return start(detection, declaration)
