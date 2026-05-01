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

# Strict filename pattern: PEP 427/625 dist files + no path components.
# Permits the same charset filenames carry on PyPI.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.(whl|tar\.gz|zip)$")


def make_handler(
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
            self.send_header("Content-Type", "text/plain; charset=utf-8")
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
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status: int, text: str) -> None:
            body = f"{text}\n".encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            body = _json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # --- publish (v0.8.0) ----------------------------------------------

        def do_POST(self) -> None:  # noqa: N802 — stdlib name
            """Twine-shape upload at ``POST /``.

            Auth must be configured (htpasswd_map non-None) — otherwise
            405. Caller must authenticate AND be in publish_users —
            otherwise 401 / 403. Path must be exactly ``/`` — anything
            else is 404 (we don't leak alternate routes via 405).
            """
            if htpasswd_map is None:
                return self._send_text(405, "405 Method Not Allowed")
            user = authenticate_user(self.headers.get("Authorization", ""), htpasswd_map)
            if user is None:
                return self._send_401()
            if not publish_users:
                return self._send_text(403, "publish disabled")
            if user not in publish_users:
                return self._send_text(403, f"user {user!r} cannot publish")
            if self.path != "/":
                return self._send_text(404, "404 Not Found")
            return self._handle_upload()

        def _handle_upload(self) -> None:
            ctype = self.headers.get("Content-Type", "")
            if not ctype.lower().startswith("multipart/form-data"):
                return self._send_text(400, "expected Content-Type: multipart/form-data")
            length = self._content_length_or_zero()
            if length > max_upload_bytes:
                return self._send_text(413, f"upload too large (max {max_upload_bytes} bytes)")
            # Counted read defends against missing/lying Content-Length:
            # we never read more than the cap regardless of what the
            # client claims.
            try:
                body = self.rfile.read(min(length, max_upload_bytes)) if length else b""
            except OSError as err:
                return self._send_text(400, f"read error: {err}")
            if length and len(body) != length:
                return self._send_text(400, "incomplete body (Content-Length mismatch)")
            try:
                fields = parse_multipart_upload(ctype, body, max_upload_bytes)
            except MultipartError as err:
                return self._send_text(400, str(err))
            if fields.action != "file_upload":
                return self._send_text(400, f"expected :action=file_upload, got {fields.action!r}")
            if not _SAFE_FILENAME.match(fields.filename):
                return self._send_text(400, f"invalid filename: {fields.filename!r}")
            parsed = parse_filename(fields.filename)
            if parsed is None:
                return self._send_text(
                    400, f"unrecognized distribution filename: {fields.filename!r}"
                )
            project, _version = parsed
            if normalize(fields.name) != normalize(project):
                return self._send_text(
                    400,
                    f"name field {fields.name!r} does not match filename " f"project {project!r}",
                )
            result = write_upload(resolved_root, fields.filename, fields.content)
            if result.status == 201:
                return self._send_json(
                    201,
                    {
                        "ok": True,
                        "filename": fields.filename,
                        "url": f"/files/{fields.filename}",
                        "written": result.written,
                    },
                )
            return self._send_text(result.status, result.detail or str(result.status))

        def _content_length_or_zero(self) -> int:
            raw = self.headers.get("Content-Length", "")
            try:
                return max(int(raw), 0)
            except ValueError:
                return 0

    return _Handler
