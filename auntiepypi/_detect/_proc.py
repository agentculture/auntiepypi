"""Linux ``/proc`` scanner — opt-in via ``--proc`` or
``[tool.auntiepypi].scan_processes = true``.

On non-Linux platforms this module's ``detect()`` short-circuits to ``[]``.

What we look for:

1. Processes whose ``/proc/<pid>/comm`` or ``/proc/<pid>/cmdline``
   matches a known PyPI-server pattern.
2. The TCP port that process is listening on, by walking
   ``/proc/<pid>/fd/*`` for ``socket:[<inode>]`` links and matching the
   inode against ``/proc/net/tcp`` LISTEN entries.

Linux-only by construction. Other platforms get a documented no-op so
``--proc`` is still accepted (with a stderr note from the CLI layer).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

KNOWN_CMDLINE_PATTERNS: tuple[str, ...] = (
    "pypi-server",
    "devpi-server",
)
_PROC_DEFAULT = Path("/proc")
_LISTEN_STATE = "0A"  # TCP_LISTEN per linux/include/net/tcp_states.h


@dataclass(frozen=True)
class _ProcMatch:
    pid: int
    comm: str
    cmdline: str


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def _flavor_from_cmdline(cmdline: str) -> str:
    if "pypi-server" in cmdline:
        return "pypiserver"
    if "devpi-server" in cmdline:
        return "devpi"
    return "unknown"


def scan_proc_root(proc_root: Path) -> list[_ProcMatch]:
    """Walk ``proc_root`` for PID dirs whose cmdline matches a known pattern."""
    if not proc_root.is_dir():
        return []
    matches: list[_ProcMatch] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline_path = entry / "cmdline"
        try:
            cmdline_bytes = cmdline_path.read_bytes()
        except OSError:
            continue
        cmdline = cmdline_bytes.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        comm = (_read_text(entry / "comm") or "").strip()
        if not any(p in cmdline or p in comm for p in KNOWN_CMDLINE_PATTERNS):
            continue
        matches.append(_ProcMatch(pid=pid, comm=comm, cmdline=cmdline))
    return matches


# Column layout for /proc/net/tcp lines (after the "sl:" index column):
#   local_addr rem_addr state tx_q:rx_q tr:tm retrnsmt uid timeout inode ...
# So between `state` and `inode` there are exactly 5 tokens.
_TCP_LINE_RE = re.compile(
    r"^\s*\d+:\s+([0-9A-Fa-f]+):([0-9A-Fa-f]+)\s+[0-9A-Fa-f]+:[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)"
    r"\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+)"
)


def parse_proc_net_tcp(path: Path) -> dict[int, int]:
    """Return ``{inode: port}`` for every LISTEN socket in ``/proc/net/tcp``."""
    text = _read_text(path)
    if text is None:
        return {}
    inode_to_port: dict[int, int] = {}
    for line in text.splitlines():
        m = _TCP_LINE_RE.match(line)
        if not m:
            continue
        local_port_hex = m.group(2)
        state = m.group(3).upper()
        inode = int(m.group(4))
        if state != _LISTEN_STATE:
            continue
        port = int(local_port_hex, 16)
        if inode != 0:
            inode_to_port[inode] = port
    return inode_to_port


def _inodes_for_pid(pid_dir: Path) -> set[int]:
    """Walk ``pid_dir/fd/*`` for ``socket:[<inode>]`` links."""
    fd_dir = pid_dir / "fd"
    inodes: set[int] = set()
    try:
        fd_entries = list(fd_dir.iterdir())
    except OSError:
        return inodes
    for fd in fd_entries:
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        m = re.match(r"socket:\[(\d+)\]", target)
        if not m:
            continue
        inodes.add(int(m.group(1)))
    return inodes


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
    proc_root: Path | None = None,
) -> list[Detection]:
    """Find PyPI servers via ``/proc``. No-op when disabled or non-Linux."""
    del declared  # signature parity; this detector is independent
    if not scan_processes:
        return []
    if proc_root is None and sys.platform != "linux":
        return []
    root = proc_root if proc_root is not None else _PROC_DEFAULT
    matches = scan_proc_root(root)
    if not matches:
        return []
    listeners = parse_proc_net_tcp(root / "net" / "tcp")
    detections: list[Detection] = []
    for m in matches:
        port: int | None = None
        for inode in _inodes_for_pid(root / str(m.pid)):
            if inode in listeners:
                port = listeners[inode]
                break
        if port is None:
            continue
        flavor = _flavor_from_cmdline(m.cmdline)
        detections.append(
            Detection(
                name=f"{flavor}:{port}",
                flavor=flavor,
                host="127.0.0.1",
                port=port,
                url=f"http://127.0.0.1:{port}/",
                status="up",
                source="proc",
                pid=m.pid,
                cmdline=m.cmdline,
            )
        )
    return detections
