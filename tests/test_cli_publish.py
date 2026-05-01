"""Tests for ``auntie publish`` (CLI verb + multipart client)."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

from auntiepypi.cli._commands import publish as publish_cmd
from auntiepypi.cli._commands._publish_client import (
    build_multipart,
    insecure_skip_verify_enabled,
    post,
)

# --------- build_multipart cross-check via the server-side parser ---------


def test_build_multipart_roundtrips_through_server_parser():
    """The body build_multipart() emits must parse cleanly with the
    server-side parse_multipart_upload — same shape, same fields."""
    from auntiepypi._server._multipart import parse_multipart_upload

    body, ctype = build_multipart(
        b"WHEEL-BYTES",
        "mypkg-1.0-py3-none-any.whl",
        "mypkg",
        "1.0",
    )
    fields = parse_multipart_upload(ctype, body, max_bytes=10 * 1024 * 1024)
    assert fields.action == "file_upload"
    assert fields.name == "mypkg"
    assert fields.filename == "mypkg-1.0-py3-none-any.whl"
    assert fields.content == b"WHEEL-BYTES"


def test_build_multipart_handles_arbitrary_bytes():
    binary = bytes(range(256))
    body, ctype = build_multipart(binary, "mypkg-1.0-py3-none-any.whl", "mypkg", "1.0")
    from auntiepypi._server._multipart import parse_multipart_upload

    fields = parse_multipart_upload(ctype, body, max_bytes=10 * 1024 * 1024)
    assert fields.content == binary


# --------- post() — error mapping ---------


def test_post_returns_status_and_body_on_2xx(monkeypatch):
    class _FakeResp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def read(self):
            return b'{"ok": true}'

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _FakeResp())
    status, body = post(
        "http://127.0.0.1:3141/",  # noqa: S104  # NOSONAR python:S5332
        b"body",
        "multipart/form-data; boundary=x",
        "alice",
        "secret",
    )
    assert status == 201
    assert body == b'{"ok": true}'


def test_post_maps_httperror_to_status_and_body(monkeypatch):
    import urllib.error

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(
            urllib.error.HTTPError(
                "http://127.0.0.1/",  # NOSONAR python:S5332
                409,
                "Conflict",
                hdrs=None,
                fp=BytesIO(b"file already exists"),
            )
        ),
    )
    status, body = post(
        "http://127.0.0.1:3141/",  # noqa: S104  # NOSONAR python:S5332
        b"x",
        "ct",
        "alice",
        "secret",
    )
    assert status == 409
    assert body == b"file already exists"


def test_post_propagates_urlerror(monkeypatch):
    import urllib.error

    def boom(*a, **kw):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(urllib.error.URLError):
        post(
            "http://127.0.0.1:3141/",  # noqa: S104  # NOSONAR python:S5332
            b"x",
            "ct",
            "alice",
            "secret",
        )


# --------- insecure_skip_verify_enabled ---------


def test_insecure_skip_verify_default_off(monkeypatch):
    monkeypatch.delenv("AUNTIE_INSECURE_SKIP_VERIFY", raising=False)
    assert insecure_skip_verify_enabled() is False


def test_insecure_skip_verify_recognises_truthy(monkeypatch):
    monkeypatch.setenv("AUNTIE_INSECURE_SKIP_VERIFY", "1")
    assert insecure_skip_verify_enabled() is True
    monkeypatch.setenv("AUNTIE_INSECURE_SKIP_VERIFY", "yes")
    assert insecure_skip_verify_enabled() is True


def test_insecure_skip_verify_recognises_falsy(monkeypatch):
    for falsy in ("", "0", "false", "False"):
        monkeypatch.setenv("AUNTIE_INSECURE_SKIP_VERIFY", falsy)
        assert insecure_skip_verify_enabled() is False, falsy


# --------- cmd_publish — end-to-end with monkey-patched post() ---------


@pytest.fixture
def wheel_file(tmp_path: Path) -> Path:
    p = tmp_path / "mypkg-1.0-py3-none-any.whl"
    p.write_bytes(b"PK\x03\x04demo")
    return p


@pytest.fixture
def loopback_pyproject(tmp_path: Path, monkeypatch) -> Path:
    """Set CWD to a tmp project with a loopback [tool.auntiepypi.local]."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.auntiepypi.local]\n" 'host = "127.0.0.1"\n' "port = 3141\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _args_for(path: Path, json_mode: bool = False) -> argparse.Namespace:
    return argparse.Namespace(path=path, json=json_mode, func=publish_cmd.cmd_publish)


def test_cmd_publish_201_exits_0(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(
        publish_cmd,
        "post",
        lambda *a, **kw: (
            201,
            json.dumps(
                {
                    "ok": True,
                    "filename": "mypkg-1.0-py3-none-any.whl",
                    "url": "/files/mypkg-1.0-py3-none-any.whl",
                }
            ).encode(),
        ),
    )
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 0
    out = capsys.readouterr().out
    assert "published" in out
    assert "mypkg-1.0-py3-none-any.whl" in out


def test_cmd_publish_409_exits_1(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (409, b"file already exists\n"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 1
    err = capsys.readouterr().err
    assert "409" in err
    assert "exists" in err


def test_cmd_publish_401_exits_1(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "wrong")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (401, b"401 Unauthorized\n"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 1
    assert "401" in capsys.readouterr().err


def test_cmd_publish_403_exits_1(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "bob")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "hunter2")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (403, b"user 'bob' cannot publish\n"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 1
    err = capsys.readouterr().err
    assert "403" in err
    assert "bob" in err


def test_cmd_publish_413_exits_1(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (413, b"upload too large\n"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 1
    assert "413" in capsys.readouterr().err


def test_cmd_publish_urlerror_exits_2(monkeypatch, wheel_file, loopback_pyproject, capsys):
    import urllib.error

    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")

    def boom(*a, **kw):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(publish_cmd, "post", boom)
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 2
    assert "transport error" in capsys.readouterr().err


def test_cmd_publish_missing_file_exits_2(loopback_pyproject, capsys):
    rc = publish_cmd.cmd_publish(_args_for(loopback_pyproject / "no-such.whl"))
    assert rc == 2
    assert "file not found" in capsys.readouterr().err


def test_cmd_publish_unparseable_filename_exits_2(loopback_pyproject, capsys):
    bogus = loopback_pyproject / "not-a-wheel.txt"
    bogus.write_bytes(b"x")
    rc = publish_cmd.cmd_publish(_args_for(bogus))
    assert rc == 2
    assert "not a recognized" in capsys.readouterr().err


def test_cmd_publish_json_mode(monkeypatch, wheel_file, loopback_pyproject, capsys):
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(
        publish_cmd,
        "post",
        lambda *a, **kw: (
            201,
            json.dumps({"ok": True, "filename": "mypkg-1.0-py3-none-any.whl"}).encode(),
        ),
    )
    rc = publish_cmd.cmd_publish(_args_for(wheel_file, json_mode=True))
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["filename"] == "mypkg-1.0-py3-none-any.whl"


def test_cmd_publish_env_creds_bypass_prompts(monkeypatch, wheel_file, loopback_pyproject):
    """When both env vars are set, neither input() nor getpass() is called."""
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (201, b'{"ok": true}'))

    def fail_input(*a, **kw):
        raise AssertionError("input() called when env creds were set")

    monkeypatch.setattr("builtins.input", fail_input)
    monkeypatch.setattr("getpass.getpass", fail_input)
    assert publish_cmd.cmd_publish(_args_for(wheel_file)) == 0


def test_cmd_publish_picks_https_when_tls_configured(monkeypatch, wheel_file, tmp_path: Path):
    """When pyproject configures cert/key, the URL becomes https://."""
    (tmp_path / "c.pem").write_text("cert")
    (tmp_path / "k.pem").write_text("key")
    (tmp_path / "pyproject.toml").write_text(f"""
        [tool.auntiepypi.local]
        host = "127.0.0.1"
        port = 3141
        cert = "{tmp_path / 'c.pem'}"
        key  = "{tmp_path / 'k.pem'}"
        """)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")

    captured: dict[str, str] = {}

    def capture(url, body, ctype, user, pw, **kw):  # noqa: ANN001
        captured["url"] = url
        return 201, b'{"ok": true}'

    monkeypatch.setattr(publish_cmd, "post", capture)
    publish_cmd.cmd_publish(_args_for(wheel_file))
    assert captured["url"].startswith("https://")


def test_cmd_publish_warns_on_insecure_skip_verify(monkeypatch, wheel_file, tmp_path: Path, capsys):
    """Setting AUNTIE_INSECURE_SKIP_VERIFY=1 must emit a stderr warning."""
    (tmp_path / "c.pem").write_text("cert")
    (tmp_path / "k.pem").write_text("key")
    (tmp_path / "pyproject.toml").write_text(f"""
        [tool.auntiepypi.local]
        host = "127.0.0.1"
        port = 3141
        cert = "{tmp_path / 'c.pem'}"
        key  = "{tmp_path / 'k.pem'}"
        """)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setenv("AUNTIE_INSECURE_SKIP_VERIFY", "1")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (201, b'{"ok": true}'))
    publish_cmd.cmd_publish(_args_for(wheel_file))
    err = capsys.readouterr().err
    assert "INSECURE" in err.upper() or "verification disabled" in err


# --------- registration ---------


def test_publish_verb_registered_in_main_parser():
    from auntiepypi.cli import _build_parser

    parser = _build_parser()
    # Smoke test — ensure `publish` parses without error.
    with mock.patch.object(publish_cmd, "cmd_publish", return_value=0):
        args = parser.parse_args(["publish", "/tmp/x.whl"])  # noqa: S108
        assert args.command == "publish"
        assert args.path == Path("/tmp/x.whl")  # noqa: S108


# --------- coverage closeouts ---------


def test_resolve_creds_non_tty_without_env_exits_2(
    monkeypatch, wheel_file, loopback_pyproject, capsys
):
    """Non-interactive run without env vars must exit 2, not block."""
    monkeypatch.delenv("AUNTIE_PUBLISH_USER", raising=False)
    monkeypatch.delenv("AUNTIE_PUBLISH_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        publish_cmd.cmd_publish(_args_for(wheel_file))
    assert exc.value.code == 2
    assert "missing credentials" in capsys.readouterr().err


def test_resolve_creds_interactive_prompt_used(monkeypatch, wheel_file, loopback_pyproject):
    """When env vars are missing but TTY is attached, prompt for both."""
    monkeypatch.delenv("AUNTIE_PUBLISH_USER", raising=False)
    monkeypatch.delenv("AUNTIE_PUBLISH_PASSWORD", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *_: "alice")
    monkeypatch.setattr("getpass.getpass", lambda *_: "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (201, b'{"ok": true}'))
    assert publish_cmd.cmd_publish(_args_for(wheel_file)) == 0


def test_emit_success_handles_non_json_body(monkeypatch, wheel_file, loopback_pyproject, capsys):
    """Server might respond 2xx with plain text; CLI must not crash."""
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (200, b"ok"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file))
    assert rc == 0
    out = capsys.readouterr().out
    # No filename in the response → falls back to <unknown>
    assert "published" in out


def test_emit_failure_json_mode(monkeypatch, wheel_file, loopback_pyproject, capsys):
    """JSON-mode failure prints structured payload, not text."""
    monkeypatch.setenv("AUNTIE_PUBLISH_USER", "alice")
    monkeypatch.setenv("AUNTIE_PUBLISH_PASSWORD", "secret")
    monkeypatch.setattr(publish_cmd, "post", lambda *a, **kw: (409, b"file already exists\n"))
    rc = publish_cmd.cmd_publish(_args_for(wheel_file, json_mode=True))
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["status"] == 409


def test_post_uses_default_verifying_context_for_https(monkeypatch):
    """verify=True on https URL → ssl.create_default_context() in play."""
    captured: dict[str, object] = {}

    class _FakeResp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(req, timeout, context):
        captured["context"] = context
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    post(
        "https://127.0.0.1:3141/",
        b"x",
        "ct",
        "alice",
        "secret",
        verify=True,
    )
    import ssl as _ssl

    # The default verifying context has CERT_REQUIRED + check_hostname=True.
    ctx = captured["context"]
    assert isinstance(ctx, _ssl.SSLContext)
    assert ctx.verify_mode == _ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
