"""TLS context builder for the first-party HTTPS server.

Thin wrapper over :class:`ssl.SSLContext` that:

- selects ``PROTOCOL_TLS_SERVER`` (modern server-side context)
- pins ``minimum_version`` to TLS 1.2 explicitly (stdlib default on
  3.12 is already sane, but be explicit so a downgraded OpenSSL
  doesn't silently accept TLS 1.0/1.1)
- loads the operator-supplied PEM cert + key

Cert/key files are loaded once at server startup. Auntie has no
file-watcher; rotating the PEMs requires ``auntie restart``. The
operator runs ``mkcert`` / ``certbot`` / their internal CA.
"""

from __future__ import annotations

import ssl
from pathlib import Path

__all__ = ["build_ssl_context"]


def build_ssl_context(cert: Path, key: Path) -> ssl.SSLContext:
    """Return a TLS server context loaded with ``cert`` + ``key``.

    Raises:
        FileNotFoundError: when either path doesn't exist.
        ssl.SSLError: when the PEM is malformed or the cert/key don't
            pair.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return ctx
