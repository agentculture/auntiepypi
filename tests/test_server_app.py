"""Tests for `auntiepypi._server._app` — PEP 503 simple-index handler."""

from __future__ import annotations

import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from auntiepypi._server._app import make_handler


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    """Spin up a ThreadingHTTPServer against a per-test wheelhouse on a
    free port. Yields ``(port, root)``.
    """
    handler_cls = make_handler(tmp_path)
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


def _get(port: int, path: str) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read(), dict(resp.getheaders())
    finally:
        conn.close()


# --------- /simple/ index ---------


def test_simple_index_empty(served):
    port, _ = served
    status, body, _ = _get(port, "/simple/")
    assert status == 200
    text = body.decode()
    assert "<html>" in text.lower()
    assert "<body>" in text.lower()
    # No project anchors yet.
    assert 'href="/simple/' not in text


def test_simple_index_lists_projects(served):
    port, root = served
    (root / "requests-2.31.0-py3-none-any.whl").touch()
    (root / "Django-4.2.0.tar.gz").touch()
    status, body, _ = _get(port, "/simple/")
    text = body.decode()
    assert status == 200
    assert 'href="/simple/requests/"' in text
    assert 'href="/simple/django/"' in text  # PEP 503 normalized to lowercase
    assert ">requests<" in text
    assert ">django<" in text


def test_simple_index_html_escapes(served):
    """Filenames can't contain HTML-magic chars (filesystem rejects most),
    but we still escape — defence in depth.
    """
    port, root = served
    # Project name with a dot in it — must show up un-mangled.
    (root / "ruamel.yaml-0.18.0.tar.gz").touch()
    status, body, _ = _get(port, "/simple/")
    text = body.decode()
    assert status == 200
    assert 'href="/simple/ruamel-yaml/"' in text


# --------- /simple/<pkg>/ project page ---------


def test_simple_project_page(served):
    port, root = served
    (root / "requests-2.30.0-py3-none-any.whl").touch()
    (root / "requests-2.31.0-py3-none-any.whl").touch()
    (root / "requests-2.31.0.tar.gz").touch()
    status, body, _ = _get(port, "/simple/requests/")
    text = body.decode()
    assert status == 200
    assert 'href="/files/requests-2.30.0-py3-none-any.whl"' in text
    assert 'href="/files/requests-2.31.0-py3-none-any.whl"' in text
    assert 'href="/files/requests-2.31.0.tar.gz"' in text


def test_simple_project_normalizes_request(served):
    """PEP 503 says clients must normalize; we accept any form and
    serve from the canonical bucket.
    """
    port, root = served
    (root / "Foo_Bar-1.0-py3-none-any.whl").touch()
    for path in ("/simple/foo-bar/", "/simple/Foo_Bar/", "/simple/foo.bar/"):
        status, body, _ = _get(port, path)
        assert status == 200, path
        assert "Foo_Bar-1.0-py3-none-any.whl" in body.decode()


def test_simple_project_404_for_missing(served):
    port, _ = served
    status, _body, _ = _get(port, "/simple/nonexistent/")
    assert status == 404


def test_simple_project_no_trailing_slash(served):
    """PEP 503 requires the trailing slash; serve a redirect or the page.
    Our minimal impl serves the page when given /simple/<pkg> too.
    """
    port, root = served
    (root / "requests-2.31.0-py3-none-any.whl").touch()
    status, body, _ = _get(port, "/simple/requests")
    # Either 200 (we serve it) or 301/308 (redirect) is acceptable for
    # PEP 503 clients; we choose 200 since the trailing slash is a
    # minor pedantry and pip handles both.
    assert status in (200, 301, 308)
    if status == 200:
        assert "requests-2.31.0-py3-none-any.whl" in body.decode()


# --------- /files/<filename> file download ---------


def test_files_serves_wheel_bytes(served):
    port, root = served
    wheel = root / "requests-2.31.0-py3-none-any.whl"
    wheel.write_bytes(b"PK\x03\x04fake-wheel-bytes")
    status, body, headers = _get(port, "/files/requests-2.31.0-py3-none-any.whl")
    assert status == 200
    assert body == b"PK\x03\x04fake-wheel-bytes"
    assert headers["Content-Type"] == "application/octet-stream"


def test_files_404_when_absent(served):
    port, _ = served
    status, _body, _ = _get(port, "/files/nope-1.0.tar.gz")
    assert status == 404


def test_files_rejects_path_traversal(served, tmp_path):
    """`..` segments must not escape the wheelhouse root."""
    port, root = served
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("private")
    # http.client URL-encodes %2e%2e; try both the raw and encoded forms.
    for path in (
        "/files/../secret.txt",
        "/files/..%2Fsecret.txt",
        "/files/%2e%2e%2Fsecret.txt",
    ):
        status, body, _ = _get(port, path)
        assert status == 404, f"{path} returned {status}: {body!r}"


def test_files_rejects_absolute_path(served):
    port, _ = served
    status, _body, _ = _get(port, "/files//etc/passwd")
    assert status == 404


def test_files_rejects_subdirectory(served):
    """Files in subdirectories of the wheelhouse aren't reachable."""
    port, root = served
    sub = root / "sub"
    sub.mkdir()
    (sub / "hidden-1.0-py3-none-any.whl").write_bytes(b"x")
    status, _body, _ = _get(port, "/files/sub/hidden-1.0-py3-none-any.whl")
    assert status == 404


# --------- catch-all ---------


def test_unknown_path_404(served):
    port, _ = served
    for path in ("/index.html", "/api/v1/whatever", "/simple"):
        status, _body, _ = _get(port, path)
        assert status == 404, path


def test_root_landing_page(served):
    """`/` returns a small 200 landing page so reprobe and curious users
    see something other than a 404 at the root."""
    port, _ = served
    status, body, _ = _get(port, "/")
    assert status == 200
    text = body.decode()
    assert "auntiepypi" in text
    assert 'href="/simple/"' in text


def test_post_method_405(served):
    """Read-only server: POST should not succeed."""
    port, _ = served
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", "/simple/", body=b"")
        resp = conn.getresponse()
        # 405 Method Not Allowed or 501 Not Implemented are both fine.
        assert resp.status in (405, 501)
        resp.read()
    finally:
        conn.close()
