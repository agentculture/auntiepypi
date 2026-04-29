"""Tests for the post-spawn re-probe loop.

The loop polls TCP+HTTP at increasing intervals (0.5s, 1s, 2s, 3.5s, 5s)
within a 5-second wall budget; first ``up`` wins.
"""

from __future__ import annotations

import http.server
import socket
import threading

import pytest

from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._detection import Detection


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _PypiServerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><a href='pkg/'>pkg</a></body></html>")

    def log_message(self, *a, **kw):  # silence
        pass


@pytest.fixture
def pypiserver_on_port():
    port = _free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _PypiServerHandler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield port
    srv.shutdown()
    srv.server_close()


def _detection(port: int, flavor: str = "pypiserver") -> Detection:
    return Detection(
        name=f"{flavor}:{port}",
        flavor=flavor,
        host="127.0.0.1",
        port=port,
        url=f"http://127.0.0.1:{port}/",
        status="down",
        source="declared",
    )


def test_reprobe_succeeds_immediately(pypiserver_on_port):
    result = probe(_detection(pypiserver_on_port), budget_seconds=5.0)
    assert result.status == "up"


def test_reprobe_never_succeeds_when_no_server():
    port = _free_port()
    result = probe(_detection(port), budget_seconds=1.0)
    assert result.status in ("absent", "down")


def test_reprobe_flavor_mismatch(pypiserver_on_port):
    det = _detection(pypiserver_on_port, flavor="devpi")
    result = probe(det, budget_seconds=2.0)
    assert result.status == "down"
    assert "flavor" in (result.detail or "")
