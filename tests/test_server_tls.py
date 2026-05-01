"""Tests for `auntiepypi._server._tls` — SSLContext builder."""

from __future__ import annotations

import ssl
from pathlib import Path

import pytest

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
