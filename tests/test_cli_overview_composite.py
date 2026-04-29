"""Tests for the composite `agentpypi overview` (packages + servers)."""

from __future__ import annotations

import json

import pytest

from agentpypi.cli import main


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
    """Patch the consumer module's local bindings."""
    target = "agentpypi.cli._commands._packages.overview"
    monkeypatch.setattr(f"{target}.fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(f"{target}.fetch_pypistats", lambda pkg: {"data": {"last_week": 100}})
    (tmp_path / "pyproject.toml").write_text('[tool.agentpypi]\npackages = ["alpha"]\n')
    monkeypatch.chdir(tmp_path)


def test_no_arg_emits_both_categories(composite_env, capsys):
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"packages", "servers"}


def test_with_pkg_target_delegates_to_packages(composite_env, capsys):
    rc = main(["overview", "alpha", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "alpha"
    titles = {s["title"] for s in payload["sections"]}
    assert "_summary" in titles


def test_with_server_target_keeps_v0_0_1_semantics(composite_env, capsys):
    rc = main(["overview", "devpi", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Single-flavor probe — sections list contains only servers entries.
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"servers"}
    titles = {s["title"] for s in payload["sections"]}
    assert "devpi" in titles


def test_with_unknown_target_zero_target_report(composite_env, capsys):
    rc = main(["overview", "i-am-not-real", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert payload.get("note")


def test_no_arg_without_packages_config_emits_servers_only(tmp_path, monkeypatch, capsys):
    """When no [tool.agentpypi].packages is configured, composite emits only servers."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = main(["overview", "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"servers"}
    assert "no [tool.agentpypi].packages" in captured.err


def test_pkg_target_without_config_falls_through_to_zero_target(tmp_path, monkeypatch, capsys):
    """If a package-named target is given but no config exists, fall through."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = main(["overview", "some-pkg", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert payload.get("note")


def test_server_target_with_detail_field(monkeypatch, tmp_path, capsys):
    """probe_status returning a detail key should populate a detail field."""
    from agentpypi.cli._commands import overview as overview_mod

    fake_probe = {
        "name": "devpi",
        "port": 3141,
        "url": "http://x",
        "status": "down",
        "detail": "http 500",
    }
    monkeypatch.setattr(overview_mod, "probe_status", lambda p, **kw: fake_probe)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = main(["overview", "devpi", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    section = payload["sections"][0]
    field_names = {f["name"] for f in section["fields"]}
    assert "detail" in field_names
    detail_field = next(f for f in section["fields"] if f["name"] == "detail")
    assert detail_field["value"] == "http 500"
