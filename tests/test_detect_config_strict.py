"""Tests for strict-mode `load_servers` — cross-field validation.

Strict mode is what `overview`/non-doctor verbs use. On any cross-field
violation, raises ``ServerConfigError`` (which the CLI converts to
``AfiError(code=1)``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auntiepypi._detect._config import ServerConfigError, load_servers


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body)
    return tmp_path


def test_strict_clean_config(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "pypi-server.service"
""",
    )
    cfg = load_servers(start=start)
    assert len(cfg.specs) == 1


def test_strict_systemd_user_missing_unit(tmp_path):
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
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    assert "unit" in str(excinfo.value)
    assert "main" in str(excinfo.value)


def test_strict_command_missing_command(tmp_path):
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
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    assert "command" in str(excinfo.value)


def test_strict_docker_missing_dockerfile(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "docker"
""",
    )
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    assert "dockerfile" in str(excinfo.value)


def test_strict_compose_missing_compose(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "compose"
""",
    )
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    assert "compose" in str(excinfo.value)


def test_strict_manual_no_companions_required(tmp_path):
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
    cfg = load_servers(start=start)
    assert len(cfg.specs) == 1


def test_strict_unset_managed_by_no_companions_required(tmp_path):
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
""",
    )
    cfg = load_servers(start=start)
    assert len(cfg.specs) == 1


def test_strict_multiple_violations_reported(tmp_path):
    """All violations should appear in the message, not just the first."""
    start = _write(
        tmp_path,
        """\
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"

[[tool.auntiepypi.servers]]
name = "b"
flavor = "devpi"
port = 3141
managed_by = "command"
""",
    )
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    msg = str(excinfo.value)
    assert "a" in msg and "b" in msg
    assert "unit" in msg and "command" in msg


def test_strict_duplicate_names_still_raises(tmp_path):
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
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers(start=start)
    assert "duplicate" in str(excinfo.value).lower()
