"""Tests for `auntiepypi._server._auth` — htpasswd parser + basic-auth verifier."""

from __future__ import annotations

import base64
import time
from pathlib import Path

import bcrypt
import pytest

from auntiepypi._server._auth import (
    HtpasswdError,
    _AuthCache,
    parse_htpasswd,
    verify_basic,
)


def _bcrypt_hash(password: str) -> bytes:
    """Real bcrypt hash with a low cost (4) for fast tests."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4))


def _basic_header(user: str, password: str) -> str:
    creds = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")


# --------- parse_htpasswd ---------


def test_parse_htpasswd_single_user(tmp_path: Path):
    h = _bcrypt_hash("secret")
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:" + h + b"\n")
    table = parse_htpasswd(htp)
    assert "alice" in table
    assert table["alice"] == h


def test_parse_htpasswd_multiple_users(tmp_path: Path):
    h1 = _bcrypt_hash("pw1")
    h2 = _bcrypt_hash("pw2")
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:" + h1 + b"\nbob:" + h2 + b"\n")
    table = parse_htpasswd(htp)
    assert table.keys() == {"alice", "bob"}


def test_parse_htpasswd_skips_blank_lines_and_comments(tmp_path: Path):
    h = _bcrypt_hash("x")
    htp = tmp_path / "htp"
    htp.write_bytes(
        b"# leading comment\n"
        b"\n"
        b"  \n"
        b"alice:" + h + b"\n"
        b"# trailing comment\n"
    )
    table = parse_htpasswd(htp)
    assert table.keys() == {"alice"}


def test_parse_htpasswd_strips_crlf(tmp_path: Path):
    h = _bcrypt_hash("x")
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:" + h + b"\r\n")
    table = parse_htpasswd(htp)
    assert "alice" in table
    # Hash must not include the trailing \r.
    assert not table["alice"].endswith(b"\r")


def test_parse_htpasswd_rejects_unknown_algo(tmp_path: Path):
    """SHA1 / MD5 / crypt entries are weak; we hard-reject at load time."""
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:{SHA}base64junk\n")
    with pytest.raises(HtpasswdError, match="line 1"):
        parse_htpasswd(htp)


def test_parse_htpasswd_rejects_plaintext(tmp_path: Path):
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:plaintextpassword\n")
    with pytest.raises(HtpasswdError, match="line 1"):
        parse_htpasswd(htp)


def test_parse_htpasswd_rejects_missing_colon(tmp_path: Path):
    htp = tmp_path / "htp"
    htp.write_bytes(b"this-has-no-colon\n")
    with pytest.raises(HtpasswdError, match="line 1"):
        parse_htpasswd(htp)


def test_parse_htpasswd_accepts_2y_2b_2a_prefixes(tmp_path: Path):
    """Apache htpasswd uses $2y$ historically; bcrypt's modern default
    is $2b$. Both must work; $2a$ legacy too.
    """
    h = _bcrypt_hash("x")
    # Hashes from python-bcrypt are $2b$; transcode the prefix to test
    # $2y$ and $2a$ acceptance.
    h_2y = b"$2y$" + h[4:]
    h_2a = b"$2a$" + h[4:]
    htp = tmp_path / "htp"
    htp.write_bytes(b"alice:" + h + b"\nbob:" + h_2y + b"\ncarol:" + h_2a + b"\n")
    table = parse_htpasswd(htp)
    assert table.keys() == {"alice", "bob", "carol"}


def test_parse_htpasswd_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        parse_htpasswd(tmp_path / "no-such-file")


def test_parse_htpasswd_line_number_in_error(tmp_path: Path):
    """Error names the line so operators can fix the right entry."""
    h = _bcrypt_hash("x")
    htp = tmp_path / "htp"
    htp.write_bytes(b"# comment\nalice:" + h + b"\nbob:bad-not-bcrypt\n")
    with pytest.raises(HtpasswdError, match="line 3"):
        parse_htpasswd(htp)


# --------- verify_basic ---------


def test_verify_basic_missing_header_returns_false():
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic("", table) is False


def test_verify_basic_non_basic_scheme_returns_false():
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic("Bearer some-token", table) is False


def test_verify_basic_malformed_b64_returns_false_not_500():
    """A bad base64 string must not raise — basic-auth bypass via
    crash is its own bug class."""
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic("Basic !!!not_b64!!!", table) is False


def test_verify_basic_valid_creds_returns_true():
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic(_basic_header("alice", "secret"), table) is True


def test_verify_basic_wrong_password_returns_false():
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic(_basic_header("alice", "wrong"), table) is False


def test_verify_basic_unknown_user_returns_false():
    table = {"alice": _bcrypt_hash("secret")}
    assert verify_basic(_basic_header("eve", "secret"), table) is False


def test_verify_basic_empty_table_returns_false():
    assert verify_basic(_basic_header("alice", "secret"), {}) is False


def test_verify_basic_password_with_colon_works():
    """`:` in a password must round-trip — split the credential pair on
    the FIRST colon only.
    """
    table = {"alice": _bcrypt_hash("pa:ss:wd")}
    assert verify_basic(_basic_header("alice", "pa:ss:wd"), table) is True


# --------- _AuthCache ---------


def test_authcache_returns_miss_for_unknown_key():
    cache = _AuthCache(maxsize=8, ttl_seconds=60)
    assert cache.get("never-seen") is None


def test_authcache_returns_hit_for_stored_key():
    cache = _AuthCache(maxsize=8, ttl_seconds=60)
    cache.put("Basic abc", "alice", b"hash-bytes")
    hit = cache.get("Basic abc")
    assert hit == ("alice", b"hash-bytes")


def test_authcache_evicts_when_full():
    cache = _AuthCache(maxsize=2, ttl_seconds=60)
    cache.put("a", "u1", b"h1")
    cache.put("b", "u2", b"h2")
    cache.put("c", "u3", b"h3")  # should evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == ("u2", b"h2")
    assert cache.get("c") == ("u3", b"h3")


def test_authcache_expires_after_ttl(monkeypatch):
    cache = _AuthCache(maxsize=8, ttl_seconds=1)
    fake_time = [1000.0]
    monkeypatch.setattr("auntiepypi._server._auth.time.monotonic",
                        lambda: fake_time[0])
    cache.put("k", "u", b"h")
    assert cache.get("k") == ("u", b"h")
    fake_time[0] += 2.0  # past TTL
    assert cache.get("k") is None


def test_verify_basic_caches_positive_result():
    """A valid header is verified once; subsequent calls must short-circuit
    bcrypt by checking the cache.
    """
    table = {"alice": _bcrypt_hash("secret")}
    header = _basic_header("alice", "secret")
    # First call goes through bcrypt.
    t0 = time.perf_counter()
    assert verify_basic(header, table) is True
    elapsed_first = time.perf_counter() - t0
    # Second call should hit the cache (much faster).
    t1 = time.perf_counter()
    assert verify_basic(header, table) is True
    elapsed_second = time.perf_counter() - t1
    # Cost-4 bcrypt is fast (~1ms), but cache hits should be ~10x faster
    # at minimum. Use a generous ratio to avoid flakes.
    assert elapsed_second < elapsed_first / 2 or elapsed_second < 0.001


def test_verify_basic_cache_does_not_leak_across_maps():
    """A cached True for header X under map A must not honor under
    map B that doesn't contain the user. Critical safety property.
    """
    table_a = {"alice": _bcrypt_hash("secret")}
    header = _basic_header("alice", "secret")
    assert verify_basic(header, table_a) is True
    # Now the same header against an empty map.
    assert verify_basic(header, {}) is False
    # And against a map that has alice but with a rotated hash.
    table_c = {"alice": _bcrypt_hash("different-password")}
    assert verify_basic(header, table_c) is False
