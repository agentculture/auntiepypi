"""Verify strict-mode cross-field validation surfaces in `overview`."""

from __future__ import annotations

import pytest

from auntiepypi.cli._commands.overview import cmd_overview
from auntiepypi.cli._errors import AfiError


def test_overview_exits_1_on_half_supervised_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "pyproject.toml"
    p.write_text("""\
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
""")
    args = type("A", (), {"target": None, "proc": False, "json": False})()
    with pytest.raises(AfiError) as excinfo:
        cmd_overview(args)
    assert excinfo.value.code == 1
    assert "main" in excinfo.value.message
    assert "unit" in excinfo.value.message
