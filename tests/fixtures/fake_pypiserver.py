"""Tiny standalone HTTP server that mimics pypiserver for `command`-strategy tests.

Usage: ``python -m tests.fixtures.fake_pypiserver <port>``.
Runs forever; killed via process group when the test exits.
"""

from __future__ import annotations

import http.server
import sys


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><a href='pkg/'>pkg</a></body></html>")

    def log_message(self, *a, **kw):
        pass


def main() -> None:
    port = int(sys.argv[1])
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
