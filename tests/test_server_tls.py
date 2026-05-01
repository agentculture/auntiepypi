"""Tests for `auntiepypi._server._tls` — SSLContext builder.

Plus end-to-end HTTPS tests for `serve()` itself, exercising the
cert/auth integration in one shot.
"""

from __future__ import annotations

import base64
import ssl
import threading
import time
from http.client import HTTPSConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import bcrypt
import pytest

from auntiepypi._server import serve
from auntiepypi._server._tls import build_ssl_context


def test_build_ssl_context_returns_tls_server(tls_cert_pair):
    cert, key = tls_cert_pair
    ctx = build_ssl_context(cert, key)
    assert isinstance(ctx, ssl.SSLContext)
    # Server-side context.
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_2


def test_build_ssl_context_loads_cert_chain(tls_cert_pair):
    """Successful load — sanity check that we don't raise."""
    cert, key = tls_cert_pair
    build_ssl_context(cert, key)  # should not raise


def test_build_ssl_context_missing_cert_raises(tmp_path: Path, tls_cert_pair):
    """A non-existent cert path raises FileNotFoundError."""
    _, key = tls_cert_pair
    with pytest.raises(FileNotFoundError):
        build_ssl_context(tmp_path / "no-such-cert.pem", key)


def test_build_ssl_context_missing_key_raises(tmp_path: Path, tls_cert_pair):
    cert, _ = tls_cert_pair
    with pytest.raises(FileNotFoundError):
        build_ssl_context(cert, tmp_path / "no-such-key.pem")


def test_build_ssl_context_garbage_pem_raises(tmp_path: Path):
    """Malformed PEM bytes raise ssl.SSLError (not silent)."""
    bad_cert = tmp_path / "bad.pem"
    bad_key = tmp_path / "bad-key.pem"
    bad_cert.write_text("-----BEGIN CERTIFICATE-----\nnot pem data\n")
    bad_key.write_text("-----BEGIN PRIVATE KEY-----\nnot key data\n")
    with pytest.raises((ssl.SSLError, ValueError)):
        build_ssl_context(bad_cert, bad_key)


def test_build_ssl_context_minimum_version_pinned(tls_cert_pair):
    """TLS minimum is pinned to 1.2 explicitly — older protocols are
    out of band even if the local OpenSSL would tolerate them.
    """
    cert, key = tls_cert_pair
    ctx = build_ssl_context(cert, key)
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


# --------- end-to-end serve() with TLS + auth ---------


def _bcrypt_hash(password: str) -> bytes:
    # cost-4: test-fixture speed; production uses ≥12 (verify_basic
    # honors whatever cost is in the stored hash).
    return bcrypt.hashpw(  # NOSONAR python:S5344
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),  # NOSONAR python:S5344
    )


def _basic_header(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


def _wait_for_https(host: str, port: int, ctx: ssl.SSLContext, timeout: float = 3.0):
    """Poll until the HTTPS server accepts a connection or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = HTTPSConnection(host, port, context=ctx, timeout=0.5)
            conn.request("GET", "/")
            conn.getresponse().read()
            conn.close()
            return
        except OSError:  # ssl.SSLError is a subclass
            time.sleep(0.05)
    raise RuntimeError("server never became reachable")


def test_serve_with_tls_and_auth_end_to_end(tmp_path: Path, tls_cert_pair):
    """Spin up serve() with a real cert + htpasswd; exercise 200/401.

    The factory captures the ``ThreadingHTTPServer`` instance so the
    test can call ``shutdown()`` / ``server_close()`` deterministically
    in ``finally``, then ``join()`` the runner thread. This avoids
    leaking a background thread + bound socket across tests.
    """
    cert, key = tls_cert_pair
    ssl_ctx = build_ssl_context(cert, key)
    htpasswd_map = {"alice": _bcrypt_hash("fixture-pw")}

    bind_host = "127.0.0.1"
    captured: dict[str, ThreadingHTTPServer] = {}

    def factory(addr, handler_cls):  # noqa: ANN001
        srv = ThreadingHTTPServer(addr, handler_cls)
        captured["srv"] = srv
        return srv

    thread = threading.Thread(
        target=serve,
        args=(bind_host, 0, tmp_path),
        kwargs={
            "ssl_context": ssl_ctx,
            "htpasswd_map": htpasswd_map,
            "server_factory": factory,
        },
        daemon=True,
    )
    thread.start()

    # Wait for bind.
    deadline = time.monotonic() + 3.0
    while "srv" not in captured and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "srv" in captured, "server never bound"
    srv = captured["srv"]
    port = srv.server_address[1]

    client_ctx = ssl._create_unverified_context()  # noqa: S323  # NOSONAR python:S4830
    try:
        _wait_for_https(bind_host, port, client_ctx)

        # No creds → 401
        conn = HTTPSConnection(bind_host, port, context=client_ctx, timeout=2)
        try:
            conn.request("GET", "/simple/")
            resp = conn.getresponse()
            assert resp.status == 401
            assert "Basic" in resp.getheader("WWW-Authenticate")
            resp.read()
        finally:
            conn.close()

        # Valid creds → 200
        conn = HTTPSConnection(bind_host, port, context=client_ctx, timeout=2)
        try:
            conn.request(
                "GET",
                "/simple/",
                headers={"Authorization": _basic_header("alice", "fixture-pw")},
            )
            resp = conn.getresponse()
            assert resp.status == 200
            resp.read()
        finally:
            conn.close()
    finally:
        # Clean shutdown — serve() unblocks from serve_forever().
        srv.shutdown()
        thread.join(timeout=5)
        assert not thread.is_alive(), "serve() did not exit cleanly"
