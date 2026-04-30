"""Tests for `command.stop` and `command.restart`.

These tests don't actually spawn processes — they monkey-patch
``command.KILL`` (the os.kill indirection) and the reprobe loop to
simulate the success / timeout / argv-mismatch paths.
"""

from __future__ import annotations

import signal

import pytest

from auntiepypi._actions import _pid, command
from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._reprobe import ReprobeResult
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection


def _detection(port: int) -> Detection:
    return Detection(
        name="lc",
        flavor="pypiserver",
        host="127.0.0.1",
        port=port,
        url=f"http://127.0.0.1:{port}/",
        status="up",
        source="declared",
    )


def _spec(port: int, command_argv: tuple[str, ...] = ("pypi-server", "run")) -> ServerSpec:
    return ServerSpec(
        name="lc",
        flavor="pypiserver",
        host="127.0.0.1",
        port=port,
        managed_by="command",
        command=command_argv,
    )


@pytest.fixture
def fake_kill(monkeypatch):
    """Capture (pid, signal) tuples instead of really signalling."""
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(command, "KILL", lambda pid, sig: calls.append((pid, sig)))
    return calls


def _patch_probe(monkeypatch, statuses):
    """Make `command.probe` return successive statuses from `statuses`."""
    it = iter(statuses)

    def fake_probe(detection, *, desired="up", budget_seconds=5.0, **_kw):
        try:
            return ReprobeResult(status=next(it))
        except StopIteration:
            # Repeat the last status forever
            return ReprobeResult(status=statuses[-1])

    monkeypatch.setattr(command, "probe", fake_probe)


# --------- happy paths ---------


def test_stop_clean_path_sigterm(tmp_path, monkeypatch, fake_kill):
    """PID file present, SIGTERM lands, port goes down on first reprobe."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    # _pid.read calls os.kill(pid, 0) for liveness; pretend it's alive
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)
    _patch_probe(monkeypatch, ["down"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert "stopped (SIGTERM)" in result.detail
    assert fake_kill == [(12345, signal.SIGTERM)]
    assert _pid.read("lc") is None  # PID file cleared


def test_stop_sigkill_escalation(tmp_path, monkeypatch, fake_kill):
    """SIGTERM lands but port is still bound; SIGKILL escalation; eventually down."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)
    # First probe (SIGTERM grace): still up. Second probe (post-SIGKILL): down.
    _patch_probe(monkeypatch, ["up", "down"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert "SIGKILL" in result.detail
    assert fake_kill == [(12345, signal.SIGTERM), (12345, signal.SIGKILL)]


def test_stop_already_stopped_no_pid_no_listener(tmp_path, monkeypatch, fake_kill):
    """No PID file, port-walk returns nothing, port is down → idempotent success."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: None)
    _patch_probe(monkeypatch, ["down"])  # port already down

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert result.detail == "already stopped"
    assert fake_kill == []  # no signal sent


def test_stop_argv_mismatch_refuses(tmp_path, monkeypatch, fake_kill):
    """No PID file but the port is up — refuse to kill (some other process)."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: None)
    # Port-walk finds nothing whose argv matches; reprobe says still up.
    _patch_probe(monkeypatch, ["up"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is False
    assert "does not match declaration" in result.detail
    assert "refusing to kill" in result.detail
    assert fake_kill == []


def test_stop_port_walk_finds_pid_when_no_pid_file(tmp_path, monkeypatch, fake_kill):
    """No PID file, port-walk returns a PID → kill it."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: 9876)
    _patch_probe(monkeypatch, ["down"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert "stopped (SIGTERM) (found via port-walk)" in result.detail
    assert fake_kill == [(9876, signal.SIGTERM)]


def test_stop_stale_pid_then_no_listener_is_already_stopped(tmp_path, monkeypatch, fake_kill):
    """PID file references a dead PID; no port-walk match; port down → already stopped."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    # Write a stale PID file. _pid.read with _is_alive=False clears it.
    _pid.write("lc", pid=2_000_000_000, argv=["x"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: False)
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: None)
    _patch_probe(monkeypatch, ["down"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert result.detail == "already stopped"
    assert fake_kill == []


def test_stop_sigterm_race_lookuperror(tmp_path, monkeypatch):
    """Process dies between read() and kill() — ProcessLookupError → success."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)

    def kill_raises_lookup(pid, sig):
        raise ProcessLookupError()

    monkeypatch.setattr(command, "KILL", kill_raises_lookup)

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is True
    assert "race" in result.detail


def test_stop_sigterm_oserror_returns_failure(tmp_path, monkeypatch):
    """An unexpected OSError from kill() (e.g. EPERM) is reported as failure."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)

    def kill_raises_perm(pid, sig):
        raise PermissionError("not your process")

    monkeypatch.setattr(command, "KILL", kill_raises_perm)

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is False
    assert "SIGTERM failed" in result.detail


def test_stop_sigkill_still_bound_returns_failure(tmp_path, monkeypatch, fake_kill):
    """SIGKILL sent but port still bound after grace → failure."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)
    # Both reprobe windows return "up" — port never unbinds.
    _patch_probe(monkeypatch, ["up", "up"])

    result = command.stop(_detection(8080), _spec(8080))
    assert result.ok is False
    assert "SIGKILL sent but port still bound" in result.detail


# --------- restart ---------


def test_restart_clean(tmp_path, monkeypatch, fake_kill):
    """restart: stop succeeds, start succeeds."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)
    _patch_probe(monkeypatch, ["down"])  # stop's reprobe sees down

    # Stub command.start so restart doesn't actually spawn anything.
    monkeypatch.setattr(
        command,
        "start",
        lambda det, decl: ActionResult(ok=True, detail="started", pid=99999),
    )

    result = command.restart(_detection(8080), _spec(8080))
    assert result.ok is True
    assert result.detail == "started"
    assert fake_kill == [(12345, signal.SIGTERM)]


def test_restart_when_not_running_acts_like_start(tmp_path, monkeypatch, fake_kill):
    """restart with no PID file + no listener: stop is a no-op; start runs."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: None)
    _patch_probe(monkeypatch, ["down", "down"])

    started = {}

    def fake_start(det, decl):
        started["called"] = True
        return ActionResult(ok=True, detail="started", pid=999)

    monkeypatch.setattr(command, "start", fake_start)

    result = command.restart(_detection(8080), _spec(8080))
    assert result.ok is True
    assert started.get("called") is True


def test_restart_logs_argv_drift(tmp_path, monkeypatch, fake_kill):
    """When sidecar argv differs from current, restart writes a drift line to the log."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _pid.write("lc", pid=12345, argv=["pypi-server", "run", "-p", "8080"], port=8080)
    monkeypatch.setattr("auntiepypi._actions._pid._is_alive", lambda pid: True)
    _patch_probe(monkeypatch, ["down"])
    monkeypatch.setattr(
        command,
        "start",
        lambda det, decl: ActionResult(ok=True, detail="started", pid=99999),
    )

    # Spec's command differs from sidecar.
    new_spec = _spec(8080, command_argv=("pypi-server", "run", "-p", "9090"))
    result = command.restart(_detection(8080), new_spec)
    assert result.ok is True

    log = (tmp_path / "auntiepypi" / "lc.log").read_text()
    assert "argv changed since last start" in log
    assert "9090" in log


def test_restart_aborts_when_stop_fails(tmp_path, monkeypatch):
    """If stop returns ok=False (e.g. argv mismatch), restart bails without starting."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.setattr(_pid, "find_by_port", lambda *a, **kw: None)
    _patch_probe(monkeypatch, ["up"])  # port up but no PID/argv match → refuse

    started = {"called": False}

    def fake_start(det, decl):
        started["called"] = True
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(command, "start", fake_start)

    result = command.restart(_detection(8080), _spec(8080))
    assert result.ok is False
    assert "refusing to kill" in result.detail
    assert started["called"] is False
