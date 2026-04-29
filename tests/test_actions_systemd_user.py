"""Tests for `systemd-user`-strategy: invokes `systemctl --user start <unit>` + re-probe.

Tests monkey-patch `RUN` (the subprocess.run indirection) — no real
systemd interaction.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from auntiepypi._actions import systemd_user
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection


@dataclass
class _FakeRunner:
    """Programmable subprocess.run replacement."""

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
        name="test",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="systemd-user",
        unit=unit,
    )


def _det() -> Detection:
    return Detection(
        name="test",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="down",
        source="declared",
    )


def test_systemd_user_happy_path(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user, "probe", lambda *a, **kw: type("R", (), {"status": "up", "detail": None})()
    )

    result = systemd_user.apply(_det(), _spec())
    assert result.ok is True
    assert result.detail == "started"
    assert runner.last_call[0][0] == ["systemctl", "--user", "start", "x.service"]


def test_systemd_user_systemctl_nonzero(monkeypatch):
    runner = _FakeRunner(returncode=5, stderr="Failed to start unit\nblah")
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user, "probe", lambda *a, **kw: type("R", (), {"status": "down", "detail": None})()
    )

    result = systemd_user.apply(_det(), _spec())
    assert result.ok is False
    assert "exit 5" in result.detail
    assert "Failed to start" in result.detail


def test_systemd_user_systemctl_ok_but_reprobe_fails(monkeypatch):
    runner = _FakeRunner(returncode=0)
    monkeypatch.setattr(systemd_user, "RUN", runner)
    monkeypatch.setattr(
        systemd_user, "probe", lambda *a, **kw: type("R", (), {"status": "down", "detail": None})()
    )

    result = systemd_user.apply(_det(), _spec())
    assert result.ok is False
    assert "systemctl ok but server not responding" in result.detail


def test_systemd_user_not_on_path(monkeypatch):
    runner = _FakeRunner(raise_=FileNotFoundError("systemctl"))
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.apply(_det(), _spec())
    assert result.ok is False
    assert "systemctl not found" in result.detail


def test_systemd_user_timeout(monkeypatch):
    runner = _FakeRunner(raise_=subprocess.TimeoutExpired(cmd="systemctl", timeout=15))
    monkeypatch.setattr(systemd_user, "RUN", runner)

    result = systemd_user.apply(_det(), _spec())
    assert result.ok is False
    assert "timed out" in result.detail


def test_systemd_user_missing_unit(monkeypatch):
    result = systemd_user.apply(_det(), _spec(unit=None))
    assert result.ok is False
    assert "unit" in result.detail
