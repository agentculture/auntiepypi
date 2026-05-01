"""Tests for `auntiepypi._server._publish.write_upload` plus end-to-end
POST handler tests (v0.8.0 task 6 + 7).

The first half exercises the atomic-write writer in isolation; the
second half spins up a real ThreadingHTTPServer with auth + publish
authz configured and POSTs to it.
"""

from __future__ import annotations

import base64
import json
import os
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from unittest import mock

import bcrypt
import pytest

from auntiepypi._server._app import make_handler
from auntiepypi._server._publish import WriteResult, write_upload

# --------- write_upload (writer-only) ---------


def test_write_upload_creates_file(tmp_path: Path):
    result = write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"PK\x03\x04demo")
    assert isinstance(result, WriteResult)
    assert result.status == 201
    assert result.written == len(b"PK\x03\x04demo")
    assert (tmp_path / "demo-1.0-py3-none-any.whl").read_bytes() == b"PK\x03\x04demo"


def test_write_upload_returns_409_when_target_exists(tmp_path: Path):
    target = tmp_path / "demo-1.0-py3-none-any.whl"
    target.write_bytes(b"original-bytes")
    result = write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"new-bytes")
    assert result.status == 409
    assert "exists" in result.detail
    assert target.read_bytes() == b"original-bytes"


def test_write_upload_no_partial_file_on_existing(tmp_path: Path):
    """When 409 fires, no temp file (.upload-*.part) is left behind."""
    (tmp_path / "demo-1.0-py3-none-any.whl").write_bytes(b"x")
    write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"y")
    leftovers = list(tmp_path.glob(".upload-*"))
    assert leftovers == []


def test_write_upload_no_partial_file_on_success(tmp_path: Path):
    write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"contents")
    leftovers = list(tmp_path.glob(".upload-*"))
    assert leftovers == []


def test_write_upload_handles_binary_content(tmp_path: Path):
    binary = bytes(range(256))
    result = write_upload(tmp_path, "demo-1.0-py3-none-any.whl", binary)
    assert result.status == 201
    assert (tmp_path / "demo-1.0-py3-none-any.whl").read_bytes() == binary


def test_write_upload_returns_500_on_oserror_with_cleanup(tmp_path: Path, monkeypatch):
    """Simulate ENOSPC during rename — must return 500 and unlink temp."""
    real_rename = os.rename

    def fake_rename(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "rename", fake_rename)
    result = write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"contents")
    assert result.status == 500
    assert "No space left" in result.detail
    monkeypatch.setattr(os, "rename", real_rename)
    assert list(tmp_path.glob(".upload-*")) == []
    assert not (tmp_path / "demo-1.0-py3-none-any.whl").exists()


def test_write_upload_concurrent_writers_first_wins(tmp_path: Path):
    """Sequential simulation of concurrent writers: first 201, second 409."""
    filename = "demo-1.0-py3-none-any.whl"
    first = write_upload(tmp_path, filename, b"first")
    second = write_upload(tmp_path, filename, b"second")
    assert first.status == 201
    assert second.status == 409
    assert (tmp_path / filename).read_bytes() == b"first"


def test_write_upload_temp_file_uses_hidden_prefix(tmp_path: Path):
    """Temp file is hidden (.upload-…) so PEP 503 listing scanner skips it."""
    captured: dict[str, str] = {}

    def fake_rename(src, dst):
        captured["src"] = str(src)
        raise OSError("simulated rename failure")

    with mock.patch("os.rename", fake_rename):
        write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"x")

    assert "/.upload-" in captured["src"]
    assert captured["src"].endswith(".part")


# --------- end-to-end POST handler ---------


def _bcrypt_hash(password: str) -> bytes:
    return bcrypt.hashpw(  # NOSONAR python:S5344 - test fixture; production cost ≥ 12
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=4),  # NOSONAR python:S5344
    )


def _basic_header(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


_BOUNDARY = "----auntie-pytest-publish-boundary"


def _twine_body(
    project: str = "mypkg",
    filename: str = "mypkg-1.0-py3-none-any.whl",
    content: bytes = b"WHEELBYTES",
    boundary: str = _BOUNDARY,
) -> tuple[bytes, str]:
    parts: list[bytes] = []
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(b'Content-Disposition: form-data; name=":action"\r\n\r\n')
    parts.append(b"file_upload\r\n")
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(b'Content-Disposition: form-data; name="name"\r\n\r\n')
    parts.append(project.encode("utf-8") + b"\r\n")
    parts.append(f"--{boundary}\r\n".encode("utf-8"))
    parts.append(
        f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n".encode("utf-8")
    )
    parts.append(content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def served_publish_ready(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    """Server with auth + publish_users=(alice,). Yields (port, root)."""
    htpasswd_map = {
        "alice": _bcrypt_hash("secret"),
        "bob": _bcrypt_hash("hunter2"),  # authenticates but NOT in publish_users
    }
    handler_cls = make_handler(
        tmp_path,
        htpasswd_map=htpasswd_map,
        publish_users=("alice",),
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, tmp_path
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _post(
    port: int,
    path: str,
    body: bytes,
    headers: dict[str, str],
) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(), dict(resp.getheaders())
    finally:
        conn.close()


def _content_headers(body: bytes, ctype: str, auth_header: str | None = None) -> dict[str, str]:
    h = {"Content-Type": ctype, "Content-Length": str(len(body))}
    if auth_header is not None:
        h["Authorization"] = auth_header
    return h


# --------- auth-not-configured ---------


def test_post_returns_405_without_htpasswd(tmp_path: Path):
    handler_cls = make_handler(tmp_path)  # no auth
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        body, ctype = _twine_body()
        status, _, _ = _post(port, "/", body, _content_headers(body, ctype))
        assert status == 405
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


# --------- 401 / 403 / 404 / 400 / 413 / 409 / 201 ---------


def test_post_returns_401_without_auth(served_publish_ready):
    port, _ = served_publish_ready
    body, ctype = _twine_body()
    status, _, headers = _post(port, "/", body, _content_headers(body, ctype))
    assert status == 401
    assert "Basic" in headers["WWW-Authenticate"]


def test_post_returns_403_for_authenticated_non_publisher(served_publish_ready):
    """bob authenticates fine but is not in publish_users."""
    port, _ = served_publish_ready
    body, ctype = _twine_body()
    auth = _basic_header("bob", "hunter2")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 403
    assert b"'bob' cannot publish" in body_resp


def test_post_returns_404_for_wrong_path(served_publish_ready):
    """Only `/` is the upload URL. /simple/ etc must 404 (not 405) so we
    don't leak alternate routes."""
    port, _ = served_publish_ready
    body, ctype = _twine_body()
    auth = _basic_header("alice", "secret")
    status, _, _ = _post(port, "/simple/", body, _content_headers(body, ctype, auth))
    assert status == 404


def test_post_returns_400_for_non_multipart_body(served_publish_ready):
    port, _ = served_publish_ready
    body = b'{"foo": "bar"}'
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, "application/json", auth))
    assert status == 400
    assert b"multipart" in body_resp


def test_post_returns_400_for_missing_action(served_publish_ready):
    port, _ = served_publish_ready
    boundary = "x"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="name"\r\n\r\nmypkg\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="content"; filename="mypkg-1.0.whl"\r\n'
        "\r\nX\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    ctype = f"multipart/form-data; boundary={boundary}"
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 400
    assert b":action" in body_resp


def test_post_returns_400_when_name_field_disagrees_with_filename(served_publish_ready):
    port, _ = served_publish_ready
    body, ctype = _twine_body(project="otherpkg")  # mismatch with mypkg-... filename
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 400
    assert b"does not match filename" in body_resp


def test_post_returns_400_for_bad_filename(served_publish_ready):
    """Filename containing path separators or non-dist extensions must 400."""
    port, _ = served_publish_ready
    body, ctype = _twine_body(filename="../etc/passwd")
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 400
    assert b"invalid filename" in body_resp or b"unrecognized" in body_resp


def test_post_returns_413_when_body_too_large(tmp_path: Path):
    """Server with low max_upload_bytes — POSTing more than that → 413."""
    htpasswd_map = {"alice": _bcrypt_hash("secret")}
    handler_cls = make_handler(
        tmp_path,
        htpasswd_map=htpasswd_map,
        publish_users=("alice",),
        max_upload_bytes=512,
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        body, ctype = _twine_body(content=b"X" * 4096)
        auth = _basic_header("alice", "secret")
        status, _, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
        assert status == 413
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_post_creates_file_on_201(served_publish_ready):
    port, root = served_publish_ready
    body, ctype = _twine_body(content=b"PK\x03\x04WHEEL")
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 201
    assert (root / "mypkg-1.0-py3-none-any.whl").read_bytes() == b"PK\x03\x04WHEEL"
    payload = json.loads(body_resp)
    assert payload["ok"] is True
    assert payload["filename"] == "mypkg-1.0-py3-none-any.whl"
    assert payload["url"] == "/files/mypkg-1.0-py3-none-any.whl"


def test_post_returns_409_when_file_exists(served_publish_ready):
    port, root = served_publish_ready
    (root / "mypkg-1.0-py3-none-any.whl").write_bytes(b"existing")
    body, ctype = _twine_body(content=b"new bytes")
    auth = _basic_header("alice", "secret")
    status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
    assert status == 409
    assert b"exists" in body_resp
    assert (root / "mypkg-1.0-py3-none-any.whl").read_bytes() == b"existing"


def test_post_403_when_publish_users_empty_but_authenticated(tmp_path: Path):
    """publish_users=() with auth on → 403 'publish disabled'."""
    htpasswd_map = {"alice": _bcrypt_hash("secret")}
    handler_cls = make_handler(
        tmp_path,
        htpasswd_map=htpasswd_map,
        publish_users=(),
    )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        body, ctype = _twine_body()
        auth = _basic_header("alice", "secret")
        status, body_resp, _ = _post(port, "/", body, _content_headers(body, ctype, auth))
        assert status == 403
        assert b"disabled" in body_resp
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def test_uploaded_file_appears_in_simple_index(served_publish_ready):
    """Regression: GET /simple/ after POST shows the new wheel."""
    port, _ = served_publish_ready
    body, ctype = _twine_body()
    auth = _basic_header("alice", "secret")
    _post(port, "/", body, _content_headers(body, ctype, auth))
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/simple/", headers={"Authorization": auth})
        resp = conn.getresponse()
        body_html = resp.read().decode()
        resp.close()
    finally:
        conn.close()
    assert "mypkg" in body_html


def test_uploaded_file_downloadable_after_publish(served_publish_ready):
    """Regression: GET /files/<name> after POST returns the bytes."""
    port, _ = served_publish_ready
    payload = b"PK\x03\x04demo-bytes"
    body, ctype = _twine_body(content=payload)
    auth = _basic_header("alice", "secret")
    _post(port, "/", body, _content_headers(body, ctype, auth))
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(
            "GET",
            "/files/mypkg-1.0-py3-none-any.whl",
            headers={"Authorization": auth},
        )
        resp = conn.getresponse()
        downloaded = resp.read()
        resp.close()
    finally:
        conn.close()
    assert downloaded == payload
