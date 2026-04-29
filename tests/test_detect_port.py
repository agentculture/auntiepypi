"""Tests for the HTTP probe primitive shared by _declared and _port."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest

from auntiepypi._detect._http import probe_endpoint


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server(handler_factory) -> tuple[HTTPServer, str, int]:
    server = HTTPServer(("127.0.0.1", 0), handler_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "127.0.0.1", server.server_address[1]


@pytest.fixture
def http_server() -> Iterator:
    servers: list[HTTPServer] = []

    def start(handler_factory):
        server, host, port = _make_server(handler_factory)
        servers.append(server)
        return host, port

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()


def _silent(handler_cls):
    handler_cls.log_message = lambda *a, **kw: None
    return handler_cls


def test_probe_absent_when_nothing_listens() -> None:
    out = probe_endpoint("127.0.0.1", _free_port(), timeout=0.5)
    assert out.tcp_open is False
    assert out.http_status is None
    assert out.body is None


def test_probe_up_when_server_returns_200(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<a href='foo/'>foo</a>")

    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0, path="/")
    assert out.tcp_open is True
    assert out.http_status == 200
    assert b"<a href" in out.body


def test_probe_5xx_returns_status(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.end_headers()

    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0)
    assert out.tcp_open is True
    assert out.http_status == 503


def test_probe_outcome_url_field(http_server) -> None:
    """ProbeOutcome carries the URL it probed for caller convenience."""

    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"")

    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0, path="/foo")
    assert out.url == f"http://{host}:{port}/foo"


# ----- Task 4: scanner + fingerprint -----

from auntiepypi._detect._detection import Detection  # noqa: E402
from auntiepypi._detect._port import (  # noqa: E402
    DEFAULT_PORTS,
    detect,
    fingerprint_flavor,
)


def test_default_ports_exposed() -> None:
    assert 3141 in DEFAULT_PORTS
    assert 8080 in DEFAULT_PORTS


def test_fingerprint_devpi_via_resources_key() -> None:
    body = b'{"type": "devpi-server", "resources": {"login": "/+login"}}'
    assert fingerprint_flavor(body, content_type="application/json") == "devpi"


def test_fingerprint_pypiserver_via_html_anchors() -> None:
    body = b'<html><body><a href="foo/">foo</a><a href="bar/">bar</a></body></html>'
    assert fingerprint_flavor(body, content_type="text/html") == "pypiserver"


def test_fingerprint_unknown_for_bare_simple_index() -> None:
    body = b"<html><body>nothing</body></html>"
    assert fingerprint_flavor(body, content_type="text/html") == "unknown"


def test_fingerprint_unknown_when_body_none() -> None:
    assert fingerprint_flavor(None, content_type=None) == "unknown"


def test_detect_emits_absent_for_closed_default_ports(monkeypatch) -> None:
    """When DEFAULT_PORTS aren't listening, scan emits absent detections."""
    monkeypatch.setattr(
        "auntiepypi._detect._port.DEFAULT_PORTS",
        (_free_port(), _free_port()),
    )
    detections = detect(declared=[], scan_processes=False)
    assert all(isinstance(d, Detection) for d in detections)
    assert all(d.status == "absent" for d in detections)
    assert all(d.source == "port" for d in detections)


def test_detect_skips_ports_in_covered_set(monkeypatch) -> None:
    """When a port is in `covered`, _port skips it."""
    p1, p2 = _free_port(), _free_port()
    monkeypatch.setattr("auntiepypi._detect._port.DEFAULT_PORTS", (p1, p2))
    detections = detect(declared=[], scan_processes=False, covered={("127.0.0.1", p1)})
    ports = {d.port for d in detections}
    assert p1 not in ports
    assert p2 in ports


def test_detect_finds_running_pypiserver(http_server, monkeypatch) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<a href="alpha/">alpha</a>')

    host, port = http_server(H)
    monkeypatch.setattr("auntiepypi._detect._port.DEFAULT_PORTS", (port,))
    detections = detect(declared=[], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.status == "up"
    assert d.flavor == "pypiserver"
    assert d.port == port
    assert d.name == f"pypiserver:{port}"
    assert d.source == "port"
