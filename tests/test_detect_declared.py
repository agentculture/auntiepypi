"""Tests for the declared-inventory detector."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._declared import detect


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server() -> Iterator:
    servers: list[HTTPServer] = []

    def start(handler_cls):
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return "127.0.0.1", server.server_address[1]

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()


def _silent(handler_cls):
    handler_cls.log_message = lambda *a, **kw: None
    return handler_cls


def test_empty_declared_returns_empty() -> None:
    assert detect(declared=[], scan_processes=False) == []


def test_declared_absent_when_nothing_listens() -> None:
    spec = ServerSpec(name="main", flavor="pypiserver", host="127.0.0.1", port=_free_port())
    detections = detect(declared=[spec], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.name == "main"
    assert d.status == "absent"
    assert d.source == "declared"
    assert d.flavor == "pypiserver"


def test_declared_up_when_server_returns_200(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<a href="foo/">foo</a>')

    host, port = http_server(H)
    spec = ServerSpec(
        name="main",
        flavor="pypiserver",
        host=host,
        port=port,
        managed_by="systemd-user",
        unit="pypi.service",
    )
    detections = detect(declared=[spec], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.status == "up"
    assert d.name == "main"
    assert d.managed_by == "systemd-user"
    assert d.unit == "pypi.service"


def test_declared_flavor_mismatch_marked_down(http_server) -> None:
    """Declared flavor must match the fingerprint; otherwise status=down."""

    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"resources": {}}')  # devpi-shaped

    host, port = http_server(H)
    spec = ServerSpec(name="main", flavor="pypiserver", host=host, port=port)
    detections = detect(declared=[spec], scan_processes=False)
    d = detections[0]
    assert d.status == "down"
    assert "flavor mismatch" in (d.detail or "")


def test_declared_5xx_marked_down(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.end_headers()

    host, port = http_server(H)
    spec = ServerSpec(name="main", flavor="pypiserver", host=host, port=port)
    detections = detect(declared=[spec], scan_processes=False)
    assert detections[0].status == "down"
    assert "503" in (detections[0].detail or "")


def test_declared_unknown_flavor_skips_fingerprint_check(http_server) -> None:
    """flavor='unknown' means 'I don't care what answers'; any 2xx is up."""

    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"hello")

    host, port = http_server(H)
    spec = ServerSpec(name="x", flavor="unknown", host=host, port=port)
    d = detect(declared=[spec], scan_processes=False)[0]
    assert d.status == "up"
