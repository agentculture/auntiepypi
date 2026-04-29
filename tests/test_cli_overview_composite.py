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
    from agentpypi._rubric import _sources

    monkeypatch.setattr(_sources, "fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(_sources, "fetch_pypistats", lambda pkg: {"data": {"last_week": 100}})
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
