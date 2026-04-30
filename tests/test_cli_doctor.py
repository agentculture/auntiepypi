"""Tests for the v0.4.0 `auntie doctor` rewrite.

Doctor consumes `_detect/.detect_all` (same source as `overview`),
groups detections into action classes, and emits a structured payload
with diagnosis + remediation per entry.

This file builds up incrementally across plan tasks 11/12/13/14:
- T11: dry-run output for declared / half-supervised / scan-found / ambiguous
- T12: --apply path with FakeRunner
- T13: --decide handling for duplicates
- T14: JSON envelope shape
"""

from __future__ import annotations

import json  # noqa: F401  # used in T12-T14
from dataclasses import dataclass
from pathlib import Path

import pytest

from auntiepypi.cli._commands.doctor import cmd_doctor
from auntiepypi.cli._errors import EXIT_SUCCESS, AfiError


def _make_args(**overrides):
    @dataclass
    class _Args:
        target: str | None = None
        apply: bool = False
        decide: list[str] | None = None
        json: bool = False  # noqa: F811  # shadows json import; both used in T12-T14

    a = _Args()
    for k, v in overrides.items():
        setattr(a, k, v)
    return a


def _write_pyproject(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body)
    return p


def _no_servers_anywhere(monkeypatch):
    """Patch `_detect.detect_all` to return an empty list (hermetic)."""
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [],
    )


def test_doctor_dry_run_with_no_servers(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _no_servers_anywhere(monkeypatch)
    rc = cmd_doctor(_make_args())
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "auntie doctor" in out
    assert "(dry-run" in out


def test_doctor_dry_run_emits_diagnosis_for_declared_down(tmp_path, monkeypatch, capsys):
    """When detect_all reports a declared down server, output contains a diagnosis line."""
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["echo", "hi"]
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="main",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="down",
                source="declared",
                managed_by="command",
                command=("echo", "hi"),
            )
        ],
    )
    rc = cmd_doctor(_make_args())
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "main" in out
    assert "down" in out
    assert "diagnosis" in out
    assert "remediation" in out


def test_doctor_dry_run_half_supervised(tmp_path, monkeypatch, capsys):
    """A spec with managed_by=systemd-user and no `unit` is half-supervised."""
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "stale"
flavor = "devpi"
port = 3141
managed_by = "systemd-user"
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="stale",
                flavor="devpi",
                host="127.0.0.1",
                port=3141,
                url="http://127.0.0.1:3141/+api",
                status="down",
                source="declared",
                managed_by="systemd-user",
            )
        ],
    )
    rc = cmd_doctor(_make_args())
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "half-supervised" in out
    assert "unit" in out


def test_doctor_dry_run_scan_found_undeclared(tmp_path, monkeypatch, capsys):
    """A scan-found server (source=port) with no declaration emits a TOML stub."""
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="pypiserver:8080",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="up",
                source="port",
            )
        ],
    )
    rc = cmd_doctor(_make_args())
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "observed" in out
    assert "[[tool.auntiepypi.servers]]" in out
    assert 'managed_by = "manual"' in out


def test_doctor_target_drilldown(tmp_path, monkeypatch, capsys):
    """Positional TARGET narrows output to one entry."""
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "manual"

[[tool.auntiepypi.servers]]
name = "alt"
flavor = "devpi"
port = 3141
managed_by = "manual"
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="main",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="up",
                source="declared",
                managed_by="manual",
            ),
            Detection(
                name="alt",
                flavor="devpi",
                host="127.0.0.1",
                port=3141,
                url="http://127.0.0.1:3141/+api",
                status="down",
                source="declared",
                managed_by="manual",
            ),
        ],
    )
    rc = cmd_doctor(_make_args(target="main"))
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "main" in out
    assert (
        "\n  alt " not in out
    )  # server-entry line must not appear; "alt" is substring of "healthy"


def test_doctor_target_unknown_warns_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _no_servers_anywhere(monkeypatch)
    rc = cmd_doctor(_make_args(target="ghost"))
    assert rc == EXIT_SUCCESS
    err = capsys.readouterr().err
    assert "ghost" in err


def test_doctor_apply_actionable_dispatches(tmp_path, monkeypatch, capsys):
    from auntiepypi._actions._action import ActionResult
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["echo", "hi"]
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="main",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="down",
                source="declared",
                managed_by="command",
                command=("echo", "hi"),
            )
        ],
    )
    captured = {}

    def fake_dispatch(det, spec):
        captured["called"] = True
        return ActionResult(ok=True, detail="started", pid=12345)

    monkeypatch.setattr("auntiepypi.cli._commands.doctor._actions.dispatch", fake_dispatch)
    rc = cmd_doctor(_make_args(apply=True))
    assert rc == EXIT_SUCCESS
    assert captured.get("called") is True


def test_doctor_apply_actionable_failure_exits_2(tmp_path, monkeypatch):
    from auntiepypi._actions._action import ActionResult
    from auntiepypi._detect._detection import Detection
    from auntiepypi.cli._errors import EXIT_ENV_ERROR

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["false"]
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="main",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="down",
                source="declared",
                managed_by="command",
                command=("false",),
            )
        ],
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor._actions.dispatch",
        lambda det, spec: ActionResult(ok=False, detail="exited immediately"),
    )
    with pytest.raises(AfiError) as excinfo:
        cmd_doctor(_make_args(apply=True))
    assert excinfo.value.code == EXIT_ENV_ERROR


def test_doctor_apply_deletes_half_supervised(tmp_path, monkeypatch, capsys):
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    p = _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "stale"
flavor = "devpi"
port = 3141
managed_by = "systemd-user"
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="stale",
                flavor="devpi",
                host="127.0.0.1",
                port=3141,
                url="http://127.0.0.1:3141/+api",
                status="down",
                source="declared",
                managed_by="systemd-user",
            )
        ],
    )
    rc = cmd_doctor(_make_args(apply=True))
    assert rc == EXIT_SUCCESS
    text = p.read_text()
    assert "stale" not in text
    bak_files = list(tmp_path.glob("pyproject.toml.*.bak"))
    assert len(bak_files) == 1


def test_doctor_apply_no_bak_when_no_mutation(tmp_path, monkeypatch):
    """An apply session that only spawns servers (no config edits) writes no .bak."""
    from auntiepypi._actions._action import ActionResult
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
command = ["echo", "hi"]
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="main",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="down",
                source="declared",
                managed_by="command",
                command=("echo", "hi"),
            )
        ],
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor._actions.dispatch",
        lambda det, spec: ActionResult(ok=True, detail="started"),
    )
    cmd_doctor(_make_args(apply=True))
    bak_files = list(tmp_path.glob("pyproject.toml.*.bak"))
    assert bak_files == []


def test_doctor_apply_unimplemented_skips_no_exit_2(tmp_path, monkeypatch):
    from auntiepypi._detect._detection import Detection

    monkeypatch.chdir(tmp_path)
    _write_pyproject(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "dock"
flavor = "pypiserver"
port = 8080
managed_by = "docker"
dockerfile = "./Dockerfile"
""",
    )
    monkeypatch.setattr(
        "auntiepypi.cli._commands.doctor.detect_all",
        lambda *a, **kw: [
            Detection(
                name="dock",
                flavor="pypiserver",
                host="127.0.0.1",
                port=8080,
                url="http://127.0.0.1:8080/",
                status="down",
                source="declared",
                managed_by="docker",
                dockerfile="./Dockerfile",
            )
        ],
    )
    rc = cmd_doctor(_make_args(apply=True))
    assert rc == EXIT_SUCCESS
