"""Tests for `auntiepypi._actions.auntie` — the first-party-server strategy.

The strategy is a thin wrapper around ``_actions.command`` that
synthesizes the argv from ``[tool.auntiepypi.local]`` on each call.
We test (1) the argv shape, (2) that start/stop/restart delegate to
``command`` with a materialized spec, (3) wheelhouse mkdir, and
(4) ACTIONS table registration.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from auntiepypi import _actions
from auntiepypi._actions import auntie as _auntie
from auntiepypi._actions import command as _command
from auntiepypi._actions._action import ActionResult
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection
from auntiepypi._server._config import LocalConfig


@pytest.fixture
def base_spec() -> ServerSpec:
    return ServerSpec(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        managed_by="auntie",
    )


@pytest.fixture
def base_detection() -> Detection:
    return Detection(
        name="auntie",
        flavor="auntiepypi",
        host="127.0.0.1",
        port=3141,
        url="http://127.0.0.1:3141/",
        status="absent",
        source="local",
    )


# --------- _argv ---------


def test_argv_shape(tmp_path):
    cfg = LocalConfig(host="127.0.0.1", port=8080, root=tmp_path / "wheels")
    argv = _auntie._argv(cfg)
    assert argv[0] == sys.executable
    assert argv[1] == "-m"
    assert argv[2] == "auntiepypi._server"
    assert "--host" in argv
    assert "127.0.0.1" in argv
    assert "--port" in argv
    assert "8080" in argv
    assert "--root" in argv
    assert str(tmp_path / "wheels") in argv


def test_argv_omits_tls_auth_flags_when_unconfigured(tmp_path):
    """v0.6.0-style configs (no cert/key/htpasswd) yield argv with no
    TLS or auth flags."""
    cfg = LocalConfig(host="127.0.0.1", port=3141, root=tmp_path / "wheels")
    argv = _auntie._argv(cfg)
    assert "--cert" not in argv
    assert "--key" not in argv
    assert "--htpasswd" not in argv


def test_argv_appends_tls_flags_when_configured(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    cfg = LocalConfig(
        host="127.0.0.1",
        port=3141,
        root=tmp_path / "wheels",
        cert=cert,
        key=key,
    )
    argv = _auntie._argv(cfg)
    assert "--cert" in argv
    assert str(cert) in argv
    assert "--key" in argv
    assert str(key) in argv
    assert "--htpasswd" not in argv  # auth not configured


def test_argv_appends_htpasswd_flag_when_configured(tmp_path):
    htp = tmp_path / "htp"
    cfg = LocalConfig(
        host="127.0.0.1",
        port=3141,
        root=tmp_path / "wheels",
        htpasswd=htp,
    )
    argv = _auntie._argv(cfg)
    assert "--htpasswd" in argv
    assert str(htp) in argv
    assert "--cert" not in argv  # tls not configured


def test_argv_full_bundle(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htp"
    cfg = LocalConfig(
        host="127.0.0.1",
        port=3141,
        root=tmp_path / "wheels",
        cert=cert,
        key=key,
        htpasswd=htp,
    )
    argv = _auntie._argv(cfg)
    assert "--cert" in argv
    assert "--key" in argv
    assert "--htpasswd" in argv


def test_argv_omits_publish_flags_when_unconfigured(tmp_path):
    """v0.7.0 pyprojects (no publish_users / no max_upload_bytes
    override) get the same argv as before — no new flags appended."""
    cfg = LocalConfig(host="127.0.0.1", root=tmp_path / "wheels")
    argv = _auntie._argv(cfg)
    assert "--publish-user" not in argv
    assert "--max-upload-bytes" not in argv


def test_argv_appends_publish_users_one_flag_per_name(tmp_path):
    """argparse `action="append"` requires --publish-user repeated."""
    htp = tmp_path / "htp"
    cfg = LocalConfig(
        root=tmp_path / "wheels",
        htpasswd=htp,
        publish_users=("alice", "bob"),
    )
    argv = _auntie._argv(cfg)
    # The flag appears twice, each followed by a name in order.
    assert argv.count("--publish-user") == 2
    idx_alice = argv.index("alice")
    idx_bob = argv.index("bob")
    # Each --publish-user precedes its name.
    assert argv[idx_alice - 1] == "--publish-user"
    assert argv[idx_bob - 1] == "--publish-user"


def test_argv_appends_max_upload_bytes_when_overridden(tmp_path):
    cfg = LocalConfig(
        root=tmp_path / "wheels",
        max_upload_bytes=2 * 1024 * 1024 * 1024,
    )
    argv = _auntie._argv(cfg)
    assert "--max-upload-bytes" in argv
    idx = argv.index("--max-upload-bytes")
    assert argv[idx + 1] == str(2 * 1024 * 1024 * 1024)


def test_argv_omits_max_upload_bytes_at_default(tmp_path):
    """The default cap doesn't need an explicit flag — argv stays terse."""
    cfg = LocalConfig(
        root=tmp_path / "wheels",
        max_upload_bytes=100 * 1024 * 1024,  # the default
    )
    argv = _auntie._argv(cfg)
    assert "--max-upload-bytes" not in argv


def test_argv_full_v8_bundle(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htp"
    cfg = LocalConfig(
        host="127.0.0.1",
        port=3141,
        root=tmp_path / "wheels",
        cert=cert,
        key=key,
        htpasswd=htp,
        publish_users=("alice",),
        max_upload_bytes=42 * 1024 * 1024,
    )
    argv = _auntie._argv(cfg)
    for flag in ("--cert", "--key", "--htpasswd", "--publish-user", "--max-upload-bytes"):
        assert flag in argv, f"missing {flag} in {argv}"
    assert argv[argv.index("--publish-user") + 1] == "alice"


# --------- ACTIONS registration ---------


def test_actions_table_has_auntie():
    assert "auntie" in _actions.ACTIONS
    assert set(_actions.ACTIONS["auntie"].keys()) == {"start", "stop", "restart"}


def test_dispatch_routes_to_auntie(monkeypatch, base_detection, base_spec):
    captured: dict[str, object] = {}

    def fake_start(det: Detection, spec: ServerSpec) -> ActionResult:
        captured["det"] = det
        captured["spec"] = spec
        return ActionResult(ok=True, detail="started")

    monkeypatch.setitem(_actions.ACTIONS["auntie"], "start", fake_start)
    result = _actions.dispatch("start", base_detection, base_spec)
    assert result.ok
    assert captured["det"] is base_detection
    assert captured["spec"] is base_spec


# --------- _materialize ---------


def test_materialize_flips_managed_by(monkeypatch, tmp_path, base_spec):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    materialized = _auntie._materialize(base_spec)
    assert materialized.managed_by == "command"
    assert materialized.command is not None
    # The argv reflects the (defaulted) LocalConfig.
    assert materialized.command[0] == sys.executable
    assert "auntiepypi._server" in materialized.command


def test_materialize_uses_current_pyproject(tmp_path, monkeypatch, base_spec):
    """The argv comes from current pyproject, not from declaration fields."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.auntiepypi.local]\nport = 9999\nhost = "127.0.0.1"\n'
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    materialized = _auntie._materialize(base_spec)
    assert "9999" in materialized.command


# --------- start delegates to command.start ---------


def test_start_delegates_to_command(monkeypatch, tmp_path, base_detection, base_spec):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_command_start(det: Detection, spec: ServerSpec) -> ActionResult:
        captured["spec"] = spec
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(_command, "start", fake_command_start)
    result = _auntie.start(base_detection, base_spec)
    assert result.ok
    spec: ServerSpec = captured["spec"]  # type: ignore[assignment]
    assert spec.managed_by == "command"
    assert spec.command is not None
    assert spec.command[0] == sys.executable


def test_start_creates_wheelhouse(monkeypatch, tmp_path, base_detection, base_spec):
    """First ``auntie up`` should mkdir -p the wheelhouse."""
    wheel_root = tmp_path / "fresh-wheels"
    assert not wheel_root.exists()
    (tmp_path / "pyproject.toml").write_text(f'[tool.auntiepypi.local]\nroot = "{wheel_root}"\n')
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(_command, "start", lambda d, s: ActionResult(ok=True, detail="started"))
    _auntie.start(base_detection, base_spec)
    assert wheel_root.is_dir()


def test_start_propagates_mkdir_error(monkeypatch, tmp_path, base_detection, base_spec):
    """If mkdir fails (e.g. permission denied), surface as failure
    without invoking command.start.
    """
    wheel_root = tmp_path / "wheels"
    (tmp_path / "pyproject.toml").write_text(f'[tool.auntiepypi.local]\nroot = "{wheel_root}"\n')
    monkeypatch.chdir(tmp_path)

    def boom(*args, **kwargs):
        raise OSError("EPERM")

    monkeypatch.setattr(Path, "mkdir", boom)
    called = {"start": False}

    def fake_start(d, s):
        called["start"] = True
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(_command, "start", fake_start)
    result = _auntie.start(base_detection, base_spec)
    assert not result.ok
    assert "wheelhouse" in result.detail
    assert not called["start"]


# --------- stop / restart delegate to command ---------


def test_stop_delegates(monkeypatch, tmp_path, base_detection, base_spec):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    captured = {}

    def fake_stop(d, s):
        captured["spec"] = s
        return ActionResult(ok=True, detail="stopped")

    monkeypatch.setattr(_command, "stop", fake_stop)
    result = _auntie.stop(base_detection, base_spec)
    assert result.ok
    assert captured["spec"].managed_by == "command"


def test_restart_delegates(monkeypatch, tmp_path, base_detection, base_spec):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    captured = {}

    def fake_restart(d, s):
        captured["spec"] = s
        return ActionResult(ok=True, detail="restarted")

    monkeypatch.setattr(_command, "restart", fake_restart)
    result = _auntie.restart(base_detection, base_spec)
    assert result.ok
    assert captured["spec"].managed_by == "command"


# --------- v0.7.0 readability guards ---------


def test_start_returns_ok_false_when_cert_missing(monkeypatch, tmp_path, base_detection, base_spec):
    """A configured cert path that doesn't exist must surface as a
    failed ActionResult (not a raise) so `auntie up --all` can still
    process declared servers."""
    cert = tmp_path / "missing-cert.pem"
    key = tmp_path / "k.pem"
    key.write_text("dummy")
    htp = tmp_path / "htp"
    htp.write_text("dummy")
    (tmp_path / "pyproject.toml").write_text(f"""
        [tool.auntiepypi.local]
        cert = "{cert}"
        key  = "{key}"
        htpasswd = "{htp}"
        """)
    monkeypatch.chdir(tmp_path)

    called = {"start": False}

    def fake_start(d, s):
        called["start"] = True
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(_command, "start", fake_start)
    result = _auntie.start(base_detection, base_spec)
    assert not result.ok
    assert "cert" in result.detail and "not found" in result.detail
    assert not called["start"]


def test_start_returns_ok_false_when_htpasswd_missing(
    monkeypatch, tmp_path, base_detection, base_spec
):
    htp = tmp_path / "no-such-htpasswd"
    (tmp_path / "pyproject.toml").write_text(f"""
        [tool.auntiepypi.local]
        htpasswd = "{htp}"
        """)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(_command, "start", lambda d, s: ActionResult(ok=True))
    result = _auntie.start(base_detection, base_spec)
    assert not result.ok
    assert "htpasswd" in result.detail and "not found" in result.detail


def test_start_passes_when_all_configured_paths_readable(
    monkeypatch, tmp_path, base_detection, base_spec
):
    """All paths exist + readable → readability guard passes,
    delegates to command.start."""
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htp"
    for p in (cert, key, htp):
        p.write_text("dummy")
    (tmp_path / "pyproject.toml").write_text(f"""
        [tool.auntiepypi.local]
        cert = "{cert}"
        key  = "{key}"
        htpasswd = "{htp}"
        """)
    monkeypatch.chdir(tmp_path)

    delegated = {"yes": False}

    def fake_start(d, s):
        delegated["yes"] = True
        return ActionResult(ok=True, detail="started")

    monkeypatch.setattr(_command, "start", fake_start)
    result = _auntie.start(base_detection, base_spec)
    assert result.ok
    assert delegated["yes"]
