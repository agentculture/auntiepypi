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


# ----- Task 7: detect_all merge logic -----

from unittest.mock import patch  # noqa: E402

from auntiepypi._detect._config import ServersConfig, ServerSpec  # noqa: E402
from auntiepypi._detect._runtime import detect_all  # noqa: E402


def _det(name, port, source, status="up", flavor="pypiserver", pid=None) -> Detection:
    return Detection(
        name=name,
        flavor=flavor,
        host="127.0.0.1",
        port=port,
        url=f"http://127.0.0.1:{port}/",
        status=status,
        source=source,
        pid=pid,
    )


def test_detect_all_empty_config_runs_port_scan_only() -> None:
    cfg = ServersConfig(specs=(), scan_processes=False)
    declared_calls: list = []

    def fake_declared(declared, *, scan_processes):
        declared_calls.append(list(declared))
        return []

    def fake_port(declared, *, scan_processes, covered=None):
        return [_det("pypiserver:8080", 8080, "port", status="absent")]

    def fake_proc(declared, *, scan_processes, **kw):
        return []

    with (
        patch("auntiepypi._detect._runtime._declared_detect", fake_declared),
        patch("auntiepypi._detect._runtime._port_detect", fake_port),
        patch("auntiepypi._detect._runtime._proc_detect", fake_proc),
    ):
        result = detect_all(cfg)
    assert len(result) == 1
    assert result[0].source == "port"
    assert declared_calls == [[]]


def test_detect_all_augment_suppresses_absent_from_scan_when_declared_exists() -> None:
    spec = ServerSpec(name="main", flavor="pypiserver", host="127.0.0.1", port=8080)
    cfg = ServersConfig(specs=(spec,), scan_processes=False)
    declared_results = [_det("main", 8080, "declared")]
    port_results = [
        _det("devpi:3141", 3141, "port", status="absent", flavor="unknown"),
    ]

    with (
        patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: declared_results),
        patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: port_results),
        patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: []),
    ):
        result = detect_all(cfg)
    sources = [d.source for d in result]
    assert "declared" in sources
    port_absent = [d for d in result if d.source == "port" and d.status == "absent"]
    assert port_absent == []


def test_detect_all_keeps_port_scan_finds_when_declared_exists() -> None:
    """When declared exists AND port scan finds an *up* extra, keep it."""
    spec = ServerSpec(name="main", flavor="devpi", host="127.0.0.1", port=3141)
    cfg = ServersConfig(specs=(spec,), scan_processes=False)
    declared_results = [_det("main", 3141, "declared", flavor="devpi")]
    port_results = [_det("pypiserver:8080", 8080, "port", status="up")]

    with (
        patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: declared_results),
        patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: port_results),
        patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: []),
    ):
        result = detect_all(cfg)
    sources = {d.source for d in result}
    assert sources == {"declared", "port"}


def test_detect_all_proc_enriches_existing_detection_with_pid() -> None:
    """Proc-found PID for a (host, port) already detected enriches it."""
    cfg = ServersConfig(specs=(), scan_processes=True)
    port_d = _det("pypiserver:8080", 8080, "port", status="up")
    proc_d = _det("pypiserver:8080", 8080, "proc", status="up", pid=1234)

    with (
        patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: []),
        patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: [port_d]),
        patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: [proc_d]),
    ):
        result = detect_all(cfg)
    assert len(result) == 1
    assert result[0].pid == 1234
    assert result[0].source == "port"


def test_detect_all_proc_only_finds_appended() -> None:
    cfg = ServersConfig(specs=(), scan_processes=True)
    proc_d = _det("pypiserver:9001", 9001, "proc", pid=999)

    with (
        patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: []),
        patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: []),
        patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: [proc_d]),
    ):
        result = detect_all(cfg)
    assert len(result) == 1
    assert result[0].source == "proc"
    assert result[0].port == 9001
