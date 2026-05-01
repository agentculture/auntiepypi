"""Stdlib HTTP client for ``auntie publish``.

Two helpers, kept in their own module so unit tests can import them
without going through argparse:

- :func:`build_multipart` — assemble a twine-shape multipart body by
  hand. Returns ``(body_bytes, content_type_header)``.
- :func:`post` — send the body to the local index with
  ``Authorization: Basic …`` over ``urllib.request``. Returns
  ``(status, response_body_bytes)`` for any HTTP response (including
  4xx via :class:`urllib.error.HTTPError`); raises
  :class:`urllib.error.URLError` on transport-layer failures so the
  caller can map to a distinct exit code.

We construct the multipart body manually rather than use
``email.message.EmailMessage``: the email API is geared toward
``multipart/mixed`` and converting it to ``multipart/form-data`` with
the right Content-Disposition headers is more boilerplate than just
emitting the bytes directly. The shape is small and stable.

HTTPS verification is on by default; operators with self-signed certs
set ``AUNTIE_INSECURE_SKIP_VERIFY=1``. The unverified context is used
*only* on this opt-in path; the production client never silently
skips verification.
"""

from __future__ import annotations

import base64
import os
import secrets
import ssl
import urllib.error
import urllib.request

__all__ = ["build_multipart", "post", "insecure_skip_verify_enabled"]


def _new_boundary() -> str:
    """Random boundary: 16 hex chars on a stable prefix."""
    return f"----auntie-{secrets.token_hex(16)}"


def _text_part(boundary: str, name: str, value: bytes) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
    ).encode("utf-8") + value + b"\r\n"


def _file_part(boundary: str, name: str, filename: str, value: bytes) -> bytes:
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; '
        f'filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    return header + value + b"\r\n"


def build_multipart(
    file_bytes: bytes, filename: str, project: str, version: str
) -> tuple[bytes, str]:
    """Build a twine-shape ``multipart/form-data`` body.

    Four parts: ``:action`` (``file_upload``), ``name`` (canonical
    project name), ``version``, and ``content`` (the raw distribution
    bytes with ``filename=…``). Twine sends additional metadata
    fields; the auntiepypi server ignores them so we don't bother.

    The ``:action`` field name is what the legacy PyPI upload API
    requires — note the leading colon. Stable random boundary uses
    ``secrets.token_hex`` to keep the chance of accidental collision
    with the file bytes vanishingly small.
    """
    boundary = _new_boundary()
    body = (
        _text_part(boundary, ":action", b"file_upload")
        + _text_part(boundary, "name", project.encode("utf-8"))
        + _text_part(boundary, "version", version.encode("utf-8"))
        + _file_part(boundary, "content", filename, file_bytes)
        + f"--{boundary}--\r\n".encode("utf-8")
    )
    ctype = f"multipart/form-data; boundary={boundary}"
    return body, ctype


def insecure_skip_verify_enabled() -> bool:
    """True iff ``AUNTIE_INSECURE_SKIP_VERIFY`` is set to a truthy value."""
    return os.environ.get("AUNTIE_INSECURE_SKIP_VERIFY", "") not in ("", "0", "false", "False")


def post(
    url: str,
    body: bytes,
    content_type: str,
    user: str,
    password: str,
    *,
    verify: bool = True,
    timeout: float = 60.0,
) -> tuple[int, bytes]:
    """POST ``body`` to ``url`` with HTTP Basic auth.

    Returns ``(status, response_body_bytes)`` on any HTTP response —
    including 4xx (we read ``HTTPError`` and surface it as a status
    rather than re-raising). Raises :class:`urllib.error.URLError` on
    transport-layer failures (DNS/connect/TLS) so the caller can map
    to a distinct exit code.

    ``verify`` controls TLS hostname/CA verification; when False, an
    unverified context is used (operators with self-signed certs
    opt in via ``AUNTIE_INSECURE_SKIP_VERIFY=1``).
    """
    creds = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(  # noqa: S310 - URL comes from cfg.host/port
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": content_type,
            "Authorization": f"Basic {creds}",
            "Content-Length": str(len(body)),
        },
    )
    ctx: ssl.SSLContext | None = None
    if url.startswith("https://"):
        if verify:
            ctx = ssl.create_default_context()
        else:
            # Opt-in via AUNTIE_INSECURE_SKIP_VERIFY for self-signed
            # operators; never silent.
            ctx = ssl._create_unverified_context()  # noqa: S323  # nosec B323  # NOSONAR python:S4830
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        # 4xx/5xx responses come through HTTPError — read the body
        # and surface as a status. Caller maps to exit codes.
        return err.code, err.read() or b""
