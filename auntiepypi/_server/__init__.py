"""auntiepypi's first-party PEP 503 simple-index server.

v0.6.0 ships the read-only slice: serves wheels and sdists from a
filesystem wheelhouse. Loopback-only by config-load-time enforcement.
``auntie publish``, HTTPS, and basic-auth are deferred to v0.7.0.

Public surface lives in :mod:`auntiepypi._server.__init__` (this
module). The HTTP layer is :mod:`._app`; filesystem walk lives in
:mod:`._wheelhouse`; CLI entry is :mod:`.__main__`.
"""

from __future__ import annotations
