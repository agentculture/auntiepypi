"""Tests for `[tool.auntiepypi.local]` loader and `LocalConfig`."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from auntiepypi._detect._config import (
    ServerConfigError,
    _is_loopback,
    load_local_config,
)
from auntiepypi._server._config import LocalConfig, default_root

# --------- default_root() ---------


def test_default_root_uses_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_root() == tmp_path / "auntiepypi" / "wheels"


def test_default_root_falls_back_to_local_share(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", "/fake/home")
    assert default_root() == Path("/fake/home/.local/share/auntiepypi/wheels")


# --------- LocalConfig defaults ---------


def test_localconfig_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = LocalConfig()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_localconfig_is_frozen():
    from dataclasses import FrozenInstanceError

    cfg = LocalConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.port = 9999  # type: ignore[misc]


# --------- _is_loopback helper ---------


def test_is_loopback_recognizes_aliases():
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("127.0.0.5")  # anywhere in 127.0.0.0/8
    assert _is_loopback("localhost")
    assert _is_loopback("LocalHost")  # case-insensitive
    assert _is_loopback("::1")


def test_is_loopback_rejects_public():
    # The hardcoded IPs below are fixtures asserting that _is_loopback
    # rejects them; they are never used to dial out. The trailing
    # markers pin the linter rule on each line so future linter
    # updates don't silently flag the surrounding test as a
    # real-world IP usage.
    assert not _is_loopback("0.0.0.0")  # noqa: S104
    assert not _is_loopback("10.0.0.1")  # NOSONAR python:S1313
    assert not _is_loopback("8.8.8.8")  # NOSONAR python:S1313
    assert not _is_loopback("example.com")
    assert not _is_loopback("")


# --------- load_local_config() ---------


def _write_pyproject(path: Path, body: str) -> None:
    (path / "pyproject.toml").write_text(textwrap.dedent(body))


def test_load_local_config_no_pyproject(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cfg = load_local_config(tmp_path)
    # Defaults apply.
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_load_local_config_table_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi]
        scan_processes = false
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 3141


def test_load_local_config_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    wheel_dir = tmp_path / "wheels-custom"
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        host = "::1"
        port = 9999
        root = "{wheel_dir}"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "::1"
    assert cfg.port == 9999
    assert cfg.root == wheel_dir


def test_load_local_config_partial_override(tmp_path, monkeypatch):
    """Setting just `port` keeps host and root at defaults."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = 4242
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 4242
    assert cfg.root == tmp_path / "auntiepypi" / "wheels"


def test_load_local_config_expands_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        root = "~/wheels"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.root == tmp_path / "wheels"


def test_load_local_config_rejects_non_loopback_without_tls_or_auth(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        """,
    )
    with pytest.raises(ServerConfigError, match="non-loopback binds require BOTH"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_public_ip_without_tls_or_auth(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "10.0.0.5"
        """,
    )
    with pytest.raises(ServerConfigError, match="non-loopback binds require BOTH"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_bad_port_type(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = "not-an-int"
        """,
    )
    with pytest.raises(ServerConfigError, match="port"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_port_out_of_range(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        port = 70000
        """,
    )
    with pytest.raises(ServerConfigError, match="port"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_non_table(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi]
        local = "not a table"
        """,
    )
    with pytest.raises(ServerConfigError, match="must be a table"):
        load_local_config(tmp_path)


def test_load_local_config_localhost_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "localhost"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "localhost"


# --------- LocalConfig.tls_enabled / .auth_enabled (v0.7.0) ---------


def test_localconfig_tls_auth_default_off():
    """v0.6.0 pyprojects (no cert/key/htpasswd) get tls_enabled = auth_enabled = False."""
    cfg = LocalConfig()
    assert cfg.cert is None
    assert cfg.key is None
    assert cfg.htpasswd is None
    assert cfg.tls_enabled is False
    assert cfg.auth_enabled is False


def test_localconfig_tls_enabled_requires_both_cert_and_key(tmp_path):
    """tls_enabled is True only when both cert AND key are set."""
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    assert LocalConfig(cert=cert).tls_enabled is False
    assert LocalConfig(key=key).tls_enabled is False
    assert LocalConfig(cert=cert, key=key).tls_enabled is True


def test_localconfig_auth_enabled_when_htpasswd_set(tmp_path):
    htp = tmp_path / "htpasswd"
    assert LocalConfig().auth_enabled is False
    assert LocalConfig(htpasswd=htp).auth_enabled is True


def test_localconfig_full_bundle(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htpasswd"
    cfg = LocalConfig(cert=cert, key=key, htpasswd=htp)
    assert cfg.tls_enabled is True
    assert cfg.auth_enabled is True
    assert cfg.cert == cert
    assert cfg.key == key
    assert cfg.htpasswd == htp


# --------- v0.7.0 cert/key/htpasswd field loading ---------


def test_load_local_config_loads_cert_key_htpasswd(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htpasswd"
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        cert = "{cert}"
        key  = "{key}"
        htpasswd = "{htp}"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.cert == cert
    assert cfg.key == key
    assert cfg.htpasswd == htp
    assert cfg.tls_enabled is True
    assert cfg.auth_enabled is True


def test_load_local_config_expands_tilde_in_tls_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        cert = "~/c.pem"
        key  = "~/k.pem"
        htpasswd = "~/htpasswd"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.cert == tmp_path / "c.pem"
    assert cfg.key == tmp_path / "k.pem"
    assert cfg.htpasswd == tmp_path / "htpasswd"


def test_load_local_config_rejects_cert_non_string(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        cert = 42
        """,
    )
    with pytest.raises(ServerConfigError, match="cert"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_htpasswd_non_string(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        htpasswd = false
        """,
    )
    with pytest.raises(ServerConfigError, match="htpasswd"):
        load_local_config(tmp_path)


# --------- truth table: loopback lift rule ---------


def test_load_local_config_loopback_with_tls_only_ok(tmp_path, monkeypatch):
    """Loopback host accepts any TLS/auth combination (including just TLS)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "127.0.0.1"
        cert = "/tmp/c.pem"
        key  = "/tmp/k.pem"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.tls_enabled is True


def test_load_local_config_non_loopback_with_full_bundle_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        cert = "/tmp/c.pem"
        key  = "/tmp/k.pem"
        htpasswd = "/tmp/htp"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "0.0.0.0"  # noqa: S104
    assert cfg.tls_enabled is True
    assert cfg.auth_enabled is True


def test_load_local_config_non_loopback_partial_tls_rejected(tmp_path):
    """cert without key → ServerConfigError naming the missing piece."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        cert = "/tmp/c.pem"
        htpasswd = "/tmp/htp"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"missing: key"):
        load_local_config(tmp_path)


def test_load_local_config_non_loopback_missing_key_only(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        key = "/tmp/k.pem"
        htpasswd = "/tmp/htp"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"missing: cert"):
        load_local_config(tmp_path)


def test_load_local_config_non_loopback_missing_htpasswd_rejected(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        cert = "/tmp/c.pem"
        key  = "/tmp/k.pem"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"missing: htpasswd"):
        load_local_config(tmp_path)


def test_load_local_config_non_loopback_missing_tls_rejected(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "0.0.0.0"
        htpasswd = "/tmp/htp"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"missing: cert\+key"):
        load_local_config(tmp_path)


def test_load_local_config_ipv6_dual_stack_rejected_without_bundle(tmp_path):
    """IPv6 :: (dual-stack) is non-loopback and requires the full bundle."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "::"
        """,
    )
    with pytest.raises(ServerConfigError, match="non-loopback binds require BOTH"):
        load_local_config(tmp_path)


def test_load_local_config_ipv6_dual_stack_with_bundle_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "::"
        cert = "/tmp/c.pem"
        key  = "/tmp/k.pem"
        htpasswd = "/tmp/htp"
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.host == "::"


def test_load_local_config_error_names_host_in_message(tmp_path):
    """The error includes the offending host so operators know which value to fix."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "10.0.0.5"
        """,
    )
    with pytest.raises(ServerConfigError, match="'10.0.0.5'"):
        load_local_config(tmp_path)


# --------- TLS pair must be both-or-neither, regardless of host ---------


def test_load_local_config_loopback_with_cert_only_rejected(tmp_path):
    """Loopback host + cert without key: half-TLS would be silently
    ignored (tls_enabled requires both). Reject explicitly."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "127.0.0.1"
        cert = "/tmp/c.pem"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"TLS pair incomplete.*missing: key"):
        load_local_config(tmp_path)


def test_load_local_config_loopback_with_key_only_rejected(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "127.0.0.1"
        key = "/tmp/k.pem"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"TLS pair incomplete.*missing: cert"):
        load_local_config(tmp_path)


def test_load_local_config_localhost_with_cert_only_rejected(tmp_path):
    """Same rule applies to the localhost alias."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        host = "localhost"
        cert = "/tmp/c.pem"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"TLS pair incomplete"):
        load_local_config(tmp_path)


# --------- v0.8.0: publish_users + max_upload_bytes ---------


def test_localconfig_publish_defaults_off():
    """Defaults: empty publish_users, 100 MiB cap, publish_enabled False."""
    cfg = LocalConfig()
    assert cfg.publish_users == ()
    assert cfg.max_upload_bytes == 100 * 1024 * 1024
    assert cfg.publish_enabled is False


def test_localconfig_publish_enabled_requires_both_allowlist_and_auth(tmp_path):
    """publish_enabled is True only when publish_users non-empty AND auth_enabled."""
    htp = tmp_path / "htpasswd"
    # allowlist alone, no auth — False
    assert LocalConfig(publish_users=("alice",)).publish_enabled is False
    # auth alone, no allowlist — False
    assert LocalConfig(htpasswd=htp).publish_enabled is False
    # both — True
    cfg = LocalConfig(htpasswd=htp, publish_users=("alice",))
    assert cfg.publish_enabled is True


def test_localconfig_publish_users_is_tuple_for_freezable():
    """publish_users stored as tuple so the frozen dataclass stays hashable."""
    cfg = LocalConfig(publish_users=("alice", "bob"))
    assert isinstance(cfg.publish_users, tuple)
    assert cfg.publish_users == ("alice", "bob")


def test_localconfig_max_upload_bytes_overridable():
    cfg = LocalConfig(max_upload_bytes=2 * 1024 * 1024 * 1024)
    assert cfg.max_upload_bytes == 2 * 1024 * 1024 * 1024


# --------- v0.8.0 publish_users / max_upload_bytes validators ---------


def test_load_local_config_loads_publish_users(tmp_path, monkeypatch):
    """Reading publish_users requires htpasswd; supply one."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    htp = tmp_path / "htpasswd"
    # Real bcrypt entries — the validator parses the file.
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4))  # noqa: S106
    htp.write_bytes(b"alice:" + h + b"\nbob:" + h + b"\n")
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        htpasswd = "{htp}"
        publish_users = ["alice", "bob"]
        max_upload_bytes = 209715200
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.publish_users == ("alice", "bob")
    assert cfg.max_upload_bytes == 209715200
    assert cfg.publish_enabled is True


def test_load_local_config_rejects_publish_users_not_a_list(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        publish_users = "alice"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"publish_users.*list of strings"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_publish_users_with_empty_string(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        publish_users = ["alice", ""]
        """,
    )
    with pytest.raises(ServerConfigError, match=r"publish_users\[1\].*non-empty"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_publish_users_with_non_string(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        publish_users = ["alice", 42]
        """,
    )
    with pytest.raises(ServerConfigError, match=r"publish_users\[1\].*non-empty"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_publish_users_without_htpasswd(tmp_path):
    """Authorization without authentication is a hard error."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        publish_users = ["alice"]
        """,
    )
    with pytest.raises(ServerConfigError, match=r"publish_users.*requires.*htpasswd"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_publish_user_not_in_htpasswd(tmp_path, monkeypatch):
    """Cross-validator catches a publish_users name that isn't an htpasswd entry."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    htp = tmp_path / "htpasswd"
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4))  # noqa: S106
    # Only alice in htpasswd, but publish_users names eve.
    htp.write_bytes(b"alice:" + h + b"\n")
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        htpasswd = "{htp}"
        publish_users = ["alice", "eve"]
        """,
    )
    with pytest.raises(ServerConfigError, match=r"publish_users contains name.*'eve'"):
        load_local_config(tmp_path)


def test_load_local_config_publish_users_membership_skipped_when_htpasswd_missing(
    tmp_path, monkeypatch
):
    """If htpasswd file doesn't exist, the membership check skips silently —
    the strategy will surface a clearer 'cannot read htpasswd' error at
    server-start time."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    htp = tmp_path / "missing.htpasswd"   # never created
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        htpasswd = "{htp}"
        publish_users = ["alice"]
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.publish_users == ("alice",)


def test_load_local_config_rejects_max_upload_bytes_not_int(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        max_upload_bytes = "104857600"
        """,
    )
    with pytest.raises(ServerConfigError, match=r"max_upload_bytes.*integer"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_max_upload_bytes_too_small(tmp_path):
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        max_upload_bytes = 100
        """,
    )
    with pytest.raises(ServerConfigError, match=r"max_upload_bytes.*>= 1024"):
        load_local_config(tmp_path)


def test_load_local_config_rejects_max_upload_bytes_bool(tmp_path):
    """`true` must not pass the int check (Python bool is an int subclass)."""
    _write_pyproject(
        tmp_path,
        """
        [tool.auntiepypi.local]
        max_upload_bytes = true
        """,
    )
    with pytest.raises(ServerConfigError, match=r"max_upload_bytes.*integer"):
        load_local_config(tmp_path)


def test_load_local_config_publish_users_empty_list_is_read_only(tmp_path, monkeypatch):
    """An explicit empty publish_users list is the same as unset: read-only."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    htp = tmp_path / "htpasswd"
    import bcrypt
    h = bcrypt.hashpw(b"pw", bcrypt.gensalt(rounds=4))  # noqa: S106
    htp.write_bytes(b"alice:" + h + b"\n")
    _write_pyproject(
        tmp_path,
        f"""
        [tool.auntiepypi.local]
        htpasswd = "{htp}"
        publish_users = []
        """,
    )
    cfg = load_local_config(tmp_path)
    assert cfg.publish_users == ()
    assert cfg.publish_enabled is False
