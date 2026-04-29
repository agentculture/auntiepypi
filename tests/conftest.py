"""Shared fixtures for auntiepypi tests.

Provides an in-process HTTP server fixture so probe tests don't depend on
any external port/process. Stdlib only — no aiohttp/Flask/etc.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Iterator

import pytest

# Type for a handler-factory: takes a status code, returns a request-handler class.
HandlerFactory = Callable[[int], type[BaseHTTPRequestHandler]]


def _handler_for(status: int) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server contract
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}\n')

        def log_message(self, fmt: str, *args: object) -> None:  # noqa: A002
            # Silence the default stderr access log.
            return

    return _Handler


@pytest.fixture
def fake_http_server() -> Iterator[Callable[[int], tuple[str, int]]]:
    """Yield a callable: ``start(status_code) -> (host, port)``.

    Multiple servers can be started in one test. All are torn down on exit.
    """
    servers: list[HTTPServer] = []

    def start(status: int = 200) -> tuple[str, int]:
        server = HTTPServer(("127.0.0.1", 0), _handler_for(status))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        host, port = server.server_address[0], server.server_address[1]
        return host, port

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()
