"""Tests for `auntiepypi._server._auth.authenticate_user` (v0.8.0).

The v0.8.0 primitive returns the username (or ``None``) instead of a
bool. Every behavioural case from ``verify_basic`` has a counterpart
here — wrong creds → None; valid → "alice"; cache hit returns the
right user; rotation invalidates.
"""

from __future__ import annotations

import base64

import bcrypt
import pytest

from auntiepypi._server import _auth
from auntiepypi._server._auth import (
    PublishAuthzError,
    assert_publish_users_in_htpasswd,
    authenticate_user,
    verify_basic,
)


def _bcrypt_hash(password: str) -> bytes:
    return bcrypt.hashpw(  # NOSONAR python:S5344 - test fixture; production cost ≥ 12
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),  # NOSONAR python:S5344
    )


def _basic_header(user: str, password: str) -> str:
    creds = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(creds).decode("ascii")


# --------- happy paths ---------


def test_authenticate_user_returns_username_on_valid_creds():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    user = authenticate_user(_basic_header("alice", "secret"), htp)
    assert user == "alice"


def test_authenticate_user_picks_correct_user_among_multiple():
    htp = {
        "alice": _bcrypt_hash("alice-pw"),
        "bob": _bcrypt_hash("bob-pw"),
    }
    assert authenticate_user(_basic_header("alice", "alice-pw"), htp) == "alice"
    assert authenticate_user(_basic_header("bob", "bob-pw"), htp) == "bob"


# --------- failure modes — every one returns None, never raises ---------


def test_authenticate_user_missing_header_returns_none():
    assert authenticate_user("", {"alice": _bcrypt_hash("pw")}) is None


def test_authenticate_user_non_basic_scheme_returns_none():
    assert authenticate_user("Bearer foo", {"alice": _bcrypt_hash("pw")}) is None


def test_authenticate_user_malformed_b64_returns_none():
    assert authenticate_user("Basic not_b64!!", {"alice": _bcrypt_hash("pw")}) is None


def test_authenticate_user_wrong_password_returns_none():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    assert authenticate_user(_basic_header("alice", "wrong"), htp) is None


def test_authenticate_user_unknown_user_returns_none():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    assert authenticate_user(_basic_header("eve", "secret"), htp) is None


def test_authenticate_user_empty_table_returns_none():
    assert authenticate_user(_basic_header("alice", "x"), {}) is None


def test_authenticate_user_decoded_payload_without_colon_returns_none():
    # Authorization: Basic <b64("nocolon")>
    payload = base64.b64encode(b"nocolon").decode("ascii")
    assert authenticate_user(f"Basic {payload}", {"alice": _bcrypt_hash("x")}) is None


# --------- cache contract ---------


def test_authenticate_user_cache_hit_returns_same_user():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    header = _basic_header("alice", "secret")
    # Prime the cache.
    assert authenticate_user(header, htp) == "alice"
    # Second call should reuse the cache (still alice).
    assert authenticate_user(header, htp) == "alice"


def test_authenticate_user_cache_invalidated_when_password_rotates():
    """If the operator rotates alice's password and reloads the map,
    the next authenticate_user call must re-verify, not return the
    stale cached username with the old hash.
    """
    old_hash = _bcrypt_hash("old-pw")
    new_hash = _bcrypt_hash("new-pw")
    header = _basic_header("alice", "old-pw")
    # Authenticate under old creds — populates the cache.
    assert authenticate_user(header, {"alice": old_hash}) == "alice"
    # Rotate the map; the cached entry's expected_hash no longer matches.
    # Old creds must now fail to authenticate (re-verify against new hash).
    assert authenticate_user(header, {"alice": new_hash}) is None
    # Fresh creds against the new hash succeed.
    new_header = _basic_header("alice", "new-pw")
    assert authenticate_user(new_header, {"alice": new_hash}) == "alice"


def test_authenticate_user_cache_invalidated_when_user_removed():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    header = _basic_header("alice", "secret")
    assert authenticate_user(header, htp) == "alice"
    # Remove alice (operator ran `htpasswd -D`).
    assert authenticate_user(header, {}) is None


# --------- verify_basic delegates to authenticate_user ---------


def test_verify_basic_is_thin_bool_adapter():
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    valid = _basic_header("alice", "secret")
    invalid = _basic_header("alice", "wrong")
    assert verify_basic(valid, htp) is True
    assert verify_basic(invalid, htp) is False


def test_verify_basic_consistent_with_authenticate_user(monkeypatch):
    """For any inputs, ``verify_basic == (authenticate_user is not None)``."""
    htp = {"alice": _bcrypt_hash("secret")}  # noqa: S106
    cases = [
        "",
        "Bearer foo",
        "Basic not_b64!!",
        _basic_header("alice", "secret"),
        _basic_header("alice", "wrong"),
        _basic_header("eve", "secret"),
    ]
    for header in cases:
        assert verify_basic(header, htp) == (authenticate_user(header, htp) is not None)


# --------- module surface ---------


def test_authenticate_user_in_module_all():
    assert "authenticate_user" in _auth.__all__


# --------- v0.8.0 publish-users / htpasswd cross-check ---------


def _write_htpasswd(path, users):
    """Write a tiny bcrypt-hashed htpasswd with the given user list."""
    lines = []
    for user in users:
        h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4))  # noqa: S106
        lines.append(user.encode() + b":" + h)
    path.write_bytes(b"\n".join(lines) + b"\n")


def test_assert_publish_users_in_htpasswd_passes_for_complete_set(tmp_path):
    htp = tmp_path / "htp"
    _write_htpasswd(htp, ["alice", "bob"])
    # No raise.
    assert_publish_users_in_htpasswd(htp, ("alice", "bob"))


def test_assert_publish_users_in_htpasswd_raises_on_missing_user(tmp_path):
    htp = tmp_path / "htp"
    _write_htpasswd(htp, ["alice"])
    with pytest.raises(PublishAuthzError, match=r"'eve'"):
        assert_publish_users_in_htpasswd(htp, ("alice", "eve"))


def test_assert_publish_users_in_htpasswd_noop_when_publish_users_empty(tmp_path):
    htp = tmp_path / "htp"
    _write_htpasswd(htp, ["alice"])
    # Empty → no read, no raise.
    assert_publish_users_in_htpasswd(htp, ())


def test_assert_publish_users_in_htpasswd_noop_when_htpasswd_none(tmp_path):
    """Caller's existence check (``_verify_tls_auth_paths``) handles
    the htpasswd-unset case before we get here."""
    assert_publish_users_in_htpasswd(None, ("alice",))


def test_assert_publish_users_in_htpasswd_silent_when_htpasswd_unreadable(tmp_path):
    """A missing file produces a clearer error from the readability
    pre-check; this helper falls through silently rather than
    double-reporting."""
    missing = tmp_path / "no-such.htpasswd"
    # No raise.
    assert_publish_users_in_htpasswd(missing, ("alice",))
