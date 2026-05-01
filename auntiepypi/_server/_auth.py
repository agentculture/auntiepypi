"""HTTP Basic auth + Apache htpasswd parsing for the v0.7.0 server.

Three pieces:

1. :func:`parse_htpasswd` — read an Apache htpasswd file, return
   ``{username: bcrypt_hash_bytes}``. Bcrypt-only — entries with
   weaker schemes (SHA1, MD5, crypt) are rejected at load time with
   the offending line number. Silent-skip is how auth bypasses ship.

2. :class:`_AuthCache` — a tiny positive-only LRU keyed on the raw
   ``Authorization`` header string, with a TTL. Bcrypt cost-12 verify
   takes ~200–300 ms; caching positive results for a minute keeps
   ``pip install`` (which opens many connections) snappy without
   weakening the per-credential check.

3. :func:`authenticate_user` — parse ``Authorization: Basic <b64>``,
   bcrypt-verify against the htpasswd map, and write to the cache on
   success. Returns the authenticated **username** on success, or
   ``None`` for any failure mode (missing header, wrong scheme,
   malformed base64, unknown user, password mismatch). Never raises
   on malformed input — auth bypass via 500 is its own bug class.

4. :func:`verify_basic` — bool adapter over :func:`authenticate_user`
   for read-side callers that only care whether the request is
   authenticated, not who it is. Kept for v0.7.0 call-site stability.

The cache is a module-level singleton because the handler factory
re-binds htpasswd_map per server instance but verify_basic is called
once per request. A per-server cache would mean recomputing on every
fresh handler; the singleton is bounded (``maxsize=128``) and keyed on
the full header bytes, so cross-request sharing is safe — different
maps that happen to share a username won't collide because the cache
records "this exact header was once verified," not "this user is OK."
"""

from __future__ import annotations

import base64
import binascii
import threading
import time
from collections import OrderedDict
from pathlib import Path

import bcrypt

__all__ = [
    "HtpasswdError",
    "authenticate_user",
    "parse_htpasswd",
    "verify_basic",
]

_BCRYPT_PREFIXES = (b"$2y$", b"$2b$", b"$2a$")
_BASIC_PREFIX = "Basic "


class HtpasswdError(Exception):
    """Malformed entry in an Apache htpasswd file."""


def parse_htpasswd(path: Path) -> dict[str, bytes]:
    """Parse an Apache htpasswd file. Bcrypt-only.

    Returns ``{username: hash_bytes}``. Skips blank lines and
    ``#`` comments. Raises :class:`HtpasswdError` (with line number)
    on a non-bcrypt entry; raises :class:`FileNotFoundError` if the
    path doesn't exist.
    """
    table: dict[str, bytes] = {}
    with path.open("rb") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.rstrip(b"\r\n").strip()
            if not line or line.startswith(b"#"):
                continue
            sep = line.find(b":")
            if sep < 0:
                raise HtpasswdError(f"{path}: line {lineno}: missing ':' separator")
            user_b = line[:sep]
            hash_b = line[sep + 1 :]
            if not user_b or not hash_b:
                raise HtpasswdError(f"{path}: line {lineno}: empty user or hash")
            if not hash_b.startswith(_BCRYPT_PREFIXES):
                raise HtpasswdError(
                    f"{path}: line {lineno}: only bcrypt entries "
                    "($2y$/$2b$/$2a$) supported; regenerate with "
                    "`htpasswd -B`"
                )
            try:
                user = user_b.decode("utf-8")
            except UnicodeDecodeError as err:
                raise HtpasswdError(
                    f"{path}: line {lineno}: username is not valid UTF-8 ({err})"
                ) from err
            table[user] = hash_b
    return table


class _AuthCache:
    """Bounded positive-only LRU on raw Authorization header strings.

    Each entry stores ``(stored_at, user, expected_hash)``. A cache hit
    is honored only when the htpasswd map still maps ``user`` to the
    same ``expected_hash`` — that way credential rotation, user
    removal, or a fresh map (in tests) all naturally invalidate.

    Threadsafe — handlers run thread-per-request.
    """

    def __init__(self, *, maxsize: int = 128, ttl_seconds: float = 60.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[float, str, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[str, bytes] | None:
        """Return ``(user, expected_hash)`` for a fresh hit, else None."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stored_at, user, expected = entry
            if (time.monotonic() - stored_at) > self._ttl:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return user, expected

    def put(self, key: str, user: str, expected: bytes) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), user, expected)
            self._store.move_to_end(key)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)


_cache = _AuthCache()


def authenticate_user(raw_header: str, htpasswd_map: dict[str, bytes]) -> str | None:
    """Verify ``Authorization: Basic <b64>`` against ``htpasswd_map``.

    Returns the authenticated **username** when the header is
    well-formed Basic auth and the credentials bcrypt-match an entry
    in the map. Returns ``None`` for every other case — never raises.

    This is the v0.8.0 primitive: publish authz needs to know *which*
    user uploaded, so the bool-only :func:`verify_basic` from v0.7.0
    delegates here and adapts to bool for read-side callers that don't
    care about identity.
    """
    if not raw_header or not raw_header.startswith(_BASIC_PREFIX):
        return None
    cache_hit = _cache.get(raw_header)
    if cache_hit is not None:
        cached_user, cached_hash = cache_hit
        # Honor the cached hit only if the map still has the same
        # (user → expected_hash) binding. Rotation / user removal /
        # fresh map all invalidate naturally.
        if htpasswd_map.get(cached_user) == cached_hash:
            return cached_user
        # Fall through to re-verify under the current map.
    payload = raw_header[len(_BASIC_PREFIX) :].strip()
    try:
        decoded = base64.b64decode(payload, validate=True)
    except binascii.Error:
        # binascii.Error is a subclass of ValueError; catching the more
        # specific exception is sufficient and clearer.
        return None
    sep = decoded.find(b":")
    if sep < 0:
        return None
    user = decoded[:sep].decode("utf-8", errors="replace")
    password = decoded[sep + 1 :]
    expected = htpasswd_map.get(user)
    if expected is None:
        return None
    try:
        ok = bcrypt.checkpw(password, expected)
    except ValueError:
        # bcrypt raises on malformed hash, but parse_htpasswd already
        # screened the prefixes; this is defence-in-depth.
        return None
    if not ok:
        return None
    _cache.put(raw_header, user, expected)
    return user


def verify_basic(raw_header: str, htpasswd_map: dict[str, bytes]) -> bool:
    """Bool adapter over :func:`authenticate_user`.

    Read-side callers (``do_GET``) don't need the username; this
    keeps the v0.7.0 call sites unchanged.
    """
    return authenticate_user(raw_header, htpasswd_map) is not None
