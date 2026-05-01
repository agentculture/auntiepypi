"""auntiepypi's first-party PEP 503 simple-index server.

v0.6.0 ships the read-only slice: serves wheels and sdists from a
filesystem wheelhouse. Loopback-only by config-load-time enforcement.
``auntie publish``, HTTPS, and basic-auth are deferred to v0.7.0.

Public surface lives in :mod:`auntiepypi._server.__init__` (this
module). The HTTP layer is :mod:`._app`; filesystem walk lives in
:mod:`._wheelhouse`; CLI entry is :mod:`.__main__`.
"""

from __future__ import annotations

import signal
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from auntiepypi._server._app import make_handler

__all__ = ["serve"]


def serve(
    host: str,
    port: int,
    root: Path,
    *,
    server_factory: Callable[..., ThreadingHTTPServer] = ThreadingHTTPServer,
) -> None:
    """Run the simple-index HTTP server until SIGTERM/SIGINT.

    ``server_factory`` is a test indirection — production callers
    accept the default ``ThreadingHTTPServer``.
    """
    handler_cls = make_handler(root)
    httpd = server_factory((host, port), handler_cls)

    def _shutdown(_signum: int, _frame: object) -> None:
        # ``httpd.shutdown()`` blocks until ``serve_forever()`` returns
        # and must therefore run on a *different* thread (Python docs:
        # http.server.BaseServer.shutdown). Calling it directly from
        # the signal handler — same thread as ``serve_forever()`` —
        # would deadlock.
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    # signal.signal() only works in the main thread; the strategy
    # module spawns this as a subprocess (its own main thread) so
    # production callers always succeed. Tests run serve() in a
    # daemon thread and call httpd.shutdown() directly, so the
    # ValueError fallback is only hit there.
    try:
        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)
    except ValueError:
        pass
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
