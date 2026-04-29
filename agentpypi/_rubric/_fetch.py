"""Stdlib JSON fetch helper.

One job: GET a URL with a sensible timeout and return decoded JSON, or
raise :class:`FetchError` carrying a short reason and (when applicable)
the HTTP status. No retries, no on-disk cache.
"""

from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from agentpypi import __version__

_UA = f"agentpypi/{__version__} (+https://github.com/agentculture/agentpypi)"


class FetchError(Exception):
    """Raised when the fetch failed. Carries a short reason and status."""

    def __init__(self, reason: str, *, status: int | None = None) -> None:  # noqa: B042
        super().__init__(reason)
        self.reason = reason
        self.status = status


def get_json(url: str, *, timeout: float = 5.0) -> dict:
    """GET ``url``, return decoded JSON dict, or raise :class:`FetchError`."""
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        # URL is constructed by callers from constants + URL-safe package
        # names; no caller-controlled scheme.
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 # nosec B310
            raw = resp.read()
    except HTTPError as err:
        raise FetchError(f"http {err.code}", status=err.code) from err
    except (URLError, socket.timeout, OSError) as err:
        raise FetchError(f"fetch failed: {err.__class__.__name__}: {err}") from err

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise FetchError(f"unexpected response shape: {err}") from err
