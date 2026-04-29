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
