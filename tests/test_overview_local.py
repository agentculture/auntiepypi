"""v0.6.0: `auntie overview` surfaces the first-party server.

The integration was wired in Task 7 (``_detect/_local``); these tests
just verify the rendered output shows the local server in both text
and JSON modes, regardless of whether it's running.
"""

from __future__ import annotations

import json

import pytest

from auntiepypi._detect import _runtime
from auntiepypi._detect._detection import Detection
from auntiepypi.cli import main


def _local_stub_up() -> Detection:
    return Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="up",
        source="local",
        managed_by="auntie",
    )


def _local_stub_absent() -> Detection:
    return Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="absent",
        source="local",
        managed_by="auntie",
    )


def test_overview_renders_local_up(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_runtime, "_local_detect", _local_stub_up)
    rc = main(["overview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auntie" in out
    assert "auntiepypi" in out
    assert "127.0.0.1" in out
    assert "3141" in out
    assert "local" in out  # source field rendered


def test_overview_renders_local_absent(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_runtime, "_local_detect", _local_stub_absent)
    rc = main(["overview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auntie" in out
    assert "absent" in out


def test_overview_json_local_shape(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_runtime, "_local_detect", _local_stub_up)
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    sections = payload["sections"]
    local_sections = [
        s
        for s in sections
        if s.get("category") == "servers"
        and any(f["name"] == "source" and f["value"] == "local" for f in s["fields"])
    ]
    assert len(local_sections) == 1
    section = local_sections[0]
    assert section["title"] == "auntie"
    field_map = {f["name"]: f["value"] for f in section["fields"]}
    assert field_map["flavor"] == "auntiepypi"
    assert field_map["managed_by"] == "auntie"
    assert field_map["status"] == "up"


def test_overview_local_target_drilldown(monkeypatch, capsys, tmp_path):
    """`auntie overview auntie` drills into the local server."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_runtime, "_local_detect", _local_stub_up)
    rc = main(["overview", "auntie"])
    assert rc == 0
    out = capsys.readouterr().out
    # The target-specific output should still surface auntie's
    # detection block (overview's TARGET resolution falls back to
    # detection name lookup).
    assert "auntie" in out
