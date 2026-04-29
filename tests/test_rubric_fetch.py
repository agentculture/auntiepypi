"""Tests for _rubric/_fetch.get_json — stdlib urllib wrapper.

Each test builds its own handler class via ``_handler_for`` to avoid
shared mutable class state under ``pytest -n auto`` (xdist).
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from agentpypi._rubric._fetch import FetchError, get_json


def _handler_for(
    *, status: int = 200, body: bytes = b'{"ok": true}', sleep: float = 0.0
) -> type[BaseHTTPRequestHandler]:
    """Return a fresh handler class with the given response baked in."""

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if sleep:
                time.sleep(sleep)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: object) -> None:
            """Silence stderr access logs for cleaner pytest output."""

    return _Handler


def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = srv.server_address[0], srv.server_address[1]
        yield f"http://{host}:{port}"  # NOSONAR S5332 - loopback test server; localhost only
    finally:
        srv.shutdown()
        thread.join(timeout=2)


def test_200_returns_dict():
    for url in _serve(_handler_for(status=200, body=b'{"hello": "world"}')):
        assert get_json(url + "/x") == {"hello": "world"}


def test_404_raises_fetcherror_with_status():
    for url in _serve(_handler_for(status=404, body=b"not found")):
        with pytest.raises(FetchError) as excinfo:
            get_json(url + "/x")
        assert excinfo.value.status == 404


def test_500_raises_fetcherror_with_status():
    for url in _serve(_handler_for(status=500, body=b"server error")):
        with pytest.raises(FetchError) as excinfo:
            get_json(url + "/x")
        assert excinfo.value.status == 500


def test_malformed_json_raises_fetcherror():
    for url in _serve(_handler_for(status=200, body=b"not json at all")):
        with pytest.raises(FetchError, match="unexpected response shape"):
            get_json(url + "/x")


def test_timeout_raises_fetcherror():
    for url in _serve(_handler_for(status=200, sleep=0.5)):
        with pytest.raises(FetchError, match="fetch failed"):
            get_json(url + "/x", timeout=0.1)


def test_connection_refused_raises_fetcherror():
    """Use a free port that nothing is listening on."""
    with pytest.raises(FetchError, match="fetch failed"):
        get_json("http://127.0.0.1:1/", timeout=1.0)


def test_user_agent_sent():
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
            """Silence stderr access logs for cleaner pytest output."""

    for url in _serve(CaptureHandler):
        get_json(url + "/x")

    assert received_ua["ua"].startswith("agentpypi/")
    assert "github.com/agentculture/agentpypi" in received_ua["ua"]
