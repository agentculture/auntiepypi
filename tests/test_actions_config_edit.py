"""Tests for delete-whole-entry mutation + numbered .bak snapshot."""

from __future__ import annotations

import pytest

from auntiepypi._actions._config_edit import (  # noqa: F401
    DeleteResult,
    delete_entry,
    snapshot,
)
from auntiepypi.cli._errors import AfiError

CLEAN_ENTRY = """\
[project]
name = "demo"

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "pypi-server.service"

[[tool.auntiepypi.servers]]
name = "alt"
flavor = "devpi"
port = 3141
managed_by = "manual"
"""


def test_delete_entry_clean(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(CLEAN_ENTRY)
    result = delete_entry(p, "main")
    assert result.ok is True
    text = p.read_text()
    assert 'name = "main"' not in text
    assert 'name = "alt"' in text  # other entry untouched
    assert "[[tool.auntiepypi.servers]]" in text  # alt's header still present
    assert text.count("[[tool.auntiepypi.servers]]") == 1  # main's header is gone


def test_delete_entry_unparseable_inline_table(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        "[[tool.auntiepypi.servers]]\n"
        'name = "main"\nflavor = "pypiserver"\nport = 8080\n'
        '[[tool.auntiepypi.servers]] { name = "weird", flavor = "devpi", port = 3141 }\n'
    )
    result = delete_entry(p, "weird")
    assert result.ok is False
    assert "could not parse" in result.reason.lower() or "inline" in result.reason.lower()


def test_delete_entry_not_found(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(CLEAN_ENTRY)
    result = delete_entry(p, "nonexistent")
    assert result.ok is False
    assert "not found" in result.reason.lower()


def test_snapshot_first_bak(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text("hello\n")
    bak = snapshot(p)
    assert bak == tmp_path / "pyproject.toml.1.bak"
    assert bak.read_text() == "hello\n"


def test_snapshot_picks_next_n(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text("v3\n")
    (tmp_path / "pyproject.toml.1.bak").write_text("v1\n")
    (tmp_path / "pyproject.toml.2.bak").write_text("v2\n")
    bak = snapshot(p)
    assert bak == tmp_path / "pyproject.toml.3.bak"
    assert bak.read_text() == "v3\n"


def test_snapshot_skips_gap(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text("x\n")
    (tmp_path / "pyproject.toml.1.bak").write_text("v1\n")
    (tmp_path / "pyproject.toml.5.bak").write_text("v5\n")
    bak = snapshot(p)
    # max+1 is acceptable; gap-filling is not required.
    assert bak.name == "pyproject.toml.6.bak"


def test_snapshot_race_retry(tmp_path, monkeypatch):
    """If `open(..., 'xb')` collides, snapshot picks the next free N."""
    p = tmp_path / "pyproject.toml"
    p.write_text("x\n")
    (tmp_path / "pyproject.toml.1.bak").write_text("v1\n")
    real_open = open
    seen_bak = []

    def patched_open(path, mode, *a, **kw):
        if str(path).endswith(".2.bak") and mode == "xb" and ".2.bak" not in seen_bak:
            seen_bak.append(".2.bak")
            (tmp_path / "pyproject.toml.2.bak").write_text("collision")
            raise FileExistsError(path)
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", patched_open)
    bak = snapshot(p)
    assert bak.name == "pyproject.toml.3.bak"


def test_snapshot_exhaustion(tmp_path, monkeypatch):
    """After 5 retries against successive collisions, raise AfiError."""
    p = tmp_path / "pyproject.toml"
    p.write_text("x\n")
    real_open = open

    def always_collide(path, mode, *a, **kw):
        if mode == "xb":
            raise FileExistsError(path)
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", always_collide)
    with pytest.raises(AfiError) as excinfo:
        snapshot(p)
    assert excinfo.value.code == 1
    assert "clean up" in excinfo.value.remediation
