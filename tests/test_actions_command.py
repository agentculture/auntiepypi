"""Tests for `command`-strategy: detached Popen + sync re-probe + log capture."""

from __future__ import annotations

import os
import signal
import socket
import sys
from pathlib import Path

from auntiepypi._actions.command import start
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _detection(port: int) -> Detection:
    return Detection(
        name="test",
        flavor="pypiserver",
        host="127.0.0.1",
        port=port,
        url=f"http://127.0.0.1:{port}/",
        status="down",
        source="declared",
    )


def _spec(name: str, port: int, command: tuple[str, ...]) -> ServerSpec:
    return ServerSpec(
        name=name,
        flavor="pypiserver",
        host="127.0.0.1",
        port=port,
        managed_by="command",
        command=command,
    )


def test_command_happy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    port = _free_port()
    cmd = (sys.executable, "-m", "tests.fixtures.fake_pypiserver", str(port))
    detection = _detection(port)
    spec = _spec("test", port, cmd)
    result = None
    try:
        result = start(detection, spec)
        assert result.ok, f"expected ok=True, got {result}"
        assert result.detail == "started"
        assert result.log_path is not None
        assert result.pid is not None
        assert Path(result.log_path).exists()
    finally:
        if result and result.pid:
            try:
                # Test cleanup signal targeting a child we ourselves spawned (PID
                # captured from Popen above); not arbitrary signal injection.
                os.killpg(os.getpgid(result.pid), signal.SIGTERM)  # NOSONAR python:S4828
            except ProcessLookupError:
                pass


def test_command_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    port = _free_port()
    spec = _spec("missing", port, ("definitely_not_a_real_binary_42",))
    result = start(_detection(port), spec)
    assert result.ok is False
    assert "not found" in result.detail


def test_command_exits_immediately(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    port = _free_port()
    spec = _spec("badexit", port, (sys.executable, "-c", "import sys; sys.exit(1)"))
    result = start(_detection(port), spec)
    assert result.ok is False
    assert "exited immediately" in result.detail
    assert result.log_path is not None  # log was written before child exited


def test_command_spawns_but_never_binds(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    port = _free_port()
    # Sleeps longer than the re-probe budget without binding the port.
    spec = _spec("idle", port, (sys.executable, "-c", "import time; time.sleep(30)"))
    result = None
    try:
        result = start(_detection(port), spec)
        assert result.ok is False
        assert "not responding" in result.detail
        assert result.pid is not None  # pid was captured
    finally:
        if result and result.pid:
            try:
                # Test cleanup signal targeting a child we ourselves spawned (PID
                # captured from Popen above); not arbitrary signal injection.
                os.killpg(os.getpgid(result.pid), signal.SIGTERM)  # NOSONAR python:S4828
            except ProcessLookupError:
                pass


def test_command_log_path_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    port = _free_port()
    spec = _spec("logtest", port, (sys.executable, "-c", "import sys; sys.exit(0)"))
    result = start(_detection(port), spec)
    assert result.log_path is not None
    assert str(tmp_path) in result.log_path
    assert Path(result.log_path).read_bytes()  # non-empty


def test_command_not_configured_returns_error(tmp_path, monkeypatch):
    """`start` returns ok=False when declaration.command is None/empty (defensive guard).

    Upstream config validation (`_detect/_config.py`, T9) prevents this in
    practice, but `start()` is a public function with its own contract.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    spec = ServerSpec(
        name="empty",
        flavor="pypiserver",
        host="127.0.0.1",
        port=_free_port(),
        managed_by="command",
        command=None,
    )
    result = start(_detection(spec.port), spec)
    assert result.ok is False
    assert "command" in result.detail and "not set" in result.detail


def test_command_permission_denied(tmp_path, monkeypatch):
    """A non-executable file as argv[0] should raise PermissionError → mapped to ok=False."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    # Create a file with no execute bit
    fake_bin = tmp_path / "no_exec_bit"
    fake_bin.write_text("#!/usr/bin/env true\n")
    fake_bin.chmod(0o644)  # readable but not executable
    port = _free_port()
    spec = _spec("noperm", port, (str(fake_bin),))
    result = start(_detection(port), spec)
    assert result.ok is False
    assert "permission denied" in result.detail.lower()
