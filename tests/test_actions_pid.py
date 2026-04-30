"""Tests for `auntiepypi._actions._pid` — PID file + sidecar + port-walk fallback."""

from __future__ import annotations

import os
import sys

import pytest

from auntiepypi._actions import _pid
from auntiepypi._actions._pid import PidRecord, _argv_matches

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc only")


# --------- write / read / clear roundtrip ---------


def test_write_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("main", pid=os.getpid(), argv=["pypi-server", "-p", "8080"], port=8080)

    record = _pid.read("main", 8080)
    assert record is not None
    assert record.pid == os.getpid()
    assert record.argv == ("pypi-server", "-p", "8080")
    assert record.port == 8080
    assert record.started_at  # ISO 8601 string, non-empty


def test_read_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert _pid.read("nonexistent", 1) is None


def test_read_detects_stale_pid_and_clears(tmp_path, monkeypatch):
    """When the PID is dead, read() returns None AND removes the files."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    fake_pid = 2_000_000_000  # essentially guaranteed not to exist
    _pid.write("ghost", pid=fake_pid, argv=["x"], port=1)

    pid_file = tmp_path / "auntiepypi" / "ghost_1.pid"
    sidecar = tmp_path / "auntiepypi" / "ghost_1.json"
    assert pid_file.exists() and sidecar.exists()

    assert _pid.read("ghost", 1) is None
    assert not pid_file.exists()
    assert not sidecar.exists()


def test_read_with_garbage_pid_file_returns_none_and_clears(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state_dir = tmp_path / "auntiepypi"
    state_dir.mkdir()
    (state_dir / "junk_1.pid").write_text("not-a-number\n")
    (state_dir / "junk_1.json").write_text("{}")

    assert _pid.read("junk", 1) is None
    assert not (state_dir / "junk_1.pid").exists()


def test_read_tolerates_missing_sidecar(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state_dir = tmp_path / "auntiepypi"
    state_dir.mkdir()
    (state_dir / "lone_1.pid").write_text(f"{os.getpid()}\n")
    # No sidecar.

    record = _pid.read("lone", 1)
    assert record is not None
    assert record.pid == os.getpid()
    assert record.argv == ()
    assert record.port == 0


def test_read_corrupt_sidecar_port_returns_none(tmp_path, monkeypatch):
    """A non-integer port in the sidecar JSON → invalid record, cleaned up."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state_dir = tmp_path / "auntiepypi"
    state_dir.mkdir()
    (state_dir / "bad_1.pid").write_text(f"{os.getpid()}\n")
    (state_dir / "bad_1.json").write_text('{"port": "not-an-int", "argv": ["x"]}')

    assert _pid.read("bad", 1) is None
    assert not (state_dir / "bad_1.pid").exists()


def test_read_sidecar_port_mismatch_returns_none(tmp_path, monkeypatch):
    """Sidecar's port disagrees with the requested port → invalid (treats as stale)."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    state_dir = tmp_path / "auntiepypi"
    state_dir.mkdir()
    (state_dir / "main_8080.pid").write_text(f"{os.getpid()}\n")
    # Sidecar says port=9999 but file is keyed on 8080
    import json as _json

    (state_dir / "main_8080.json").write_text(
        _json.dumps({"pid": os.getpid(), "argv": ["x"], "port": 9999, "started_at": "x"})
    )

    assert _pid.read("main", 8080) is None


def test_duplicate_names_with_different_ports_dont_collide(tmp_path, monkeypatch):
    """Two declarations sharing `name` but on different ports keep separate state."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    pid_a = os.getpid()
    pid_b = os.getpid()  # not real distinct processes; we just want distinct records
    _pid.write("main", pid=pid_a, argv=["server-a"], port=8080)
    _pid.write("main", pid=pid_b, argv=["server-b"], port=9090)

    rec_a = _pid.read("main", 8080)
    rec_b = _pid.read("main", 9090)
    assert rec_a is not None and tuple(rec_a.argv) == ("server-a",)
    assert rec_b is not None and tuple(rec_b.argv) == ("server-b",)


def test_clear_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.clear("never-written", 1)  # no exception
    _pid.write("real", pid=os.getpid(), argv=["x"], port=1)
    _pid.clear("real", 1)
    _pid.clear("real", 1)  # idempotent
    assert _pid.read("real", 1) is None


def test_write_uses_slugified_name(tmp_path, monkeypatch):
    """Names with unsafe chars are slugified before becoming filenames."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("Main/Pypi:1", pid=os.getpid(), argv=["x"], port=8080)

    state_dir = tmp_path / "auntiepypi"
    files = sorted(p.name for p in state_dir.iterdir())
    # _logs.slugify lowercases + replaces non-[a-z0-9._-] with '_'.
    # Filename also includes the port for duplicate-name disambiguation.
    assert "main_pypi_1_8080.pid" in files
    assert "main_pypi_1_8080.json" in files


# --------- _argv_matches helper ---------


def test_argv_matches_exact():
    assert _argv_matches(
        ["pypi-server", "run", "-p", "8080", "."],
        ["pypi-server", "run", "-p", "8080", "."],
    )


def test_argv_matches_basename_equality():
    """argv[0] basename, not full path, is what matters."""
    assert _argv_matches(
        ["/usr/local/bin/pypi-server", "run"],
        ["pypi-server", "run"],
    )


def test_argv_matches_skips_flag_tokens_in_expected():
    """A flag-style token in expected ('-p') is skipped in the membership check."""
    assert _argv_matches(
        ["pypi-server", "run", "8080"],  # discovered, no -p
        ["pypi-server", "run", "-p", "8080"],  # expected has -p (skipped)
    )


def test_argv_matches_rejects_different_executable():
    assert not _argv_matches(["nginx", "-c", "/etc/nginx.conf"], ["pypi-server"])


def test_argv_matches_rejects_missing_token():
    assert not _argv_matches(
        ["pypi-server", "run"],
        ["pypi-server", "run", ".", "-p", "8080"],
    )


def test_argv_matches_rejects_empty():
    assert not _argv_matches([], ["pypi-server"])
    assert not _argv_matches(["pypi-server"], [])


# --------- find_by_port ---------


def test_find_by_port_returns_none_on_non_linux(monkeypatch):
    """Non-Linux platforms get None without hitting /proc."""
    monkeypatch.setattr(sys, "platform", "darwin")
    assert _pid.find_by_port(8080, expected_argv=["pypi-server"]) is None


def test_find_by_port_returns_none_when_no_listener(tmp_path):
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    (proc / "net" / "tcp").write_text("\n")
    assert _pid.find_by_port(8080, expected_argv=["pypi-server"], proc_root=proc) is None


def test_find_by_port_returns_none_when_proc_root_missing(tmp_path):
    assert (
        _pid.find_by_port(
            8080,
            expected_argv=["pypi-server"],
            proc_root=tmp_path / "does-not-exist",
        )
        is None
    )


@linux_only
def test_find_by_port_happy_path(tmp_path):
    """argv match → returns PID."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00.\x00")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    (fd_dir / "3").symlink_to("socket:[9999]")
    net_dir = proc / "net"
    net_dir.mkdir()
    # 1F90 = 8080 in hex
    (net_dir / "tcp").write_text(
        "  sl local rem st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000  1000        0 9999 1 ffff 100 0 0 10 0\n"
    )

    pid = _pid.find_by_port(
        8080,
        expected_argv=["pypi-server", "run", "-p", "8080", "."],
        proc_root=proc,
    )
    assert pid == 1234


@linux_only
def test_find_by_port_argv_mismatch_returns_none(tmp_path):
    """Listener exists on port but its argv doesn't match expected → None (footgun guard)."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "cmdline").write_bytes(b"nginx\x00-c\x00/etc/nginx.conf\x00")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    (fd_dir / "3").symlink_to("socket:[9999]")
    net_dir = proc / "net"
    net_dir.mkdir()
    (net_dir / "tcp").write_text(
        "  sl local rem st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000  1000        0 9999 1 ffff 100 0 0 10 0\n"
    )

    pid = _pid.find_by_port(
        8080,
        expected_argv=["pypi-server", "run", "-p", "8080"],
        proc_root=proc,
    )
    assert pid is None


@linux_only
def test_find_by_port_wrong_port_returns_none(tmp_path):
    """Listener bound to port other than asked → no match."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    (fd_dir / "3").symlink_to("socket:[9999]")
    net_dir = proc / "net"
    net_dir.mkdir()
    # 0050 = 80, not 8080
    (net_dir / "tcp").write_text(
        "  sl local rem st\n"
        "   0: 0100007F:0050 00000000:0000 0A 00000000:00000000 00:00000000 "
        "00000000  1000        0 9999 1 ffff 100 0 0 10 0\n"
    )

    assert _pid.find_by_port(8080, expected_argv=["pypi-server", "run"], proc_root=proc) is None


def test_pidrecord_is_frozen():
    """Frozen dataclass: assignment raises FrozenInstanceError."""
    from dataclasses import FrozenInstanceError

    rec = PidRecord(pid=1, argv=("x",), started_at="2026-04-30T00:00:00+00:00", port=8080)
    with pytest.raises(FrozenInstanceError):
        rec.pid = 2  # type: ignore[misc]
