"""Tests for XDG state-dir resolver and name slugifier."""

from __future__ import annotations

from pathlib import Path

import pytest

from auntiepypi._actions._logs import path_for, slugify, state_root


def test_state_root_uses_xdg_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert state_root() == tmp_path / "auntiepypi"


def test_state_root_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert state_root() == Path.home() / ".local" / "state" / "auntiepypi"


def test_state_root_treats_blank_xdg_as_unset(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "   ")
    assert state_root() == Path.home() / ".local" / "state" / "auntiepypi"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("main", "main"),
        ("Main", "main"),
        ("hello world", "hello_world"),
        ("a/b\\c", "a_b_c"),
        ("name.with.dots", "name.with.dots"),
        ("UPPER_CASE", "upper_case"),
        ("hyphen-ok", "hyphen-ok"),
        ("..", ".."),
        ("名前", "__"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_path_for_uses_state_root(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert path_for("main") == tmp_path / "auntiepypi" / "main.log"


def test_path_for_slugifies(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert path_for("Bad/Name") == tmp_path / "auntiepypi" / "bad_name.log"
