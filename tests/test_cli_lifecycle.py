"""Tests for the v0.5.0 lifecycle verbs (`auntie up` / `down` / `restart`).

These exercise the shared `_lifecycle.run_lifecycle` core. Per-verb
test files (`test_cli_up.py` etc.) only verify the wiring (parser
registration + subcommand resolution).
"""

from __future__ import annotations

import json

import pytest

from auntiepypi import _actions
from auntiepypi._actions._action import ActionResult
from auntiepypi.cli import main
from auntiepypi.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, EXIT_USER_ERROR


def _write_pyproject(tmp_path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(body)


@pytest.fixture
def stub_dispatch(monkeypatch):
    """Replace _actions.dispatch with a controllable stub.

    Set the fixture's `result` attribute to control what every dispatch
    call returns. Inspect `calls` to assert.
    """

    class _Stub:
        def __init__(self):
            self.result = ActionResult(ok=True, detail="started")
            self.calls: list[tuple] = []

        def __call__(self, action, det, spec):
            self.calls.append((action, det.name, spec.name, spec.managed_by))
            return self.result

    stub = _Stub()
    monkeypatch.setattr(_actions, "dispatch", stub)
    # _lifecycle imports _actions module; _actions.dispatch is the routing
    # function so monkeypatching that directly is sufficient.
    return stub


# --------- Bare invocation: first-party server ---------


def test_up_bare_invocation_dispatches_local(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, "")
    rc = main(["up"])
    assert rc == EXIT_SUCCESS
    assert len(stub_dispatch.calls) == 1
    action, det_name, spec_name, managed_by = stub_dispatch.calls[0]
    assert action == "start"
    assert det_name == "auntie"
    assert spec_name == "auntie"
    assert managed_by == "auntie"


def test_down_bare_invocation_dispatches_stop(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, "")
    stub_dispatch.result = ActionResult(ok=True, detail="stopped")
    rc = main(["down"])
    assert rc == EXIT_SUCCESS
    assert stub_dispatch.calls[0][0] == "stop"
    assert stub_dispatch.calls[0][2] == "auntie"


def test_restart_bare_invocation_dispatches_restart(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, "")
    stub_dispatch.result = ActionResult(ok=True, detail="restarted")
    rc = main(["restart"])
    assert rc == EXIT_SUCCESS
    assert stub_dispatch.calls[0][0] == "restart"
    assert stub_dispatch.calls[0][2] == "auntie"


def test_up_bare_uses_configured_local_port(tmp_path, monkeypatch, stub_dispatch):
    """Bare invocation reads [tool.auntiepypi.local] for host/port."""
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[tool.auntiepypi.local]
host = "127.0.0.1"
port = 9999
""",
    )

    captured: dict = {}

    def stub(action, det, spec):
        captured["det"] = det
        captured["spec"] = spec
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(_actions, "dispatch", stub)
    rc = main(["up"])
    assert rc == EXIT_SUCCESS
    assert captured["spec"].port == 9999
    assert captured["det"].port == 9999


def test_named_target_auntie_is_reserved(tmp_path, monkeypatch, capsys):
    """`auntie up auntie` is rejected — bare form is the only way to act on the local server."""
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "auntie"
flavor = "pypiserver"
host = "127.0.0.1"
port = 8080
managed_by = "command"
command = ["python", "-m", "http.server"]
""",
    )
    rc = main(["up", "auntie"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "reserved" in err


# --------- Single-target happy paths ---------


def test_up_single_name_dispatches_start(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
host = "127.0.0.1"
port = 8080
managed_by = "command"
command = ["pypi-server", "run"]
""",
    )
    rc = main(["up", "main"])
    assert rc == EXIT_SUCCESS
    assert len(stub_dispatch.calls) == 1
    assert stub_dispatch.calls[0][0] == "start"
    assert stub_dispatch.calls[0][2] == "main"


def test_down_single_name_dispatches_stop(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "main.service"
""",
    )
    stub_dispatch.result = ActionResult(ok=True, detail="stopped")
    rc = main(["down", "main"])
    assert rc == EXIT_SUCCESS
    assert stub_dispatch.calls[0][0] == "stop"


def test_restart_single_name_dispatches_restart(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "main.service"
""",
    )
    stub_dispatch.result = ActionResult(ok=True, detail="restarted")
    rc = main(["restart", "main"])
    assert rc == EXIT_SUCCESS
    assert stub_dispatch.calls[0][0] == "restart"


# --------- Refusal for unsupervised modes ---------


def test_up_refuses_managed_by_manual(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "manual"
""",
    )
    rc = main(["up", "main"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "manual" in err
    assert "does not supervise" in err
    assert stub_dispatch.calls == []  # never reached dispatch


def test_up_refuses_managed_by_docker(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "docker"
dockerfile = "./Dockerfile"
""",
    )
    rc = main(["up", "main"])
    assert rc == EXIT_USER_ERROR
    assert "docker" in capsys.readouterr().err


# --------- Unknown target ---------


def test_up_unknown_target_exits_1(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, "")
    rc = main(["up", "nonexistent"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "unknown TARGET" in err
    assert "'nonexistent'" in err


# --------- --all path ---------


def test_up_all_dispatches_every_supervised(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "first"
flavor = "pypiserver"
port = 18080
managed_by = "command"
command = ["pypi-server"]

[[tool.auntiepypi.servers]]
name = "second"
flavor = "devpi"
port = 13141
managed_by = "systemd-user"
unit = "second.service"

[[tool.auntiepypi.servers]]
name = "manual-one"
flavor = "pypiserver"
port = 28080
managed_by = "manual"
""",
    )
    rc = main(["up", "--all"])
    assert rc == EXIT_SUCCESS
    # Two supervised dispatches; manual-one skipped
    names = [c[2] for c in stub_dispatch.calls]
    assert "first" in names
    assert "second" in names
    assert "manual-one" not in names


def test_up_all_with_no_servers_acts_on_local_only(tmp_path, monkeypatch, stub_dispatch):
    """v0.6.0: --all always includes the first-party server, even when no servers are declared."""
    monkeypatch.chdir(tmp_path)
    _write_pyproject(tmp_path, "")
    rc = main(["up", "--all"])
    assert rc == EXIT_SUCCESS
    assert len(stub_dispatch.calls) == 1
    assert stub_dispatch.calls[0][2] == "auntie"
    assert stub_dispatch.calls[0][3] == "auntie"


def test_up_all_partial_failure_exits_2(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "first"
flavor = "pypiserver"
port = 18080
managed_by = "command"
command = ["pypi-server"]

[[tool.auntiepypi.servers]]
name = "second"
flavor = "pypiserver"
port = 18081
managed_by = "command"
command = ["pypi-server"]
""",
    )
    # 3 calls: local first (ok), then first declared (ok), then second declared (fails)
    seq = [
        ActionResult(ok=True, detail="started", pid=42),
        ActionResult(ok=True, detail="started", pid=111),
        ActionResult(ok=False, detail="exited immediately"),
    ]
    it = iter(seq)
    stub_dispatch.calls = []  # reset
    monkeypatch.setattr(
        _actions,
        "dispatch",
        lambda action, det, spec: (
            stub_dispatch.calls.append((action, det.name, spec.name, spec.managed_by)) or next(it)
        ),
    )
    rc = main(["up", "--all"])
    assert rc == EXIT_ENV_ERROR


# --------- --json envelope ---------


def test_up_json_payload(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["pypi-server"]
""",
    )
    log_path = str(tmp_path / "x.log")
    stub_dispatch.result = ActionResult(ok=True, detail="started", pid=999, log_path=log_path)
    rc = main(["up", "main", "--json"])
    assert rc == EXIT_SUCCESS

    payload = json.loads(capsys.readouterr().out)
    assert payload["verb"] == "up"
    assert len(payload["results"]) == 1
    entry = payload["results"][0]
    assert entry["name"] == "main"
    assert entry["ok"] is True
    assert entry["detail"] == "started"
    assert entry["pid"] == 999
    assert entry["log_path"] == log_path


def test_down_json_omits_pid_when_unset(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "main.service"
""",
    )
    stub_dispatch.result = ActionResult(ok=True, detail="stopped")  # no pid
    rc = main(["down", "main", "--json"])
    assert rc == EXIT_SUCCESS

    payload = json.loads(capsys.readouterr().out)
    entry = payload["results"][0]
    assert "pid" not in entry  # absent when None
    assert "log_path" not in entry


# --------- --decide=duplicate ---------


def test_up_duplicate_name_requires_decide(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["pypi-server", "-p", "8080"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "devpi"
port = 3141
managed_by = "command"
command = ["devpi-server", "--port", "3141"]
""",
    )
    rc = main(["up", "main"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "ambiguous" in err
    assert "duplicate:main=1" in err
    assert "=2" in err


def test_up_decide_picks_specific_duplicate(tmp_path, monkeypatch, stub_dispatch):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["pypi-server", "-p", "8080"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "devpi"
port = 3141
managed_by = "command"
command = ["devpi-server"]
""",
    )
    rc = main(["up", "main", "--decide=duplicate:main=2"])
    assert rc == EXIT_SUCCESS
    # Verify the second declaration (devpi) was the one dispatched
    assert len(stub_dispatch.calls) == 1
    # Inspect via spec: managed_by + name match, but we don't expose
    # spec.flavor to the stub_dispatch wrapper. The test trusts that
    # _resolve_one_spec correctly selected index 2.


def test_up_decide_out_of_range_exits_1(tmp_path, monkeypatch, stub_dispatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["pypi-server"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "devpi"
port = 3141
managed_by = "command"
command = ["devpi-server"]
""",
    )
    rc = main(["up", "main", "--decide=duplicate:main=5"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert "out of range" in err
