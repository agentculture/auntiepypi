"""``python -m auntiepypi._server`` entry.

Argparse → :func:`auntiepypi._server.serve`. The ``auntie`` CLI's
lifecycle strategy spawns this module via ``sys.executable -m
auntiepypi._server …`` so we don't depend on a console-script entry
point.

v0.7.0 adds ``--cert`` / ``--key`` (TLS PEM paths, both required
together) and ``--htpasswd`` (Apache htpasswd path). When both
``--cert`` and ``--key`` are supplied, the server runs HTTPS;
``--htpasswd`` enables Basic auth. Either alone vs. combined is
not enforced here — the ``[tool.auntiepypi.local]`` validator in
:mod:`auntiepypi._detect._config` is the source of truth on legality.
This module only enforces ``--cert``+``--key`` pairing as a usability
guard against accidentally invoking with a half-configured TLS pair.

v0.8.0 adds ``--publish-user NAME`` (repeatable) and
``--max-upload-bytes N``: the publish allowlist and per-request body
cap. Defaults preserve v0.7.0 read-only behavior — no ``--publish-user``
means no one can POST. The cross-checks (publish_users requires
htpasswd, names must exist in htpasswd) live in the config-load
validator; this module just passes the values through.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from auntiepypi._server import serve
from auntiepypi._server._auth import parse_htpasswd
from auntiepypi._server._config import _DEFAULT_MAX_UPLOAD_BYTES
from auntiepypi._server._tls import build_ssl_context


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m auntiepypi._server",
        description="auntiepypi first-party PEP 503 simple-index server",
    )
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address; non-loopback requires --cert/--key + --htpasswd",
    )
    p.add_argument("--port", type=int, default=3141, help="bind port")
    p.add_argument(
        "--root",
        type=Path,
        required=True,
        help="wheelhouse directory served by /simple/ and /files/",
    )
    p.add_argument(
        "--cert",
        type=Path,
        default=None,
        help="PEM certificate path (required together with --key)",
    )
    p.add_argument(
        "--key",
        type=Path,
        default=None,
        help="PEM private-key path (required together with --cert)",
    )
    p.add_argument(
        "--htpasswd",
        type=Path,
        default=None,
        help="Apache htpasswd file (bcrypt-only) for HTTP Basic auth",
    )
    p.add_argument(
        "--publish-user",
        action="append",
        default=[],
        metavar="NAME",
        help="username allowed to POST uploads (repeatable; "
        "requires --htpasswd; empty list = no one publishes)",
    )
    p.add_argument(
        "--max-upload-bytes",
        type=int,
        default=_DEFAULT_MAX_UPLOAD_BYTES,
        help=f"reject uploads larger than this (bytes; default " f"{_DEFAULT_MAX_UPLOAD_BYTES})",
    )
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)

    # Pairing check — both halves of TLS must be supplied together.
    if (args.cert is None) != (args.key is None):
        missing = "key" if args.cert is not None else "cert"
        print(
            f"--cert and --key must be set together; missing --{missing}",
            file=sys.stderr,
        )
        raise SystemExit(2)

    ssl_context = None
    if args.cert is not None and args.key is not None:
        ssl_context = build_ssl_context(args.cert, args.key)

    htpasswd_map = None
    if args.htpasswd is not None:
        htpasswd_map = parse_htpasswd(args.htpasswd)

    serve(
        args.host,
        args.port,
        args.root,
        ssl_context=ssl_context,
        htpasswd_map=htpasswd_map,
        publish_users=tuple(args.publish_user),
        max_upload_bytes=args.max_upload_bytes,
    )


if __name__ == "__main__":  # pragma: no cover — executed via -m
    main()
