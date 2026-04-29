"""Tests for `agentpypi packages overview [PKG]`."""

from __future__ import annotations

import json

import pytest

from agentpypi.cli import main


def _good_pypi(name: str = "x") -> dict:
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


def _good_stats() -> dict:
    return {"data": {"last_week": 100}}


@pytest.fixture
def patched_sources(monkeypatch):
    """Patch the consumer module's local bindings (from ... import fetch_pypi)."""
    target = "agentpypi.cli._commands._packages.overview"
    monkeypatch.setattr(f"{target}.fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(f"{target}.fetch_pypistats", lambda pkg: _good_stats())


def test_overview_no_arg_requires_config(tmp_path, monkeypatch, capsys):
    """Without [tool.agentpypi].packages, no-arg form errors with code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = main(["packages", "overview"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "tool.agentpypi" in err
    assert "hint:" in err


def test_overview_no_arg_emits_dashboard(tmp_path, monkeypatch, capsys, patched_sources):
    (tmp_path / "pyproject.toml").write_text('[tool.agentpypi]\npackages = ["alpha", "beta"]\n')
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "packages"
    assert len(payload["sections"]) == 2
    for section in payload["sections"]:
        assert section["category"] == "packages"
        assert section["light"] in {"green", "yellow", "red", "unknown"}
        names = {f["name"] for f in section["fields"]}
        assert {"version", "index", "released", "downloads_w"} <= names
        index_field = next(f for f in section["fields"] if f["name"] == "index")
        assert index_field["value"] == "pypi.org"


def test_overview_with_pkg_emits_deep_dive(tmp_path, monkeypatch, capsys, patched_sources):
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "requests", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "requests"
    titles = [s["title"] for s in payload["sections"]]
    assert titles[-1] == "_summary"
    rubric_titles = set(titles[:-1])
    assert rubric_titles == {
        "recency",
        "cadence",
        "downloads",
        "lifecycle",
        "distribution",
        "metadata",
        "versioning",
    }
    summary = payload["sections"][-1]
    assert summary["light"] in {"green", "yellow", "red", "unknown"}


def test_overview_invalid_pkg_name_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "Bad Name With Spaces"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid package name" in err.lower() or "invalid" in err.lower()


def test_overview_unknown_to_pypi_yields_unknown_section(tmp_path, monkeypatch, capsys):
    """Package that pypi.org returns 404 for: deep-dive lights all unknown."""
    from agentpypi._rubric._fetch import FetchError

    def fail_pypi(pkg):
        raise FetchError("http 404", status=404)

    target = "agentpypi.cli._commands._packages.overview"
    monkeypatch.setattr(f"{target}.fetch_pypi", fail_pypi)
    monkeypatch.setattr(
        f"{target}.fetch_pypistats",
        lambda pkg: (_ for _ in ()).throw(FetchError("http 404", status=404)),
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "ghost-package", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["sections"][-1]
    assert summary["title"] == "_summary"
    assert summary["light"] == "unknown"


def test_overview_all_fetches_fail_in_dashboard_returns_2(tmp_path, monkeypatch, capsys):
    """Dashboard mode: every package's both fetches fail → exit 2 (env error)."""
    from agentpypi._rubric._fetch import FetchError

    def fail_pypi(pkg):
        raise FetchError("fetch failed: URLError", status=None)

    def fail_stats(pkg):
        raise FetchError("fetch failed: URLError", status=None)

    target = "agentpypi.cli._commands._packages.overview"
    monkeypatch.setattr(f"{target}.fetch_pypi", fail_pypi)
    monkeypatch.setattr(f"{target}.fetch_pypistats", fail_stats)
    (tmp_path / "pyproject.toml").write_text('[tool.agentpypi]\npackages = ["alpha", "beta"]\n')
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "--json"])
    assert rc == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "packages"
    assert all(s["light"] == "unknown" for s in payload["sections"])


def test_packages_with_no_subverb_prints_help_and_exits_1(tmp_path, monkeypatch, capsys):
    """Bare `agentpypi packages` (no subverb) → help + EXIT_USER_ERROR."""
    monkeypatch.chdir(tmp_path)
    rc = main(["packages"])
    assert rc == 1
