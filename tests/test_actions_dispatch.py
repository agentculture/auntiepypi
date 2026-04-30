"""Tests for the `_actions` dispatch surface."""

from __future__ import annotations

from auntiepypi import _actions
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection


def _det() -> Detection:
    return Detection(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="down",
        source="declared",
    )


def test_dispatch_routes_systemd_user(monkeypatch):
    called = []
    monkeypatch.setitem(
        _actions.ACTIONS,
        "systemd-user",
        lambda d, s: (
            called.append(("systemd-user", d, s)) or _actions.ActionResult(ok=True, detail="ok")
        ),
    )
    spec = ServerSpec(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="systemd-user",
        unit="x.service",
    )
    result = _actions.dispatch(_det(), spec)
    assert result.ok is True
    assert len(called) == 1, f"expected exactly one call, got {called!r}"
    assert called[0][0] == "systemd-user"


def test_dispatch_routes_command(monkeypatch):
    called = []
    monkeypatch.setitem(
        _actions.ACTIONS,
        "command",
        lambda d, s: (called.append("command") or _actions.ActionResult(ok=True, detail="ok")),
    )
    spec = ServerSpec(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="command",
        command=("echo",),
    )
    result = _actions.dispatch(_det(), spec)
    assert result.ok is True
    assert len(called) == 1, f"expected exactly one call, got {called!r}"
    assert called == ["command"]


def test_dispatch_docker_returns_not_implemented():
    spec = ServerSpec(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="docker",
        dockerfile="./Dockerfile",
    )
    result = _actions.dispatch(_det(), spec)
    assert result.ok is False
    assert "not implemented in v0.4.0" in result.detail


def test_dispatch_compose_returns_not_implemented():
    spec = ServerSpec(
        name="t",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        managed_by="compose",
        compose="./docker-compose.yml",
    )
    result = _actions.dispatch(_det(), spec)
    assert result.ok is False
    assert "not implemented" in result.detail


def test_dispatch_manual_is_noop():
    spec = ServerSpec(
        name="t", flavor="pypiserver", host="127.0.0.1", port=8080, managed_by="manual"
    )
    result = _actions.dispatch(_det(), spec)
    assert result.ok is False  # observed-only is not "fixed"
    assert "manual" in result.detail.lower() or "not supervised" in result.detail.lower()


def test_dispatch_unset_managed_by_treated_as_manual():
    spec = ServerSpec(name="t", flavor="pypiserver", host="127.0.0.1", port=8080, managed_by=None)
    result = _actions.dispatch(_det(), spec)
    assert result.ok is False
    assert "manual" in result.detail.lower() or "not supervised" in result.detail.lower()
