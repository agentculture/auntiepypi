"""Tests for [tool.auntiepypi].packages loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from auntiepypi._packages_config import (
    ConfigError,
    find_pyproject,
    load_package_names,
)


def _write_toml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body)
    return p


def test_loads_simple_list(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["foo", "bar"]\n')
    assert load_package_names(tmp_path) == ["foo", "bar"]


def test_missing_table_raises(tmp_path):
    _write_toml(tmp_path, '[project]\nname = "x"\n')
    with pytest.raises(ConfigError, match="no .tool.auntiepypi..packages"):
        load_package_names(tmp_path)


def test_empty_list_raises(tmp_path):
    _write_toml(tmp_path, "[tool.auntiepypi]\npackages = []\n")
    with pytest.raises(ConfigError, match="empty"):
        load_package_names(tmp_path)


def test_walks_up_to_find_pyproject(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["root-pkg"]\n')
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    assert load_package_names(nested) == ["root-pkg"]


def test_no_pyproject_anywhere_raises(tmp_path, monkeypatch):
    nested = tmp_path / "sub"
    nested.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ConfigError, match="no pyproject.toml"):
        load_package_names(nested)


def test_find_pyproject_returns_none_when_missing(tmp_path, monkeypatch):
    nested = tmp_path / "sub"
    nested.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    assert find_pyproject(nested) is None


def test_rejects_non_string_entries(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["good", 42]\n')
    with pytest.raises(ConfigError, match="non-string"):
        load_package_names(tmp_path)


def test_walks_past_pyproject_without_auntiepypi_table(tmp_path, monkeypatch):
    """Intermediate pyproject without [tool.auntiepypi] should not stop the walk."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Outer pyproject has the table; intermediate does not.
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["outer-pkg"]\n')
    inner = tmp_path / "sub"
    inner.mkdir()
    (inner / "pyproject.toml").write_text('[project]\nname = "intermediate"\n')
    deepest = inner / "src"
    deepest.mkdir()
    assert load_package_names(deepest) == ["outer-pkg"]
