"""Tests for `[tool.auntiepypi.local]` loader and `LocalConfig`."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from auntiepypi._detect._config import (
    ServerConfigError,
    _is_loopback,
    load_local_config,
)
from auntiepypi._server._config import LocalConfig, default_root

# --------- default_root() ---------


def test_default_root_uses_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_root() == tmp_path / "auntiepypi" / "wheels"


def test_default_root_falls_back_to_local_share(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", "/fake/home")
    assert default_root() == Path("/fake/home/.local/share/auntiepypi/wheels")


# --------- LocalConfig defaults ---------


def test_localconfig_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = LocalConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_localconfig_is_frozen():
    from dataclasses import FrozenInstanceError

    cfg = LocalConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.port = 9999  # type: ignore[misc]


# --------- _is_loopback helper ---------


def test_is_loopback_recognizes_aliases():
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("127.0.0.5")  # anywhere in 127.0.0.0/8
    assert _is_loopback("localhost")
    assert _is_loopback("LocalHost")  # case-insensitive
    assert _is_loopback("::1")


def test_is_loopback_rejects_public():
    # The hardcoded IPs below are fixtures asserting that _is_loopback
    # rejects them; they are never used to dial out. The trailing
    # markers pin the linter rule on each line so future linter
    # updates don't silently flag the surrounding test as a
    # real-world IP usage.
    assert not _is_loopback("0.0.0.0")  # noqa: S104
    assert not _is_loopback("10.0.0.1")  # NOSONAR python:S1313
    assert not _is_loopback("8.8.8.8")  # NOSONAR python:S1313
    assert not _is_loopback("example.com")
    assert not _is_loopback("")


# --------- load_local_config() ---------


def _write_pyproject(path: Path, body: str) -> None:
    (path / "pyproject.toml").write_text(textwrap.dedent(body))


def test_load_local_config_no_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = load_local_config(tmp_path)
    # Defaults apply.
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_load_local_config_table_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi]
        scan_processes = false
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141


def test_load_local_config_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    wheel_dir = tmp_path / "wheels-custom"
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        host = "::1"
        port = 9999
        root = "{wheel_dir}"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "::1"
    assert cfg.port == 9999
    assert cfg.root == wheel_dir


def test_load_local_config_partial_override(tmp_path, monkeypatch):
    """Setting just `port` keeps host and root at defaults."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = 4242
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 4242
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_load_local_config_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        root = "~/wheels"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.root == tmp_path / "wheels"


def test_load_local_config_rejects_non_loopback(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        """,
    )
    with pytest.raises(ServerConfigError, match="loopback only"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_public_ip(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "10.0.0.5"
        """,
    )
    with pytest.raises(ServerConfigError, match="loopback only"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_bad_port_type(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = "not-an-int"
        """,
    )
    with pytest.raises(ServerConfigError, match="port"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_port_out_of_range(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = 70000
        """,
    )
    with pytest.raises(ServerConfigError, match="port"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_non_table(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi]
        local = "not a table"
        """,
    )
    with pytest.raises(ServerConfigError, match="must be a table"):
        load_local_config(tmp_path)


def test_load_local_config_localhost_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "localhost"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "localhost"
