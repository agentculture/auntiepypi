"""Tests for `auntiepypi._server.__main__` and the `serve()` helper."""

from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from auntiepypi import _server
from auntiepypi._server import __main__ as server_main

# --------- argparse ---------


def test_parser_defaults():
    # /tmp path is an argparse fixture, never created on disk.
    fixture_root = "/tmp/wh"  # noqa: S108  # NOSONAR python:S5443
    args = server_main._parser().parse_args(["--root", fixture_root])
    assert args.host == "127.0.0.1"
    assert args.port == 3141
    assert args.root == Path(fixture_root)


def test_parser_overrides():
    # "0.0.0.0" is a fixture asserting argparse passes the value through;
    # the bind would be rejected at config-load time by load_local_config.
    args = server_main._parser().parse_args(
        ["--host", "0.0.0.0", "--port", "8080", "--root", "/var/wheels"]  # noqa: S104
    )
    assert args.host == "0.0.0.0"  # noqa: S104
    assert args.port == 8080
    assert args.root == Path("/var/wheels")


def test_parser_requires_root():
    with pytest.raises(SystemExit):
        server_main._parser().parse_args([])


def test_main_calls_serve(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_serve(host: str, port: int, root: Path) -> None:
        captured.update({"host": host, "port": port, "root": root})

    monkeypatch.setattr(server_main, "serve", fake_serve)
    server_main.main(["--host", "127.0.0.1", "--port", "9999", "--root", str(tmp_path)])
    assert captured == {"host": "127.0.0.1", "port": 9999, "root": tmp_path}


# --------- serve() integration ---------


def test_serve_handles_request_and_shuts_down(tmp_path):
    """End-to-end smoke test: serve() responds to /simple/ and exits cleanly."""
    (tmp_path / "demo-1.0-py3-none-any.whl").touch()

    started = threading.Event()
    captured: dict[str, object] = {}

    class _Recording:
        """Wrap ThreadingHTTPServer so the test can grab the instance and
        call shutdown() from outside.
        """

        def __init__(self, address, handler):
            from http.server import ThreadingHTTPServer

            self.inner = ThreadingHTTPServer(address, handler)
            self.server_address = self.inner.server_address
            captured["server"] = self
            started.set()

        def serve_forever(self):
            return self.inner.serve_forever()

        def shutdown(self):
            return self.inner.shutdown()

        def server_close(self):
            return self.inner.server_close()

    def runner():
        _server.serve("127.0.0.1", 0, tmp_path, server_factory=_Recording)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    assert started.wait(timeout=5), "server didn't start"

    server = captured["server"]
    port = server.server_address[1]

    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/simple/")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode()
        assert 'href="/simple/demo/"' in body
    finally:
        conn.close()

    server.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive()
