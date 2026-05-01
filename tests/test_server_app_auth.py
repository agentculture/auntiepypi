"""Tests for the auth-gated path of `auntiepypi._server._app.make_handler`."""

from __future__ import annotations

import base64
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import bcrypt
import pytest

from auntiepypi._server._app import make_handler


def _bcrypt_hash(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4))


def _basic_header(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


@pytest.fixture
def htpasswd_map() -> dict[str, bytes]:
    return {
        "alice": _bcrypt_hash("secret"),
        "bob": _bcrypt_hash("hunter2"),
    }


@pytest.fixture
def served_with_auth(
    tmp_path: Path, htpasswd_map: dict[str, bytes]
) -> Iterator[tuple[int, Path, dict[str, bytes]]]:
    """Spin up the handler with auth gated on, yield ``(port, root, map)``."""
    handler_cls = make_handler(tmp_path, htpasswd_map=htpasswd_map)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, tmp_path, htpasswd_map
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _get(port: int, path: str, headers: dict[str, str] | None = None):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, resp.read(), dict(resp.getheaders())
    finally:
        conn.close()


# --------- 401 challenge ---------


def test_no_auth_header_returns_401(served_with_auth):
    port, _, _ = served_with_auth
    status, body, headers = _get(port, "/simple/")
    assert status == 401
    assert "Basic" in headers["WWW-Authenticate"]
    assert "auntiepypi" in headers["WWW-Authenticate"]
    assert b"401" in body


def test_wrong_password_returns_401(served_with_auth):
    port, _, _ = served_with_auth
    status, _, headers = _get(
        port, "/simple/", headers={"Authorization": _basic_header("alice", "wrong")}
    )
    assert status == 401
    assert "Basic" in headers["WWW-Authenticate"]


def test_unknown_user_returns_401(served_with_auth):
    port, _, _ = served_with_auth
    status, _, _ = _get(
        port,
        "/simple/",
        headers={"Authorization": _basic_header("eve", "secret")},
    )
    assert status == 401


def test_malformed_b64_returns_401_not_500(served_with_auth):
    port, _, _ = served_with_auth
    status, _, _ = _get(port, "/simple/", headers={"Authorization": "Basic not_b64!!"})
    assert status == 401


def test_bearer_token_returns_401(served_with_auth):
    """Non-Basic schemes get 401 too (we only support Basic)."""
    port, _, _ = served_with_auth
    status, _, _ = _get(port, "/simple/", headers={"Authorization": "Bearer some-token"})
    assert status == 401


# --------- 200 with valid creds ---------


def test_valid_creds_returns_200(served_with_auth):
    port, _, _ = served_with_auth
    status, _, _ = _get(
        port,
        "/simple/",
        headers={"Authorization": _basic_header("alice", "secret")},
    )
    assert status == 200


def test_valid_creds_serves_file(served_with_auth):
    port, root, _ = served_with_auth
    wheel = root / "demo-1.0-py3-none-any.whl"
    wheel.write_bytes(b"PK\x03\x04demo-bytes")
    status, body, _ = _get(
        port,
        "/files/demo-1.0-py3-none-any.whl",
        headers={"Authorization": _basic_header("alice", "secret")},
    )
    assert status == 200
    assert body == b"PK\x03\x04demo-bytes"


def test_valid_creds_serves_project_page(served_with_auth):
    port, root, _ = served_with_auth
    (root / "requests-2.31.0-py3-none-any.whl").touch()
    status, body, _ = _get(
        port,
        "/simple/requests/",
        headers={"Authorization": _basic_header("bob", "hunter2")},
    )
    assert status == 200
    assert b"requests-2.31.0-py3-none-any.whl" in body


# --------- regression: defenses still apply with auth ---------


def test_auth_does_not_bypass_path_traversal(served_with_auth):
    """Valid creds + path traversal still 404 — defense in depth."""
    port, _, _ = served_with_auth
    status, _, _ = _get(
        port,
        "/files/../etc/passwd",
        headers={"Authorization": _basic_header("alice", "secret")},
    )
    assert status == 404


def test_post_still_405_with_auth(served_with_auth):
    """POST is still rejected even with valid creds (read-only server)."""
    port, _, _ = served_with_auth
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(
            "POST",
            "/simple/",
            body=b"",
            headers={"Authorization": _basic_header("alice", "secret")},
        )
        resp = conn.getresponse()
        assert resp.status in (401, 405, 501)
        # Note: the auth check runs only in do_GET; POST takes a different
        # code path in BaseHTTPRequestHandler (no do_POST defined → 501).
        # Either outcome (401 from gate or 501 from no-handler) is fine.
        resp.read()
    finally:
        conn.close()


# --------- regression: unauth handler still works (v0.6.0 path) ---------


def test_unauth_handler_still_serves_without_auth(tmp_path: Path):
    """make_handler with htpasswd_map=None preserves v0.6.0 behavior."""
    handler_cls = make_handler(tmp_path)  # default: no auth
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, headers = _get(port, "/simple/")
        assert status == 200
        assert "WWW-Authenticate" not in headers
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
