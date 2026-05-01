"""Tests for `auntiepypi._server.__main__` and the `serve()` helper."""

from __future__ import annotations

import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

from auntiepypi import _server
from auntiepypi._server import __main__ as server_main

# --------- argparse ---------


def test_parser_defaults():
    # /tmp path is an argparse fixture, never created on disk.
    fixture_root = "/tmp/wh"  # noqa: S108  # NOSONAR python:S5443
    args = server_main._parser().parse_args(["--root", fixture_root])
    assert args.host == "127.0.0.1"
    assert args.port == 3141
    assert args.root == Path(fixture_root)


def test_parser_overrides():
    # "0.0.0.0" is a fixture asserting argparse passes the value through;
    # the bind would be rejected at config-load time by load_local_config.
    args = server_main._parser().parse_args(
        ["--host", "0.0.0.0", "--port", "8080", "--root", "/var/wheels"]  # noqa: S104
    )
    assert args.host == "0.0.0.0"  # noqa: S104
    assert args.port == 8080
    assert args.root == Path("/var/wheels")


def test_parser_requires_root():
    with pytest.raises(SystemExit):
        server_main._parser().parse_args([])


def test_parser_tls_auth_flags_default_to_none():
    fixture_root = "/tmp/wh"  # noqa: S108  # NOSONAR python:S5443
    args = server_main._parser().parse_args(["--root", fixture_root])
    assert args.cert is None
    assert args.key is None
    assert args.htpasswd is None


def test_parser_tls_auth_flags_pass_through(tmp_path: Path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    htp = tmp_path / "htp"
    args = server_main._parser().parse_args(
        [
            "--root",
            str(tmp_path),
            "--cert",
            str(cert),
            "--key",
            str(key),
            "--htpasswd",
            str(htp),
        ]
    )
    assert args.cert == cert
    assert args.key == key
    assert args.htpasswd == htp


def test_main_calls_serve(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_serve(host: str, port: int, root: Path, **kw) -> None:  # noqa: ANN003
        captured.update({"host": host, "port": port, "root": root, **kw})

    monkeypatch.setattr(server_main, "serve", fake_serve)
    server_main.main(["--host", "127.0.0.1", "--port", "9999", "--root", str(tmp_path)])
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9999
    assert captured["root"] == tmp_path
    assert captured["ssl_context"] is None
    assert captured["htpasswd_map"] is None
    # v0.8.0 defaults: empty allowlist + 100 MiB cap
    assert captured["publish_users"] == ()
    assert captured["max_upload_bytes"] == 100 * 1024 * 1024


def test_main_rejects_cert_without_key(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        server_main.main(["--root", str(tmp_path), "--cert", str(tmp_path / "c.pem")])
    assert exc.value.code == 2


def test_main_rejects_key_without_cert(tmp_path: Path):
    with pytest.raises(SystemExit) as exc:
        server_main.main(["--root", str(tmp_path), "--key", str(tmp_path / "k.pem")])
    assert exc.value.code == 2


def test_main_builds_ssl_context_when_pair_set(monkeypatch, tmp_path, tls_cert_pair):
    cert, key = tls_cert_pair
    captured: dict[str, object] = {}

    def fake_serve(host, port, root, **kw):  # noqa: ANN001
        captured["ssl_context"] = kw.get("ssl_context")

    monkeypatch.setattr(server_main, "serve", fake_serve)
    server_main.main(
        [
            "--root",
            str(tmp_path),
            "--cert",
            str(cert),
            "--key",
            str(key),
        ]
    )
    import ssl as _ssl

    assert isinstance(captured["ssl_context"], _ssl.SSLContext)


def test_main_parses_htpasswd_when_set(monkeypatch, tmp_path):
    import bcrypt

    htp = tmp_path / "htp"
    # Test fixture only — never written to disk outside tmp_path. Cost-4
    # keeps the suite fast (production cost ≥ 12 via `htpasswd -B`).
    h = bcrypt.hashpw(  # NOSONAR python:S5344
        b"fixture-pw",  # NOSONAR python:S2068 - test fixture, not a credential
        bcrypt.gensalt(rounds=4),  # NOSONAR python:S5344
    )
    htp.write_bytes(b"alice:" + h + b"\n")

    captured: dict[str, object] = {}

    def fake_serve(host, port, root, **kw):  # noqa: ANN001
        captured["htpasswd_map"] = kw.get("htpasswd_map")

    monkeypatch.setattr(server_main, "serve", fake_serve)
    server_main.main(["--root", str(tmp_path), "--htpasswd", str(htp)])
    assert isinstance(captured["htpasswd_map"], dict)
    assert "alice" in captured["htpasswd_map"]


# --------- v0.8.0 publish flags ---------


def test_parser_publish_user_repeatable():
    args = server_main._parser().parse_args(
        [
            "--root",
            "/tmp/wh",  # noqa: S108
            "--publish-user",
            "alice",
            "--publish-user",
            "bob",
        ]
    )
    assert args.publish_user == ["alice", "bob"]


def test_parser_publish_user_default_is_empty_list():
    args = server_main._parser().parse_args(["--root", "/tmp/wh"])  # noqa: S108
    assert args.publish_user == []


def test_parser_max_upload_bytes_default():
    args = server_main._parser().parse_args(["--root", "/tmp/wh"])  # noqa: S108
    assert args.max_upload_bytes == 100 * 1024 * 1024


def test_parser_max_upload_bytes_override():
    args = server_main._parser().parse_args(
        ["--root", "/tmp/wh", "--max-upload-bytes", "536870912"]  # noqa: S108
    )
    assert args.max_upload_bytes == 536870912


def test_main_passes_publish_users_and_max_upload_bytes(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_serve(host, port, root, **kw):  # noqa: ANN001, ANN003
        captured.update(kw)

    monkeypatch.setattr(server_main, "serve", fake_serve)
    server_main.main(
        [
            "--root",
            str(tmp_path),
            "--publish-user",
            "alice",
            "--publish-user",
            "bob",
            "--max-upload-bytes",
            "12345",
        ]
    )
    assert captured["publish_users"] == ("alice", "bob")
    assert captured["max_upload_bytes"] == 12345


# --------- serve() integration ---------


def test_serve_handles_request_and_shuts_down(tmp_path):
    """End-to-end smoke test: serve() responds to /simple/ and exits cleanly."""
    (tmp_path / "demo-1.0-py3-none-any.whl").touch()

    started = threading.Event()
    captured: dict[str, object] = {}

    class _Recording:
        """Wrap ThreadingHTTPServer so the test can grab the instance and
        call shutdown() from outside.
        """

        def __init__(self, address, handler):
            from http.server import ThreadingHTTPServer

            self.inner = ThreadingHTTPServer(address, handler)
            self.server_address = self.inner.server_address
            captured["server"] = self
            started.set()

        def serve_forever(self):
            return self.inner.serve_forever()

        def shutdown(self):
            return self.inner.shutdown()

        def server_close(self):
            return self.inner.server_close()

    def runner():
        _server.serve("127.0.0.1", 0, tmp_path, server_factory=_Recording)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    assert started.wait(timeout=5), "server didn't start"

    server = captured["server"]
    port = server.server_address[1]

    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/simple/")
        resp = conn.getresponse()
        assert resp.status == 200
        body = resp.read().decode()
        assert 'href="/simple/demo/"' in body
    finally:
        conn.close()

    server.shutdown()
    thread.join(timeout=5)
    assert not thread.is_alive()
