"""Tests for `auntiepypi._detect._local` and the runtime chain order."""

from __future__ import annotations

from auntiepypi._detect import _local, _runtime
from auntiepypi._detect._config import ServersConfig
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import ProbeOutcome


def _outcome(
    *, tcp_open: bool, http_status: int | None, body: bytes | None = None, error: str | None = None
) -> ProbeOutcome:
    return ProbeOutcome(
        url="http://127.0.0.1:3141/",
        tcp_open=tcp_open,
        http_status=http_status,
        body=body,
        error=error,
    )


# --------- _local.detect() ---------


def test_local_detect_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _local, "probe_endpoint", lambda h, p, **kw: _outcome(tcp_open=False, http_status=None)
    )
    det = _local.detect()
    assert det.name == "auntie"
    assert det.flavor == "auntiepypi"
    assert det.source == "local"
    assert det.managed_by == "auntie"
    assert det.host == "127.0.0.1"
    assert det.port == 3141
    assert det.status == "absent"


def test_local_detect_up(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _local,
        "probe_endpoint",
        lambda h, p, **kw: _outcome(tcp_open=True, http_status=200, body=b"<html>"),
    )
    det = _local.detect()
    assert det.status == "up"
    assert det.source == "local"


def test_local_detect_down_http_error(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _local,
        "probe_endpoint",
        lambda h, p, **kw: _outcome(tcp_open=True, http_status=None, error="timeout"),
    )
    det = _local.detect()
    assert det.status == "down"
    assert det.detail == "timeout"


def test_local_detect_down_5xx(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _local,
        "probe_endpoint",
        lambda h, p, **kw: _outcome(tcp_open=True, http_status=503),
    )
    det = _local.detect()
    assert det.status == "down"
    assert "503" in det.detail


def test_local_detect_uses_configured_host_port(tmp_path, monkeypatch):
    """_local reads pyproject's [tool.auntiepypi.local] each call."""
    (tmp_path / "pyproject.toml").write_text('[tool.auntiepypi.local]\nhost = "::1"\nport = 9999\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    captured = {}

    def fake_probe(host, port, **kw):
        captured["host"] = host
        captured["port"] = port
        return _outcome(tcp_open=False, http_status=None)

    monkeypatch.setattr(_local, "probe_endpoint", fake_probe)
    det = _local.detect()
    assert captured == {"host": "::1", "port": 9999}
    assert det.host == "::1"
    assert det.port == 9999


# --------- v0.7.0: HTTPS scheme + 401-as-up ---------


def test_local_detect_uses_https_when_tls_configured(tmp_path, monkeypatch):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.auntiepypi.local]\ncert = "{cert}"\nkey = "{key}"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    captured = {}

    def fake_probe(host, port, **kw):
        captured["scheme"] = kw.get("scheme")
        captured["ssl_context"] = kw.get("ssl_context")
        return _outcome(tcp_open=True, http_status=200)

    monkeypatch.setattr(_local, "probe_endpoint", fake_probe)
    _local.detect()
    assert captured["scheme"] == "https"
    assert captured["ssl_context"] is not None


def test_local_detect_uses_http_when_tls_not_configured(tmp_path, monkeypatch):
    """v0.6.0-style configs (no cert/key) still probe over plain HTTP."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    captured = {}

    def fake_probe(host, port, **kw):
        captured["scheme"] = kw.get("scheme")
        captured["ssl_context"] = kw.get("ssl_context")
        return _outcome(tcp_open=False, http_status=None)

    monkeypatch.setattr(_local, "probe_endpoint", fake_probe)
    _local.detect()
    assert captured["scheme"] == "http"
    assert captured["ssl_context"] is None


def test_local_detect_401_counts_as_up_when_auth_enabled(tmp_path, monkeypatch):
    htp = tmp_path / "htp"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.auntiepypi.local]\nhtpasswd = "{htp}"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    monkeypatch.setattr(
        _local,
        "probe_endpoint",
        lambda h, p, **kw: _outcome(tcp_open=True, http_status=401),
    )
    det = _local.detect()
    # 401 from a server with auth on means the gate is working.
    assert det.status == "up"


def test_local_detect_401_is_down_when_auth_not_enabled(tmp_path, monkeypatch):
    """A 401 from a server we *don't* expect to require auth is anomalous."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    monkeypatch.setattr(
        _local,
        "probe_endpoint",
        lambda h, p, **kw: _outcome(tcp_open=True, http_status=401),
    )
    det = _local.detect()
    assert det.status == "down"
    assert "401" in det.detail


# --------- detect_all chain ---------


def test_detect_all_includes_local_first(monkeypatch, tmp_path):
    """The local detection appears first in the result list."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _runtime,
        "_local_detect",
        lambda: Detection(
            name="auntie",
            flavor="auntiepypi",
            host="127.0.0.1",
            port=3141,
            url="http://127.0.0.1:3141/",
            status="absent",
            source="local",
            managed_by="auntie",
        ),
    )
    monkeypatch.setattr(_runtime, "_declared_detect", lambda specs, *, scan_processes: [])
    monkeypatch.setattr(_runtime, "_port_detect", lambda specs, *, scan_processes, covered: [])

    results = _runtime.detect_all(ServersConfig())
    assert results[0].source == "local"
    assert results[0].name == "auntie"


def test_detect_all_passes_local_into_covered(monkeypatch, tmp_path):
    """Port scanner sees local (host, port) in `covered` and skips it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(
        _runtime,
        "_local_detect",
        lambda: Detection(
            name="auntie",
            flavor="auntiepypi",
            host="127.0.0.1",
            port=3141,
            url="http://127.0.0.1:3141/",
            status="absent",
            source="local",
        ),
    )
    monkeypatch.setattr(_runtime, "_declared_detect", lambda specs, *, scan_processes: [])

    captured: dict[str, set] = {}

    def fake_port_detect(specs, *, scan_processes, covered):
        captured["covered"] = set(covered)
        return []

    monkeypatch.setattr(_runtime, "_port_detect", fake_port_detect)
    _runtime.detect_all(ServersConfig())
    assert ("127.0.0.1", 3141) in captured["covered"]


def test_detect_all_dedup_with_declared_on_same_port(monkeypatch, tmp_path):
    """If a declared server happens to be on 127.0.0.1:3141, both
    appear (local first); the port scanner sees both in covered.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    local = Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="absent",
        source="local",
    )
    declared = Detection(
        name="my-devpi",
        flavor="devpi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="up",
        source="declared",
    )
    monkeypatch.setattr(_runtime, "_local_detect", lambda: local)
    monkeypatch.setattr(_runtime, "_declared_detect", lambda specs, *, scan_processes: [declared])

    captured: dict = {}

    def fake_port_detect(specs, *, scan_processes, covered):
        captured["covered"] = set(covered)
        return []

    monkeypatch.setattr(_runtime, "_port_detect", fake_port_detect)
    results = _runtime.detect_all(ServersConfig())
    # Local first, then declared.
    assert results[0].source == "local"
    assert results[1].source == "declared"
    # Only one (host, port) in covered (set semantics).
    assert ("127.0.0.1", 3141) in captured["covered"]
