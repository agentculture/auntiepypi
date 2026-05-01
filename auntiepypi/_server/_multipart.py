"""Twine-style ``multipart/form-data`` parser for the v0.8.0 upload endpoint.

The legacy PyPI upload API sends a multipart body with one part per
field. We only consume three:

- ``:action`` (must be ``file_upload``)
- ``name`` (canonical project name; cross-checked against the filename)
- ``content`` (the distribution bytes; ``filename=…`` parameter required)

PyPI sends another ~17 fields (``version``, ``pyversion``, ``summary``,
``metadata_version``, ``sha256_digest``, ``gpg_signature``, …) — we
silently ignore them. The wheel/sdist itself is the source of truth
for metadata; we just need to write the right bytes to the right
filename.

Implementation: stdlib ``email.parser.BytesParser`` with
``policy.compat32``. ``cgi`` would have been a closer fit, but it
was removed in Python 3.13. Third-party ``multipart`` / ``werkzeug``
would break the "stdlib + bcrypt only" runtime-dep invariant.

v0.8.0 buffers the whole upload in memory before parsing. With
``max_upload_bytes`` capped (100 MiB default) and a single-host LAN
footprint, this is acceptable. Streaming parser → v0.9.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

__all__ = [
    "MultipartError",
    "UploadFields",
    "parse_multipart_upload",
]


class MultipartError(Exception):
    """Malformed multipart upload body."""


@dataclass(frozen=True)
class UploadFields:
    """The three fields the upload endpoint cares about."""

    action: str
    name: str
    filename: str
    content: bytes


def parse_multipart_upload(
    content_type: str, raw_body: bytes, max_bytes: int
) -> UploadFields:
    """Parse a twine-style upload body.

    :param content_type: the request's ``Content-Type`` header value
        (must start with ``multipart/form-data``; boundary= required).
    :param raw_body: the full request body as bytes.
    :param max_bytes: per-request body cap. Already enforced by the
        counted reader before this function runs; checked again here
        so the parser is safe to call directly from tests.

    :raises MultipartError: on malformed Content-Type, missing
        boundary, missing required parts, missing content filename, or
        body exceeding ``max_bytes``.
    """
    if not content_type or not content_type.lower().startswith("multipart/form-data"):
        raise MultipartError(
            f"expected multipart/form-data Content-Type, got {content_type!r}"
        )
    if "boundary=" not in content_type.lower():
        raise MultipartError("multipart Content-Type missing boundary parameter")
    if len(raw_body) > max_bytes:
        raise MultipartError(
            f"body too large ({len(raw_body)} > max_upload_bytes {max_bytes})"
        )

    # email.parser needs a header block on top of the body — synthesize one.
    synthetic = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8") + raw_body
    try:
        msg = BytesParser(policy=policy.compat32).parsebytes(synthetic)
    except (ValueError, TypeError) as err:
        raise MultipartError(f"failed to parse multipart body: {err}") from err

    if not msg.is_multipart():
        raise MultipartError("body is not multipart (no parts found)")

    fields: dict[str, bytes] = {}
    filename: str | None = None
    for part in msg.walk():
        if part is msg or part.is_multipart():
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        fields[name] = payload
        if name == "content":
            # Filename is a Content-Disposition parameter on the
            # content part. Twine sends it; we reject the upload
            # without it because there's no other way to determine
            # the on-disk wheel name.
            filename = part.get_param("filename", header="content-disposition")

    return _build_fields(fields, filename)


def _build_fields(fields: dict[str, bytes], filename: str | None) -> UploadFields:
    """Assemble :class:`UploadFields`, raising on missing requirements."""
    action_b = fields.get(":action")
    if action_b is None:
        raise MultipartError("missing required part: ':action'")
    name_b = fields.get("name")
    if name_b is None:
        raise MultipartError("missing required part: 'name'")
    content_b = fields.get("content")
    if content_b is None:
        raise MultipartError("missing required part: 'content'")
    if not filename:
        raise MultipartError(
            "'content' part is missing filename= in Content-Disposition"
        )
    try:
        action = action_b.decode("utf-8")
        name = name_b.decode("utf-8")
    except UnicodeDecodeError as err:
        raise MultipartError(f"non-utf8 metadata field: {err}") from err
    return UploadFields(
        action=action.strip(),
        name=name.strip(),
        filename=filename,
        content=content_b,
    )
