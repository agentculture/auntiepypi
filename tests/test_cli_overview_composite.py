"""Tests for the composite ``auntie overview`` (packages + detected servers)."""

from __future__ import annotations

import json

import pytest

from auntiepypi._detect._detection import Detection
from auntiepypi.cli import main


def _good_pypi(name="x"):
    return {
        "info": {
            "name": name,
            "version": "1.0.0",
            "license": "MIT",
            "requires_python": ">=3.10",
            "project_urls": {"Homepage": "h", "Source": "s"},
            "description": "y" * 250,
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        },
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2026-04-25T00:00:00Z", "yanked": False}],
            "0.9.0": [{"upload_time_iso_8601": "2026-04-15T00:00:00Z", "yanked": False}],
        },
        "urls": [{"packagetype": "bdist_wheel"}, {"packagetype": "sdist"}],
    }


@pytest.fixture
def composite_env(tmp_path, monkeypatch):
    target = "auntiepypi._packages_view"
    monkeypatch.setattr(f"{target}.fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(f"{target}.fetch_pypistats", lambda pkg: {"data": {"last_week": 100}})
    (tmp_path / "pyproject.toml").write_text('[tool.auntiepypi]\npackages = ["alpha"]\n')
    monkeypatch.chdir(tmp_path)


def _stub_detect(detections):
    """Return a stub that ignores its config arg and returns `detections`."""
    return lambda cfg: list(detections)


def test_no_arg_emits_both_categories(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main",
            flavor="pypiserver",
            host="127.0.0.1",
            port=8080,
            url="http://127.0.0.1:8080/",
            status="up",
            source="declared",
        ),
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections))
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"packages", "servers"}
    server_titles = {s["title"] for s in payload["sections"] if s["category"] == "servers"}
    assert "main" in server_titles


def test_declared_servers_show_up_in_composite(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main",
            flavor="pypiserver",
            host="127.0.0.1",
            port=8081,
            url="http://127.0.0.1:8081/",
            status="up",
            source="declared",
            managed_by="systemd-user",
            unit="pypi.service",
        ),
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections))
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    server = next(s for s in payload["sections"] if s["title"] == "main")
    field_map = {f["name"]: f["value"] for f in server["fields"]}
    assert field_map["source"] == "declared"
    assert field_map["managed_by"] == "systemd-user"
    assert field_map["unit"] == "pypi.service"


def test_target_resolves_to_declared_name(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main",
            flavor="pypiserver",
            host="127.0.0.1",
            port=8080,
            url="http://127.0.0.1:8080/",
            status="up",
            source="declared",
        ),
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections))
    rc = main(["overview", "main", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "main"
    titles = {s["title"] for s in payload["sections"]}
    assert titles == {"main"}


def test_target_resolves_to_bare_flavor_alias(composite_env, capsys, monkeypatch) -> None:
    """`auntie overview pypiserver` resolves to the first pypiserver detection."""
    detections = [
        Detection(
            name="alpha",
            flavor="devpi",
            host="127.0.0.1",
            port=3141,
            url="http://127.0.0.1:3141/+api",
            status="up",
            source="declared",
        ),
        Detection(
            name="beta",
            flavor="pypiserver",
            host="127.0.0.1",
            port=8080,
            url="http://127.0.0.1:8080/",
            status="up",
            source="declared",
        ),
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections))
    rc = main(["overview", "pypiserver", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "beta"
    assert {s["title"] for s in payload["sections"]} == {"beta"}


def test_target_resolves_to_auto_name_with_port(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="pypiserver:8080",
            flavor="pypiserver",
            host="127.0.0.1",
            port=8080,
            url="http://127.0.0.1:8080/",
            status="up",
            source="port",
        ),
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections))
    rc = main(["overview", "pypiserver:8080", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {s["title"] for s in payload["sections"]} == {"pypiserver:8080"}


def test_target_resolves_to_package(composite_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect([]))
    rc = main(["overview", "alpha", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "alpha"
    titles = {s["title"] for s in payload["sections"]}
    assert "_summary" in titles


def test_unknown_target_zero_target_report(composite_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect([]))
    rc = main(["overview", "i-am-not-real", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert payload.get("note")


def test_no_arg_without_packages_config(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect([]))
    rc = main(["overview", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["sections"] == []
    assert "no [tool.auntiepypi].packages" in captured.err


def test_proc_flag_on_non_linux_emits_stderr_warning(composite_env, capsys, monkeypatch) -> None:
    """`--proc` on non-Linux is a no-op but must emit a stderr note."""
    monkeypatch.setattr("auntiepypi.cli._commands.overview.sys.platform", "darwin")
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect([]))
    rc = main(["overview", "--proc", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "--proc is Linux-only" in captured.err


def test_proc_flag_on_linux_emits_no_warning(composite_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr("auntiepypi.cli._commands.overview.sys.platform", "linux")
    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", _stub_detect([]))
    rc = main(["overview", "--proc", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "--proc is Linux-only" not in captured.err


def test_proc_flag_propagates_to_detect_all(composite_env, capsys, monkeypatch) -> None:
    """`--proc` overrides the config's scan_processes to True."""
    seen: list = []

    def stub(cfg):
        seen.append(cfg.scan_processes)
        return []

    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", stub)
    rc = main(["overview", "--proc", "--json"])
    assert rc == 0
    assert seen == [True]


def test_default_scan_processes_false_when_no_config(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    seen: list = []

    def stub(cfg):
        seen.append(cfg.scan_processes)
        return []

    monkeypatch.setattr("auntiepypi.cli._commands.overview.detect_all", stub)
    rc = main(["overview", "--json"])
    assert rc == 0
    assert seen == [False]


def test_malformed_servers_config_exits_user_error(tmp_path, monkeypatch, capsys) -> None:
    """Malformed [[tool.auntiepypi.servers]] -> exit 1 with a hint."""
    (tmp_path / "pyproject.toml").write_text("""\
[tool.auntiepypi]
packages = ["x"]

[[tool.auntiepypi.servers]]
flavor = "pypiserver"
port = 8080
""")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = main(["overview", "--json"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "missing 'name'" in captured.err
