"""Tests for [[tool.auntiepypi.servers]] config loading."""

from __future__ import annotations

import pytest

from auntiepypi._detect._config import (
    ServerConfigError,
    ServerSpec,
    ServersConfig,
    load_servers,
)


def _write(tmp_path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(body)


def test_no_pyproject_returns_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg == ServersConfig(specs=(), scan_processes=False)


def test_pyproject_without_servers_key_returns_empty(tmp_path, monkeypatch) -> None:
    _write(tmp_path, '[tool.auntiepypi]\npackages = ["x"]\n')
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.specs == ()
    assert cfg.scan_processes is False


def test_array_of_tables_parsed(tmp_path, monkeypatch) -> None:
    _write(
        tmp_path,
        """\
[tool.auntiepypi]
packages = ["x"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080

[[tool.auntiepypi.servers]]
name = "dev"
flavor = "devpi"
host = "127.0.0.1"
port = 3141
managed_by = "systemd-user"
unit = "devpi.service"
""",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert len(cfg.specs) == 2
    assert cfg.specs[0] == ServerSpec(
        name="main", flavor="pypiserver", host="127.0.0.1", port=8080,
    )
    assert cfg.specs[1].name == "dev"
    assert cfg.specs[1].managed_by == "systemd-user"
    assert cfg.specs[1].unit == "devpi.service"
    assert cfg.scan_processes is False


def test_scan_processes_scalar(tmp_path, monkeypatch) -> None:
    _write(
        tmp_path,
        """\
[tool.auntiepypi]
packages = ["x"]
scan_processes = true
""",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.scan_processes is True


def test_command_normalised_to_tuple(tmp_path, monkeypatch) -> None:
    _write(
        tmp_path,
        """\
[tool.auntiepypi]
packages = ["x"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
command = ["pypi-server", "run", "-p", "8080"]
""",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.specs[0].command == ("pypi-server", "run", "-p", "8080")


@pytest.mark.parametrize(
    "body, msg",
    [
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
flavor = "pypiserver"
port = 8080
""",
            "missing 'name'",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
port = 8080
""",
            "missing 'flavor'",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "wat"
port = 8080
""",
            "invalid 'flavor'",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
""",
            "missing 'port'",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 0
""",
            "out of range",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 8080
[[tool.auntiepypi.servers]]
name = "a"
flavor = "devpi"
port = 3141
""",
            "duplicate name",
        ),
        (
            """\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 8080
managed_by = "kubernetes"
""",
            "invalid 'managed_by'",
        ),
    ],
)
def test_validation_errors(tmp_path, monkeypatch, body, msg) -> None:
    _write(tmp_path, body)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers()
    assert msg in str(excinfo.value)
