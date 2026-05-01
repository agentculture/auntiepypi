"""Tests for `auntiepypi._server._multipart` — twine-shape upload parser."""

from __future__ import annotations

import pytest

from auntiepypi._server._multipart import (
    MultipartError,
    UploadFields,
    parse_multipart_upload,
)

_BOUNDARY = "----auntie-pytest-boundary"
_DEFAULT_MAX = 10 * 1024 * 1024


def _make_body(parts: list[tuple[dict[str, str], bytes]], boundary: str = _BOUNDARY) -> bytes:
    """Assemble a multipart body from (headers, payload) tuples."""
    chunks: list[bytes] = []
    for headers, payload in parts:
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        for key, value in headers.items():
            chunks.append(f"{key}: {value}\r\n".encode("utf-8"))
        chunks.append(b"\r\n")
        chunks.append(payload)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def _twine_body(content: bytes = b"WHEELBYTES", filename: str = "mypkg-1.0.whl") -> bytes:
    return _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            (
                {
                    "Content-Disposition": (
                        f'form-data; name="content"; filename="{filename}"'
                    ),
                    "Content-Type": "application/octet-stream",
                },
                content,
            ),
        ]
    )


def _ctype(boundary: str = _BOUNDARY) -> str:
    return f"multipart/form-data; boundary={boundary}"


# --------- happy path ---------


def test_parse_valid_twine_shape_returns_fields():
    fields = parse_multipart_upload(_ctype(), _twine_body(), _DEFAULT_MAX)
    assert isinstance(fields, UploadFields)
    assert fields.action == "file_upload"
    assert fields.name == "mypkg"
    assert fields.filename == "mypkg-1.0.whl"
    assert fields.content == b"WHEELBYTES"


def test_parse_handles_content_with_binary_bytes():
    """Wheel files contain arbitrary bytes including \\x00, \\xff."""
    binary = bytes(range(256))
    fields = parse_multipart_upload(_ctype(), _twine_body(content=binary), _DEFAULT_MAX)
    assert fields.content == binary


def test_parse_ignores_extra_pypi_metadata_fields():
    """PyPI clients send ~20 fields. We consume :action/name/content
    and silently ignore the rest. Extra fields must not break parsing.
    """
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            ({"Content-Disposition": 'form-data; name="version"'}, b"1.0"),
            ({"Content-Disposition": 'form-data; name="pyversion"'}, b"py3"),
            ({"Content-Disposition": 'form-data; name="metadata_version"'}, b"2.1"),
            ({"Content-Disposition": 'form-data; name="summary"'}, b"my pkg"),
            ({"Content-Disposition": 'form-data; name="filetype"'}, b"bdist_wheel"),
            ({"Content-Disposition": 'form-data; name="sha256_digest"'}, b"deadbeef"),
            (
                {
                    "Content-Disposition": (
                        'form-data; name="content"; filename="mypkg-1.0.whl"'
                    ),
                },
                b"WHEELBYTES",
            ),
        ]
    )
    fields = parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)
    assert fields.name == "mypkg"
    assert fields.filename == "mypkg-1.0.whl"
    assert fields.content == b"WHEELBYTES"


def test_parse_ignores_gpg_signature_part():
    """Twine optionally uploads a detached .asc; PyPI deprecated this;
    we silently discard it (server doesn't store signatures)."""
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            (
                {
                    "Content-Disposition": (
                        'form-data; name="content"; filename="mypkg-1.0.whl"'
                    ),
                },
                b"WHEELBYTES",
            ),
            (
                {
                    "Content-Disposition": (
                        'form-data; name="gpg_signature"; filename="mypkg-1.0.whl.asc"'
                    ),
                },
                b"-----BEGIN PGP SIGNATURE-----\n...sig...",
            ),
        ]
    )
    fields = parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)
    assert fields.name == "mypkg"


def test_parse_handles_alternative_boundary_string():
    boundary = "Hi-there-this-is-a-different-boundary"
    body = _twine_body() if False else _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            (
                {
                    "Content-Disposition": (
                        'form-data; name="content"; filename="mypkg-1.0.whl"'
                    ),
                },
                b"WHEELBYTES",
            ),
        ],
        boundary=boundary,
    )
    fields = parse_multipart_upload(_ctype(boundary), body, _DEFAULT_MAX)
    assert fields.name == "mypkg"


# --------- malformed Content-Type ---------


def test_parse_rejects_non_multipart_content_type():
    with pytest.raises(MultipartError, match=r"expected multipart"):
        parse_multipart_upload("application/json", b"{}", _DEFAULT_MAX)


def test_parse_rejects_empty_content_type():
    with pytest.raises(MultipartError, match=r"expected multipart"):
        parse_multipart_upload("", b"", _DEFAULT_MAX)


def test_parse_rejects_multipart_without_boundary():
    with pytest.raises(MultipartError, match=r"missing boundary"):
        parse_multipart_upload("multipart/form-data", b"--xxx--", _DEFAULT_MAX)


# --------- missing required parts ---------


def test_parse_rejects_missing_action():
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            (
                {"Content-Disposition": 'form-data; name="content"; filename="m.whl"'},
                b"X",
            ),
        ]
    )
    with pytest.raises(MultipartError, match=r"':action'"):
        parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)


def test_parse_rejects_missing_name():
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            (
                {"Content-Disposition": 'form-data; name="content"; filename="m.whl"'},
                b"X",
            ),
        ]
    )
    with pytest.raises(MultipartError, match=r"'name'"):
        parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)


def test_parse_rejects_missing_content():
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
        ]
    )
    with pytest.raises(MultipartError, match=r"'content'"):
        parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)


def test_parse_rejects_content_without_filename():
    """Content part must carry filename= in its Content-Disposition.
    Without it there's no on-disk name to use.
    """
    body = _make_body(
        [
            ({"Content-Disposition": 'form-data; name=":action"'}, b"file_upload"),
            ({"Content-Disposition": 'form-data; name="name"'}, b"mypkg"),
            ({"Content-Disposition": 'form-data; name="content"'}, b"WHEELBYTES"),
        ]
    )
    with pytest.raises(MultipartError, match=r"missing filename="):
        parse_multipart_upload(_ctype(), body, _DEFAULT_MAX)


# --------- size cap ---------


def test_parse_rejects_oversized_body():
    body = _twine_body(content=b"X" * 1024)
    with pytest.raises(MultipartError, match=r"body too large"):
        parse_multipart_upload(_ctype(), body, max_bytes=100)
