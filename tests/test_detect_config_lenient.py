"""Tests for `load_servers_lenient` — used only by `doctor`.

Returns ``(ServersConfig, list[ConfigGap])``. Never raises on
cross-field violations; surfaces them as gaps with line numbers.
"""

from __future__ import annotations

from pathlib import Path

from auntiepypi._detect._config import (
    ConfigGap,
    ServersConfig,
    load_servers_lenient,
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body)
    return tmp_path


def test_lenient_clean_config(tmp_path):
    start = _write(
        tmp_path,
        """\
[project]
name = "demo"

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "pypi-server.service"
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    assert isinstance(cfg, ServersConfig)
    assert len(cfg.specs) == 1
    assert gaps == []


def test_lenient_half_supervised_systemd_user(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    assert len(cfg.specs) == 1
    assert len(gaps) == 1
    assert isinstance(gaps[0], ConfigGap)
    assert gaps[0].kind == "missing-companion"
    assert gaps[0].name == "main"
    assert "unit" in gaps[0].detail


def test_lenient_half_supervised_command(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "command"
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    assert len(gaps) == 1
    assert gaps[0].kind == "missing-companion"
    assert "command" in gaps[0].detail


def test_lenient_duplicate_name(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "manual"

[[tool.auntiepypi.servers]]
name = "main"
flavor = "devpi"
port = 3141
managed_by = "manual"
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    dup_gaps = [g for g in gaps if g.kind == "duplicate"]
    assert len(dup_gaps) == 1
    assert dup_gaps[0].name == "main"
    assert len(dup_gaps[0].lines) == 2


def test_lenient_manual_no_companions_required(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "manual"
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    assert gaps == []


def test_lenient_unset_managed_by_no_companions_required(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
""",
    )
    cfg, gaps = load_servers_lenient(start=start)
    assert gaps == []


def test_lenient_no_pyproject_returns_empty(tmp_path):
    cfg, gaps = load_servers_lenient(start=tmp_path)
    assert cfg.specs == ()
    assert gaps == []
