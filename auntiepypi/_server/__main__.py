"""``python -m auntiepypi._server`` entry.

Argparse → :func:`auntiepypi._server.serve`. The ``auntie`` CLI's
lifecycle strategy spawns this module via ``sys.executable -m
auntiepypi._server …`` so we don't depend on a console-script entry
point.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from auntiepypi._server import serve


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m auntiepypi._server",
        description="auntiepypi first-party PEP 503 simple-index server (read-only)",
    )
    p.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind address; v0.6.0 enforces loopback at config-load time",
    )
    p.add_argument("--port", type=int, default=3141, help="bind port")
    p.add_argument(
        "--root",
        type=Path,
        required=True,
        help="wheelhouse directory served by /simple/ and /files/",
    )
    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    serve(args.host, args.port, args.root)


if __name__ == "__main__":  # pragma: no cover — executed via -m
    main()
