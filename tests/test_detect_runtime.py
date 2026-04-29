"""Tests for _detect runtime: Detection dataclass and merge logic."""

from __future__ import annotations

from auntiepypi._detect._detection import Detection


def test_to_section_minimal_fields() -> None:
    d = Detection(
        name="main",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="up",
        source="declared",
    )
    section = d.to_section()
    assert section["category"] == "servers"
    assert section["title"] == "main"
    assert section["light"] == "green"
    field_names = {f["name"] for f in section["fields"]}
    assert {"flavor", "host", "port", "url", "status", "source"} <= field_names
    # No optional fields when none populated
    assert "pid" not in field_names
    assert "managed_by" not in field_names


def test_to_section_includes_optional_fields_when_populated() -> None:
    d = Detection(
        name="main",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="down",
        source="declared",
        pid=1234,
        cmdline="pypi-server run -p 8080",
        detail="http 503",
        managed_by="systemd-user",
        unit="pypi.service",
        command=("pypi-server", "run", "-p", "8080"),
    )
    section = d.to_section()
    field_map = {f["name"]: f["value"] for f in section["fields"]}
    assert field_map["pid"] == "1234"
    assert field_map["detail"] == "http 503"
    assert field_map["managed_by"] == "systemd-user"
    assert field_map["unit"] == "pypi.service"
    assert field_map["command"] == "pypi-server run -p 8080"
    assert section["light"] == "red"


def test_light_mapping_for_absent() -> None:
    d = Detection(
        name="x",
        flavor="unknown",
        host="127.0.0.1",
        port=99,
        url="http://127.0.0.1:99/",
        status="absent",
        source="port",
    )
    assert d.to_section()["light"] == "unknown"
