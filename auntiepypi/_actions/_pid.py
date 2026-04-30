"""PID-file + sidecar tracking for `managed_by=command` lifecycle.

Files cluster with the v0.4.0 log file at
``$XDG_STATE_HOME/auntiepypi/<slug>.{log,pid,json}`` (slug derivation
reuses :func:`auntiepypi._actions._logs.slugify`).

- ``<slug>.pid`` — raw integer PID (newline-terminated text).
- ``<slug>.json`` — sidecar with pid/argv/started_at/port for `down`'s
  argv-match heuristic + diagnostics.

Atomic writes via ``tempfile.mkstemp`` + ``os.replace`` to avoid the
SonarCloud S2083 path-traversal class that bit ``_config_edit`` in v0.4.0.

``find_by_port`` is the Linux-only fallback for ``command.stop`` when
no PID file exists (e.g. server was started outside ``auntie up``).
Non-Linux platforms get None — documented degradation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from auntiepypi._actions._logs import slugify, state_root
from auntiepypi._detect._proc import (
    _inodes_for_pid,
    parse_proc_net_tcp,
    scan_proc_root,
)

_PROC_DEFAULT = Path("/proc")


@dataclass(frozen=True)
class PidRecord:
    """Parsed contents of ``<slug>.pid`` + ``<slug>.json``."""

    pid: int
    argv: tuple[str, ...]
    started_at: str  # ISO 8601 UTC
    port: int


def _pid_path(name: str) -> Path:
    return state_root() / f"{slugify(name)}.pid"


def _sidecar_path(name: str) -> Path:
    return state_root() / f"{slugify(name)}.json"


def _atomic_write(target: Path, payload: bytes) -> None:
    """Write `payload` to `target` atomically: tempfile → fsync → os.replace."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f"{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target)
    except OSError:
        # Best-effort cleanup of the temp file if replace fails
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write(name: str, *, pid: int, argv: Sequence[str], port: int) -> None:
    """Write ``<name>.pid`` and ``<name>.json`` atomically."""
    started_at = datetime.now(timezone.utc).isoformat()
    sidecar = {
        "pid": pid,
        "argv": list(argv),
        "started_at": started_at,
        "port": port,
    }
    _atomic_write(_sidecar_path(name), json.dumps(sidecar).encode("utf-8"))
    _atomic_write(_pid_path(name), f"{pid}\n".encode("ascii"))


def _is_alive(pid: int) -> bool:
    """Probe liveness via ``os.kill(pid, 0)``. ESRCH → dead. EPERM → live but not ours."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read(name: str) -> Optional[PidRecord]:
    """Return the parsed record, or None if absent / stale (cleans up stale)."""
    pid_path = _pid_path(name)
    sidecar_path = _sidecar_path(name)
    try:
        pid_text = pid_path.read_text(encoding="ascii").strip()
    except OSError:
        return None
    try:
        pid = int(pid_text)
    except ValueError:
        clear(name)
        return None

    try:
        sidecar_raw = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        sidecar = {}
    else:
        try:
            sidecar = json.loads(sidecar_raw)
        except json.JSONDecodeError:
            sidecar = {}

    if not _is_alive(pid):
        clear(name)
        return None

    argv_list = sidecar.get("argv") or []
    return PidRecord(
        pid=pid,
        argv=tuple(str(a) for a in argv_list),
        started_at=str(sidecar.get("started_at") or ""),
        port=int(sidecar.get("port") or 0),
    )


def clear(name: str) -> None:
    """Delete ``<name>.pid`` and ``<name>.json``. Idempotent."""
    for p in (_pid_path(name), _sidecar_path(name)):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def _argv_matches(discovered: Sequence[str], expected: Sequence[str]) -> bool:
    """Heuristic argv match for the port-walk fallback.

    True iff:
    1. ``basename(discovered[0]) == basename(expected[0])``, AND
    2. every non-flag token in `expected` (skipping tokens starting with
       '-') appears somewhere in `discovered`.

    The flag-skipping rule is what lets ``["pypi-server","run","-p","8080","."]``
    match against a discovered argv that uses ``--port 8080`` instead of ``-p``.
    """
    if not discovered or not expected:
        return False
    if os.path.basename(discovered[0]) != os.path.basename(expected[0]):
        return False
    discovered_set = set(discovered)
    for tok in expected[1:]:
        if tok.startswith("-"):
            continue
        if tok not in discovered_set:
            return False
    return True


def _cmdline_for_pid(proc_root: Path, pid: int) -> tuple[str, ...]:
    """Read ``/proc/<pid>/cmdline``; return argv tuple or empty."""
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ()
    parts = raw.split(b"\x00")
    return tuple(p.decode("utf-8", errors="replace") for p in parts if p)


def find_by_port(
    port: int,
    *,
    expected_argv: Sequence[str],
    proc_root: Optional[Path] = None,
) -> Optional[int]:
    """Linux-only: PID of the listener on `port` whose argv matches `expected_argv`.

    Returns None on non-Linux, no listener, or argv mismatch. The argv
    match (`_argv_matches`) prevents accidentally killing an unrelated
    process bound to the same port.
    """
    if proc_root is None and sys.platform != "linux":
        return None
    root = proc_root if proc_root is not None else _PROC_DEFAULT
    if not root.is_dir():
        return None

    listeners = parse_proc_net_tcp(root / "net" / "tcp")
    if not listeners:
        return None
    # Invert: port -> inode (we want to find the inode for OUR port)
    target_inodes = {inode for inode, p in listeners.items() if p == port}
    if not target_inodes:
        return None

    # Walk every PID whose fd/* contains one of those inodes
    try:
        entries = list(root.iterdir())
    except OSError:
        return None
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if not (target_inodes & _inodes_for_pid(entry)):
            continue
        argv = _cmdline_for_pid(root, pid)
        if _argv_matches(argv, expected_argv):
            return pid
    return None


# Re-export for tests that want to spy on the underlying scanner.
__all__ = [
    "PidRecord",
    "clear",
    "find_by_port",
    "read",
    "scan_proc_root",
    "write",
]
