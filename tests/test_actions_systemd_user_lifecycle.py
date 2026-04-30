"""Tests for `systemd_user.stop` and `systemd_user.restart`.

Both shell out to `systemctl --user <verb> <unit>` via the `RUN`
indirection that the v0.4.0 start path already uses.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from auntiepypi._actions import systemd_user
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection


@dataclass
class _FakeRunner:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    raise_: BaseException | None = None
    last_call: tuple = ()

    def __call__(self, *args, **kw):
        self.last_call = (args, kw)
        if self.raise_:
            raise self.raise_
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


def _spec(unit: str | None = "x.service") -> ServerSpec:
    return ServerSpec(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="systemd-user",
        unit=unit,
    )


def _det() -> Detection:
    return Detection(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="up",
        source="declared",
    )


# --------- stop ---------


def test_stop_happy_path(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user,
        "probe",
        lambda *a, **kw: type("R", (), {"status": "down", "detail": None})(),
    )

    result = systemd_user.stop(_det(), _spec())
    assert result.ok is True
    assert result.detail == "stopped"
    assert runner.last_call[0][0] == ["systemctl", "--user", "stop", "x.service"]


def test_stop_already_inactive_returns_stopped(monkeypatch):
    """systemctl returns 0 even when unit is already inactive."""
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user,
        "probe",
        lambda *a, **kw: type("R", (), {"status": "absent", "detail": None})(),
    )

    result = systemd_user.stop(_det(), _spec())
    assert result.ok is True
    assert result.detail == "stopped"


def test_stop_systemctl_nonzero(monkeypatch):
    runner = _FakeRunner(returncode=1, stderr="Failed to stop\nblah")
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.stop(_det(), _spec())
    assert result.ok is False
    assert "exit 1" in result.detail


def test_stop_systemctl_ok_but_port_still_up(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user,
        "probe",
        lambda *a, **kw: type("R", (), {"status": "up", "detail": None})(),
    )

    result = systemd_user.stop(_det(), _spec())
    assert result.ok is False
    assert "still responding" in result.detail


def test_stop_missing_unit():
    result = systemd_user.stop(_det(), _spec(unit=None))
    assert result.ok is False
    assert "unit" in result.detail


def test_stop_systemctl_not_on_path(monkeypatch):
    runner = _FakeRunner(raise_=FileNotFoundError("systemctl"))
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.stop(_det(), _spec())
    assert result.ok is False
    assert "systemctl not found" in result.detail


# --------- restart ---------


def test_restart_happy_path(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user,
        "probe",
        lambda *a, **kw: type("R", (), {"status": "up", "detail": None})(),
    )

    result = systemd_user.restart(_det(), _spec())
    assert result.ok is True
    assert result.detail == "restarted"
    assert runner.last_call[0][0] == ["systemctl", "--user", "restart", "x.service"]


def test_restart_systemctl_nonzero(monkeypatch):
    runner = _FakeRunner(returncode=2, stderr="unit not found")
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.restart(_det(), _spec())
    assert result.ok is False
    assert "exit 2" in result.detail


def test_restart_ok_but_reprobe_fails(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user,
        "probe",
        lambda *a, **kw: type("R", (), {"status": "down", "detail": None})(),
    )

    result = systemd_user.restart(_det(), _spec())
    assert result.ok is False
    assert "not responding after restart" in result.detail


def test_restart_missing_unit():
    result = systemd_user.restart(_det(), _spec(unit=None))
    assert result.ok is False
    assert "unit" in result.detail


def test_restart_timeout(monkeypatch):
    runner = _FakeRunner(raise_=subprocess.TimeoutExpired(cmd="systemctl", timeout=15))
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.restart(_det(), _spec())
    assert result.ok is False
    assert "timed out" in result.detail
