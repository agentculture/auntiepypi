"""HTTP handler factory for the PEP 503 simple-index.

Read routes (since v0.6.0):

- ``GET /simple/`` — HTML anchor list of projects in the wheelhouse.
- ``GET /simple/<pkg>/`` (or without trailing slash) — HTML anchor list
  of distribution files for ``<pkg>``. PEP 503 name normalization is
  applied to the request path. 404 when the project has no dists.
- ``GET /files/<filename>`` — raw file bytes
  (``application/octet-stream``). 404 when the filename doesn't exist
  in the wheelhouse, contains separators, or otherwise tries to escape
  the root.

Write route (v0.8.0):

- ``POST /`` — twine-shape ``multipart/form-data`` upload. Requires
  authentication (htpasswd_map non-None) AND the authenticated user in
  ``publish_users``. 401 / 403 / 400 / 409 / 413 / 201 by failure mode.

Any other path or method → 404.

v0.7.0 adds an optional auth gate: when ``make_handler(root,
htpasswd_map=...)`` is called with a non-None map, every GET request
must present a valid ``Authorization: Basic`` header (verified against
:mod:`._auth`). v0.8.0 extends this: POST always requires auth (405
when ``htpasswd_map`` is None), and the authenticated user must
additionally be in ``publish_users``.

The handler is a *factory* (``make_handler(root)``) returning a
``BaseHTTPRequestHandler`` subclass that closes over ``root``. This
lets the same module serve multiple wheelhouses in tests.
"""

from __future__ import annotations

import html
import json as _json
import re
import shutil
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

from auntiepypi._server._auth import authenticate_user, verify_basic
from auntiepypi._server._config import _DEFAULT_MAX_UPLOAD_BYTES
from auntiepypi._server._multipart import MultipartError, parse_multipart_upload
from auntiepypi._server._publish import write_upload
from auntiepypi._server._wheelhouse import list_projects, normalize, parse_filename

_SIMPLE_PREFIX = "/simple/"
_FILES_PREFIX = "/files/"

_TEXT_PLAIN_UTF8 = "text/plain; charset=utf-8"

# Strict filename pattern: PEP 427/625 dist files + no path components.
# Permits the same charset filenames carry on PyPI.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.(whl|tar\.gz|zip)$")


class _UploadReadError(Exception):
    """Body-read failure during POST. Carries an HTTP status hint."""

    def __init__(self, status: int, detail: str, *args: object) -> None:
        super().__init__(detail, status, *args)
        self.status = status
        self.detail = detail


def make_handler(  # NOSONAR python:S3776 - factory closure; see note below
    root: Path,
    *,
    htpasswd_map: dict[str, bytes] | None = None,
    publish_users: tuple[str, ...] = (),
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES,
) -> type[BaseHTTPRequestHandler]:
    """Return a request-handler class bound to ``root``.

    When ``htpasswd_map`` is non-None, every GET request is gated
    through HTTP Basic auth against the map; missing/invalid creds →
    401. When None, the GET handler is unauthenticated (v0.6.0
    behavior).

    POST always requires auth: with ``htpasswd_map=None`` the handler
    returns 405. The authenticated user must additionally be in
    ``publish_users`` (403 otherwise). Empty ``publish_users`` ⇒ no
    one can publish (read-only mode preserved with 403 "publish
    disabled"). ``max_upload_bytes`` is enforced both pre-read
    (Content-Length) and during-read (counted reader).

    .. note::
       Cognitive complexity is high (Sonar S3776) because this is a
       closure factory: ``_Handler`` and all its helpers close over
       ``root`` / ``htpasswd_map`` / ``publish_users`` /
       ``max_upload_bytes``. Hoisting the methods out as module-level
       functions would require explicit-passing of all four to every
       call site — net cognitive cost goes up, not down. The v0.9.0
       streaming-multipart refactor will revisit this; for v0.8.0 the
       trade-off is deliberate.
    """
    resolved_root = root.resolve()

    class _Handler(BaseHTTPRequestHandler):
        # Silence the default request log; tests don't want noise.
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802 — stdlib name
            if htpasswd_map is not None and not self._authenticate():
                return self._send_401()
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            if path == "/":
                return self._serve_root()
            if path == _SIMPLE_PREFIX:
                return self._serve_index()
            if path.startswith(_SIMPLE_PREFIX):
                tail = path[len(_SIMPLE_PREFIX) :]
                # Strip an optional single trailing slash; reject anything
                # with internal separators (sub-paths).
                if tail.endswith("/"):
                    tail = tail[:-1]
                if "/" in tail or not tail:
                    return self._send_status(404)
                return self._serve_project(tail)
            if path.startswith(_FILES_PREFIX):
                tail = path[len(_FILES_PREFIX) :]
                return self._serve_file(tail)
            return self._send_status(404)

        # --- routes --------------------------------------------------------

        def _serve_root(self) -> None:
            body = (
                "<!DOCTYPE html>\n"
                "<html><head><title>auntiepypi</title></head>\n"
                "<body><h1>auntiepypi</h1>\n"
                "<p>First-party PEP 503 simple-index server. "
                'See <a href="/simple/">/simple/</a> for the index.</p>\n'
                "</body></html>\n"
            )
            self._send_html(body)

        def _serve_index(self) -> None:
            projects = sorted(list_projects(resolved_root).keys())
            anchors = "\n".join(
                f'    <a href="/simple/{html.escape(p)}/">{html.escape(p)}</a><br/>'
                for p in projects
            )
            body = (
                "<!DOCTYPE html>\n"
                "<html><head><title>auntiepypi simple index</title></head>\n"
                f"<body>\n{anchors}\n</body></html>\n"
            )
            self._send_html(body)

        def _serve_project(self, name: str) -> None:
            projects = list_projects(resolved_root)
            normalized = normalize(name)
            files = projects.get(normalized)
            if not files:
                return self._send_status(404)
            files_sorted = sorted(files, key=lambda p: p.name)
            anchors = "\n".join(
                f'    <a href="/files/{html.escape(p.name)}">{html.escape(p.name)}</a><br/>'
                for p in files_sorted
            )
            body = (
                "<!DOCTYPE html>\n"
                f"<html><head><title>{html.escape(normalized)}</title></head>\n"
                f"<body>\n{anchors}\n</body></html>\n"
            )
            self._send_html(body)

        def _serve_file(self, filename: str) -> None:
            if not _SAFE_FILENAME.match(filename):
                return self._send_status(404)
            candidate = (resolved_root / filename).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                # Symlink or `..` escape attempt.
                return self._send_status(404)
            if not candidate.is_file():
                return self._send_status(404)
            # Stream the file rather than read_bytes() — wheels can be
            # tens of megabytes and a thread-per-request server holds
            # one buffer per concurrent download. shutil.copyfileobj
            # uses an 8 KiB default chunk under the hood.
            size = candidate.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with candidate.open("rb") as src:
                shutil.copyfileobj(src, self.wfile)

        # --- helpers -------------------------------------------------------

        def _send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_status(self, status: int) -> None:
            body = f"{status}\n".encode()
            self.send_response(status)
            self.send_header("Content-Type", _TEXT_PLAIN_UTF8)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # --- auth (v0.7.0) -------------------------------------------------

        def _authenticate(self) -> bool:
            """Check the ``Authorization`` header against ``htpasswd_map``.

            Caller (``do_GET``) only invokes this when ``htpasswd_map``
            is non-None; the assertion below is a tripwire if that
            invariant is ever violated by a future refactor.
            """
            assert htpasswd_map is not None  # noqa: S101 - invariant tripwire
            return verify_basic(self.headers.get("Authorization", ""), htpasswd_map)

        def _send_401(self) -> None:
            """401 + WWW-Authenticate per RFC 7617.

            ``Connection: close`` prevents header confusion across a
            stale keep-alive on stdlib HTTP/1.0 — defensive.
            """
            body = b"401 Unauthorized\n"
            self.send_response(401)
            self.send_header(
                "WWW-Authenticate",
                'Basic realm="auntiepypi", charset="UTF-8"',
            )
            self.send_header("Connection", "close")
            self.send_header("Content-Type", _TEXT_PLAIN_UTF8)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_post_response(
            self, status: int, *, text: str | None = None, payload: dict | None = None
        ) -> None:
            """Single-shot POST response emitter.

            Always sends ``Connection: close``: the upload body might
            be partially-read or oversized, and HTTP/1.1 keep-alive
            with leftover bytes leads to request desync. Closing the
            socket is cheap (uploads are infrequent) and safer.
            """
            assert (text is None) != (payload is None)  # noqa: S101 - one-of contract
            if payload is not None:
                body = _json.dumps(payload).encode("utf-8")
                ctype = "application/json"
            else:
                assert text is not None  # noqa: S101 - mypy hint
                body = f"{text}\n".encode("utf-8")
                ctype = _TEXT_PLAIN_UTF8
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        # --- publish (v0.8.0) ----------------------------------------------

        def do_POST(self) -> None:  # noqa: N802 — stdlib name
            """Twine-shape upload at ``POST /``.

            Auth must be configured (htpasswd_map non-None) — otherwise
            405. Caller must authenticate AND be in publish_users —
            otherwise 401 / 403. Path must be exactly ``/`` — anything
            else is 404 (we don't leak alternate routes via 405).

            Every response sends ``Connection: close`` (see
            :meth:`_send_post_response`); upload bodies don't benefit
            from keep-alive, and leftover unread bytes on a kept-alive
            socket lead to request desync.
            """
            if htpasswd_map is None:
                return self._send_post_response(405, text="405 Method Not Allowed")
            user = authenticate_user(self.headers.get("Authorization", ""), htpasswd_map)
            if user is None:
                # _send_401 already includes Connection: close.
                return self._send_401()
            if not publish_users:
                return self._send_post_response(403, text="publish disabled")
            if user not in publish_users:
                return self._send_post_response(403, text=f"user {user!r} cannot publish")
            if self.path != "/":
                return self._send_post_response(404, text="404 Not Found")
            return self._handle_upload()

        def _handle_upload(self) -> None:
            ctype = self.headers.get("Content-Type", "")
            if not ctype.lower().startswith("multipart/form-data"):
                return self._send_post_response(
                    400, text="expected Content-Type: multipart/form-data"
                )
            length = self._content_length_strict()
            if length is None:
                # No / invalid Content-Length: refuse rather than
                # read-until-EOF (which would block keep-alive).
                return self._send_post_response(411, text="Content-Length required for upload")
            if length > max_upload_bytes:
                return self._send_post_response(
                    413, text=f"upload too large (max {max_upload_bytes} bytes)"
                )
            try:
                body = self._read_body(length)
            except _UploadReadError as err:
                return self._send_post_response(err.status, text=err.detail)
            try:
                fields = parse_multipart_upload(ctype, body, max_upload_bytes)
            except MultipartError as err:
                return self._send_post_response(400, text=str(err))
            if fields.action != "file_upload":
                return self._send_post_response(
                    400, text=f"expected :action=file_upload, got {fields.action!r}"
                )
            if not _SAFE_FILENAME.match(fields.filename):
                return self._send_post_response(400, text=f"invalid filename: {fields.filename!r}")
            parsed = parse_filename(fields.filename)
            if parsed is None:
                return self._send_post_response(
                    400, text=f"unrecognized distribution filename: {fields.filename!r}"
                )
            project, _version = parsed
            if normalize(fields.name) != normalize(project):
                return self._send_post_response(
                    400,
                    text=(
                        f"name field {fields.name!r} does not match filename "
                        f"project {project!r}"
                    ),
                )
            result = write_upload(resolved_root, fields.filename, fields.content)
            if result.status == 201:
                return self._send_post_response(
                    201,
                    payload={
                        "ok": True,
                        "filename": fields.filename,
                        "url": f"/files/{fields.filename}",
                        "written": result.written,
                    },
                )
            return self._send_post_response(result.status, text=result.detail or str(result.status))

        def _content_length_strict(self) -> int | None:
            """Parse ``Content-Length``; ``None`` if missing/invalid.

            v0.8.0 requires Content-Length on POST (411 Length Required
            when absent). The alternative — read-until-EOF — would
            block on a keep-alive client that doesn't half-close.
            """
            raw = self.headers.get("Content-Length", "")
            if not raw:
                return None
            try:
                value = int(raw)
            except ValueError:
                return None
            if value < 0:
                return None
            return value

        def _read_body(self, length: int) -> bytes:
            """Counted read with a hard cap.

            Loops on ``rfile.read`` rather than calling once: the
            stdlib ``BufferedReader`` *should* return everything
            requested, but the contract permits short reads on a
            partial flush from the client. Counting bytes locally
            defends against a lying ``Content-Length``: we never read
            past the cap and never trust the header alone.

            Raises :class:`_UploadReadError` on incomplete or
            oversized reads — caller maps to a 400 / 413.
            """
            cap = min(length, max_upload_bytes)
            chunks: list[bytes] = []
            remaining = cap
            while remaining > 0:
                try:
                    # 64 KiB chunk — small enough to bound memory growth
                    # on a slow client, large enough that wheel-sized
                    # uploads finish in a handful of iterations.
                    chunk = self.rfile.read(min(65536, remaining))
                except OSError as err:
                    raise _UploadReadError(400, f"read error: {err}") from err
                if not chunk:
                    # Client closed before delivering Content-Length
                    # bytes — legitimate truncation; reject as 400.
                    raise _UploadReadError(
                        400,
                        f"incomplete body (got {cap - remaining} of {length} bytes)",
                    )
                chunks.append(chunk)
                remaining -= len(chunk)
            return b"".join(chunks)

    return _Handler
