"""Tests for _rubric/_fetch.get_json — stdlib urllib wrapper."""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agentpypi._rubric._fetch import FetchError, get_json


class _Handler(BaseHTTPRequestHandler):
    """Configurable handler. Behavior set by class attrs before each test."""

    status: int = 200
    body: bytes = b'{"ok": true}'
    sleep: float = 0.0

    def do_GET(self) -> None:  # noqa: N802
        if self.sleep:
            time.sleep(self.sleep)
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *_: object) -> None:  # silence
        pass


@pytest.fixture
def server():
    """Start a localhost HTTP server on an ephemeral port."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{srv.server_address[0]}:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        thread.join(timeout=2)


def test_200_returns_dict(server):
    _Handler.status = 200
    _Handler.body = b'{"hello": "world"}'
    _Handler.sleep = 0.0
    assert get_json(server + "/x") == {"hello": "world"}


def test_404_raises_fetcherror_with_status(server):
    _Handler.status = 404
    _Handler.body = b"not found"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError) as excinfo:
        get_json(server + "/x")
    assert excinfo.value.status == 404


def test_500_raises_fetcherror_with_status(server):
    _Handler.status = 500
    _Handler.body = b"server error"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError) as excinfo:
        get_json(server + "/x")
    assert excinfo.value.status == 500


def test_malformed_json_raises_fetcherror(server):
    _Handler.status = 200
    _Handler.body = b"not json at all"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError, match="unexpected response shape"):
        get_json(server + "/x")


def test_timeout_raises_fetcherror(server):
    _Handler.status = 200
    _Handler.body = b'{"ok": true}'
    _Handler.sleep = 0.5
    with pytest.raises(FetchError, match="fetch failed"):
        get_json(server + "/x", timeout=0.1)


def test_connection_refused_raises_fetcherror():
    """Use a free port that nothing is listening on."""
    with pytest.raises(FetchError, match="fetch failed"):
        get_json("http://127.0.0.1:1/", timeout=1.0)


def test_user_agent_sent(server):
    """Confirm the UA header is what we promise downstream."""
    received_ua: dict[str, str] = {}

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received_ua["ua"] = self.headers.get("User-Agent", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_: object) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        url = f"http://{srv.server_address[0]}:{srv.server_address[1]}"
        get_json(url + "/x")
    finally:
        srv.shutdown()
        thr.join(timeout=2)

    assert received_ua["ua"].startswith("agentpypi/")
    assert "github.com/agentculture/agentpypi" in received_ua["ua"]
