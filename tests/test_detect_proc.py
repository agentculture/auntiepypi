"""Tests for the /proc-based detector (Linux-only; opt-in)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._proc import (
    KNOWN_CMDLINE_PATTERNS,
    detect,
    parse_proc_net_tcp,
    scan_proc_root,
)

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc only")


def test_known_patterns_include_pypi_server() -> None:
    assert any("pypi-server" in p for p in KNOWN_CMDLINE_PATTERNS)
    assert any("devpi-server" in p for p in KNOWN_CMDLINE_PATTERNS)


def test_disabled_returns_empty() -> None:
    """scan_processes=False short-circuits."""
    assert detect(declared=[], scan_processes=False, proc_root=Path("/proc")) == []


@linux_only
def test_proc_root_missing_returns_empty(tmp_path) -> None:
    detections = detect(declared=[], scan_processes=True, proc_root=tmp_path / "no")
    assert detections == []


@linux_only
def test_scan_proc_root_finds_matching_cmdline(tmp_path) -> None:
    pid_dir = tmp_path / "1234"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("pypi-server\n")
    # cmdline uses NUL separators between argv entries
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00")
    matches = scan_proc_root(tmp_path)
    assert len(matches) == 1
    assert matches[0].pid == 1234
    assert "pypi-server" in matches[0].cmdline


@linux_only
def test_parse_proc_net_tcp_extracts_listening_pids(tmp_path) -> None:
    """0A in the state column means LISTEN; that's what we care about."""
    body = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 9999 1 ffff 100 0 0 10 0
"""
    tcp_path = tmp_path / "proc_net_tcp"
    tcp_path.write_text(body)
    listeners = parse_proc_net_tcp(tcp_path)
    assert listeners == {9999: 8080}


@linux_only
def test_full_pipeline_links_pid_to_port(tmp_path) -> None:
    """End-to-end: cmdline match + matching inode in net/tcp + fd link."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("pypi-server\n")
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    # /proc/<pid>/fd/3 -> socket:[9999]
    (fd_dir / "3").symlink_to("socket:[9999]")
    net_dir = proc / "net"
    net_dir.mkdir()
    (net_dir / "tcp").write_text(
        "  sl local rem st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 9999 1 ffff 100 0 0 10 0\n"
    )
    detections = detect(declared=[], scan_processes=True, proc_root=proc)
    assert len(detections) == 1
    d = detections[0]
    assert isinstance(d, Detection)
    assert d.pid == 1234
    assert d.port == 8080
    assert d.flavor == "pypiserver"
    assert d.source == "proc"


@linux_only
def test_no_matching_processes_returns_empty(tmp_path) -> None:
    """A /proc with no PyPI processes yields nothing."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "999"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("bash\n")
    (pid_dir / "cmdline").write_bytes(b"bash\x00")
    detections = detect(declared=[], scan_processes=True, proc_root=proc)
    assert detections == []


@linux_only
def test_process_without_listening_socket_skipped(tmp_path) -> None:
    """Match by cmdline but no socket -> skipped (no port to report)."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("pypi-server\n")
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00")
    (pid_dir / "fd").mkdir()
    net_dir = proc / "net"
    net_dir.mkdir()
    (net_dir / "tcp").write_text("\n")
    detections = detect(declared=[], scan_processes=True, proc_root=proc)
    assert detections == []
