"""auntiepypi's first-party PEP 503 simple-index server.

v0.6.0 shipped the read-only slice: serves wheels and sdists from a
filesystem wheelhouse, loopback-only.

v0.7.0 adds optional HTTPS termination (``ssl_context=...``) and HTTP
Basic auth (``htpasswd_map=...``). When both are configured at
config-load time, the loopback restriction lifts. ``auntie publish``
remains deferred to v0.8.0.

Public surface lives in :mod:`auntiepypi._server.__init__` (this
module). The HTTP layer is :mod:`._app`; filesystem walk lives in
:mod:`._wheelhouse`; htpasswd parsing in :mod:`._auth`; TLS context
in :mod:`._tls`; CLI entry is :mod:`.__main__`.
"""

from __future__ import annotations

import signal
import ssl
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
    ssl_context: ssl.SSLContext | None = None,
    htpasswd_map: dict[str, bytes] | None = None,
    server_factory: Callable[..., ThreadingHTTPServer] = ThreadingHTTPServer,
) -> None:
    """Run the simple-index HTTP(S) server until SIGTERM/SIGINT.

    ``ssl_context`` (when set) wraps the listening socket via
    ``SSLContext.wrap_socket`` after ``bind_and_activate`` and before
    ``serve_forever`` — the standard idiom for stdlib HTTP+TLS.

    ``htpasswd_map`` (when set) gates every GET through Basic auth
    (see :mod:`._app`).

    ``server_factory`` is a test indirection — production callers
    accept the default ``ThreadingHTTPServer``.
    """
    handler_cls = make_handler(root, htpasswd_map=htpasswd_map)
    httpd = server_factory((host, port), handler_cls)
    if ssl_context is not None:
        # In-flight TLS connections may log noisy ssl.SSLError on
        # abrupt shutdown; that's acceptable. server_close() only
        # closes the listening socket; daemon threads handle in-flight.
        httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)

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
