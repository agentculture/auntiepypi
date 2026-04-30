"""Tests for `auntiepypi._server._wheelhouse` — filename parsing + project listing."""

from __future__ import annotations

from pathlib import Path

import pytest

from auntiepypi._server import _wheelhouse


# --------- PEP 503 name normalization ---------


def test_normalize_lowercases():
    assert _wheelhouse.normalize("Foo") == "foo"


def test_normalize_collapses_separators():
    assert _wheelhouse.normalize("Foo_Bar.Baz") == "foo-bar-baz"


def test_normalize_collapses_runs():
    assert _wheelhouse.normalize("foo___bar...baz") == "foo-bar-baz"


def test_normalize_mixed_separators():
    assert _wheelhouse.normalize("foo_-_bar") == "foo-bar"


def test_normalize_already_canonical():
    assert _wheelhouse.normalize("foo-bar") == "foo-bar"


def test_normalize_keeps_digits():
    assert _wheelhouse.normalize("Pillow9") == "pillow9"


# --------- parse_filename ---------


def test_parse_wheel_simple():
    assert _wheelhouse.parse_filename("requests-2.31.0-py3-none-any.whl") == (
        "requests",
        "2.31.0",
    )


def test_parse_wheel_with_build_tag():
    """PEP 427: optional build tag is digit-prefixed (3rd segment)."""
    assert _wheelhouse.parse_filename(
        "tensorflow-2.0.0-1-cp37-cp37m-manylinux2010_x86_64.whl"
    ) == ("tensorflow", "2.0.0")


def test_parse_wheel_underscore_in_name():
    """Wheels canonicalize the dist name with underscores."""
    assert _wheelhouse.parse_filename(
        "scikit_learn-1.3.0-cp311-cp311-manylinux_2_17_x86_64.whl"
    ) == ("scikit_learn", "1.3.0")


def test_parse_sdist_tar_gz():
    assert _wheelhouse.parse_filename("requests-2.31.0.tar.gz") == ("requests", "2.31.0")


def test_parse_sdist_zip():
    assert _wheelhouse.parse_filename("requests-2.31.0.zip") == ("requests", "2.31.0")


def test_parse_sdist_with_dot_in_version():
    assert _wheelhouse.parse_filename("Django-4.2.7.tar.gz") == ("Django", "4.2.7")


def test_parse_rejects_non_dist():
    assert _wheelhouse.parse_filename("README.md") is None
    assert _wheelhouse.parse_filename("requirements.txt") is None
    assert _wheelhouse.parse_filename("foo.exe") is None


def test_parse_rejects_malformed_wheel():
    """Wheel without enough segments → None."""
    assert _wheelhouse.parse_filename("foo.whl") is None


def test_parse_rejects_malformed_sdist():
    """Sdist without version separator → None."""
    assert _wheelhouse.parse_filename("foo.tar.gz") is None


# --------- list_projects ---------


def test_list_projects_empty(tmp_path):
    assert _wheelhouse.list_projects(tmp_path) == {}


def test_list_projects_single_wheel(tmp_path):
    (tmp_path / "requests-2.31.0-py3-none-any.whl").touch()
    result = _wheelhouse.list_projects(tmp_path)
    assert set(result.keys()) == {"requests"}
    assert len(result["requests"]) == 1
    assert result["requests"][0].name == "requests-2.31.0-py3-none-any.whl"


def test_list_projects_groups_by_normalized_name(tmp_path):
    """Both 'Foo_Bar' and 'foo-bar' filenames bucket under 'foo-bar'."""
    (tmp_path / "Foo_Bar-1.0-py3-none-any.whl").touch()
    (tmp_path / "foo-bar-2.0.tar.gz").touch()
    result = _wheelhouse.list_projects(tmp_path)
    assert set(result.keys()) == {"foo-bar"}
    assert len(result["foo-bar"]) == 2


def test_list_projects_multiple_versions(tmp_path):
    (tmp_path / "requests-2.30.0-py3-none-any.whl").touch()
    (tmp_path / "requests-2.31.0-py3-none-any.whl").touch()
    (tmp_path / "requests-2.31.0.tar.gz").touch()
    result = _wheelhouse.list_projects(tmp_path)
    assert set(result.keys()) == {"requests"}
    assert len(result["requests"]) == 3


def test_list_projects_skips_non_dist(tmp_path):
    (tmp_path / "requests-2.31.0-py3-none-any.whl").touch()
    (tmp_path / "README.md").touch()
    (tmp_path / ".gitkeep").touch()
    result = _wheelhouse.list_projects(tmp_path)
    assert set(result.keys()) == {"requests"}


def test_list_projects_missing_root(tmp_path):
    """Missing root → empty dict, not exception (server keeps running)."""
    assert _wheelhouse.list_projects(tmp_path / "does-not-exist") == {}


def test_list_projects_skips_subdirectories(tmp_path):
    """Walk is one-level only; subdirs are not recursed."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "should-not-be-found-1.0-py3-none-any.whl").touch()
    (tmp_path / "found-1.0-py3-none-any.whl").touch()
    result = _wheelhouse.list_projects(tmp_path)
    assert set(result.keys()) == {"found"}


def test_list_projects_returns_paths_in_root(tmp_path):
    (tmp_path / "requests-2.31.0-py3-none-any.whl").touch()
    result = _wheelhouse.list_projects(tmp_path)
    path: Path = result["requests"][0]
    assert path.parent == tmp_path
