"""HTTP handler factory for the v0.6.0 read-only PEP 503 simple-index.

Three routes:

- ``GET /simple/`` — HTML anchor list of projects in the wheelhouse.
- ``GET /simple/<pkg>/`` (or without trailing slash) — HTML anchor list
  of distribution files for ``<pkg>``. PEP 503 name normalization is
  applied to the request path. 404 when the project has no dists.
- ``GET /files/<filename>`` — raw file bytes
  (``application/octet-stream``). 404 when the filename doesn't exist
  in the wheelhouse, contains separators, or otherwise tries to escape
  the root.

Any other path or non-GET method → 404 / 405.

The handler is a *factory* (``make_handler(root)``) returning a
``BaseHTTPRequestHandler`` subclass that closes over ``root``. This
lets the same module serve multiple wheelhouses in tests.
"""

from __future__ import annotations

import html
import re
import shutil
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

from auntiepypi._server._wheelhouse import list_projects, normalize

# Strict filename pattern: PEP 427/625 dist files + no path components.
# Permits the same charset filenames carry on PyPI.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.(whl|tar\.gz|zip)$")


def make_handler(root: Path) -> type[BaseHTTPRequestHandler]:
    """Return a request-handler class bound to ``root``."""
    resolved_root = root.resolve()

    class _Handler(BaseHTTPRequestHandler):
        # Silence the default request log; tests don't want noise.
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802 — stdlib name
            parsed = urlparse(self.path)
            path = unquote(parsed.path)

            if path == "/":
                return self._serve_root()
            if path == "/simple/":
                return self._serve_index()
            if path.startswith("/simple/"):
                tail = path[len("/simple/") :]
                # Strip an optional single trailing slash; reject anything
                # with internal separators (sub-paths).
                if tail.endswith("/"):
                    tail = tail[:-1]
                if "/" in tail or not tail:
                    return self._send_status(404)
                return self._serve_project(tail)
            if path.startswith("/files/"):
                tail = path[len("/files/") :]
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

    return _Handler
