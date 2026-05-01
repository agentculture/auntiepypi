"""Tests for `auntiepypi._server._publish.write_upload` (writer-only).

End-to-end do_POST tests live in tests/test_server_app_publish.py
(task 7); this file covers the atomic-write path in isolation.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from auntiepypi._server._publish import WriteResult, write_upload


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
    # Original must be untouched.
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
    # Restore so the cleanup line in `finally` works for verification.
    monkeypatch.setattr(os, "rename", real_rename)
    # No temp files left.
    assert list(tmp_path.glob(".upload-*")) == []
    # And the target wasn't created.
    assert not (tmp_path / "demo-1.0-py3-none-any.whl").exists()


def test_write_upload_concurrent_writers_first_wins(tmp_path: Path, monkeypatch):
    """Two writers race on the same filename; first wins (201), second
    sees existing → 409. We can't easily exercise true concurrency in
    a unit test, but we can simulate the second-after-first sequence.
    """
    filename = "demo-1.0-py3-none-any.whl"
    first = write_upload(tmp_path, filename, b"first")
    second = write_upload(tmp_path, filename, b"second")
    assert first.status == 201
    assert second.status == 409
    # First wheel's bytes survive.
    assert (tmp_path / filename).read_bytes() == b"first"


def test_write_upload_temp_file_uses_hidden_prefix(tmp_path: Path):
    """The temp file should be hidden (starts with '.') so the
    PEP 503 listing scanner doesn't pick up partial uploads.
    """
    # Capture the temp by mocking the rename (so the temp survives).
    captured: dict[str, str] = {}

    def fake_rename(src, dst):
        captured["src"] = str(src)
        # Don't actually rename; the finally clause will clean up.
        raise OSError("simulated rename failure")

    with mock.patch("os.rename", fake_rename):
        write_upload(tmp_path, "demo-1.0-py3-none-any.whl", b"x")

    # The src path's basename should start with '.upload-' (hidden).
    assert "/.upload-" in captured["src"]
    assert captured["src"].endswith(".part")
