"""Tests for the probe runtime and per-flavor definitions."""

from __future__ import annotations

import socket
from typing import Callable

from agentpypi._probes import PROBES, devpi, probe_status, pypiserver
from agentpypi._probes._probe import Probe


def _free_port() -> int:
    """Return a port that's free at the moment of the call."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_known_flavors_registered() -> None:
    """The Probe registry exposes both shipped flavors."""
    names = {p.name for p in PROBES}
    assert names == {"devpi", "pypiserver"}


def test_devpi_definition() -> None:
    assert devpi.name == "devpi"
    assert devpi.default_port == 3141
    assert devpi.health_path == "/+api"
    assert devpi.start_command == ("devpi-server", "--start")


def test_pypiserver_definition() -> None:
    assert pypiserver.name == "pypiserver"
    assert pypiserver.default_port == 8080
    assert pypiserver.start_command == ("pypi-server", "run")


def test_health_url_format() -> None:
    assert devpi.health_url("h", 1234) == "http://h:1234/+api"
    assert devpi.health_url() == "http://127.0.0.1:3141/+api"


def test_probe_up_when_server_returns_2xx(
    fake_http_server: Callable[[int], tuple[str, int]],
) -> None:
    host, port = fake_http_server(200)
    result = probe_status(devpi, host=host, port=port, timeout=2.0)
    assert result["status"] == "up"
    assert result["name"] == "devpi"
    assert result["port"] == port
    assert result["url"].startswith("http://")


def test_probe_down_when_server_returns_5xx(
    fake_http_server: Callable[[int], tuple[str, int]],
) -> None:
    host, port = fake_http_server(500)
    result = probe_status(devpi, host=host, port=port, timeout=2.0)
    assert result["status"] == "down"
    assert "500" in result.get("detail", "")


def test_probe_absent_when_nothing_listens() -> None:
    port = _free_port()
    # Nothing is listening on `port` between the bind/release above and now;
    # there's a tiny race window but it's been reliable in CI for siblings.
    result = probe_status(devpi, port=port, timeout=0.5)
    assert result["status"] == "absent"


def test_probe_returns_typed_keys() -> None:
    result = probe_status(devpi, port=_free_port(), timeout=0.5)
    assert set(result.keys()) >= {"name", "port", "url", "status"}


def test_custom_probe_can_be_constructed() -> None:
    """The Probe interface accepts new flavors without code changes elsewhere."""
    custom = Probe(
        name="custom",
        default_port=9999,
        health_path="/health",
        start_command=("custom-server", "start"),
    )
    assert custom.health_url() == "http://127.0.0.1:9999/health"
