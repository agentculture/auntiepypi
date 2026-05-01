"""``auntie publish <path>`` — upload a wheel/sdist to the local index.

Reads ``[tool.auntiepypi.local]`` for ``host``/``port``/``tls_enabled``
and POSTs the file via the twine-shape upload protocol that the v0.8.0
server accepts. Credentials come from ``$AUNTIE_PUBLISH_USER`` /
``$AUNTIE_PUBLISH_PASSWORD`` or interactive prompt; keyring/netrc
support is deferred to v0.8.1.

Exit codes:

- 0 on 2xx (server accepted the upload)
- 1 on any 4xx/5xx (auth failure, authz miss, conflict, size cap)
- 2 on transport error (DNS / TCP / TLS failure, missing file path)

Exit-code mapping is deliberate: a server-side 409 ("file already
exists") is a script-author error (pick a new version), distinct from
a network or config error which is an environment problem.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.error
from pathlib import Path

from auntiepypi._detect._config import load_local_config
from auntiepypi._server._wheelhouse import parse_filename
from auntiepypi.cli._commands._publish_client import (
    build_multipart,
    insecure_skip_verify_enabled,
    post,
)
from auntiepypi.cli._output import emit_result

__all__ = ["cmd_publish", "register"]


def _resolve_creds(args: argparse.Namespace) -> tuple[str, str]:
    """Return ``(user, password)`` from env or prompts.

    Uses ``getpass`` for the password so it doesn't echo. In non-TTY
    environments without env vars set, exits 2 rather than blocking
    on a hidden read.
    """
    user = os.environ.get("AUNTIE_PUBLISH_USER")
    password = os.environ.get("AUNTIE_PUBLISH_PASSWORD")
    if user and password:
        return user, password
    if not sys.stdin.isatty():
        print(
            "auntie publish: missing credentials. Set "
            "AUNTIE_PUBLISH_USER and AUNTIE_PUBLISH_PASSWORD, or "
            "run interactively.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not user:
        user = input("user: ")
    if not password:
        password = getpass.getpass("password: ")
    return user, password


def _build_url(host: str, port: int, *, tls: bool) -> str:
    scheme = "https" if tls else "http"
    bracketed = f"[{host}]" if ":" in host else host
    return f"{scheme}://{bracketed}:{port}/"


def _emit_failure(status: int, body: bytes, json_mode: bool) -> int:
    detail = body.decode("utf-8", errors="replace").strip()
    payload = {"ok": False, "status": status, "detail": detail}
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        print(f"HTTP {status}: {detail}", file=sys.stderr)
    return 1


def _emit_success(body: bytes, json_mode: bool) -> int:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        decoded = {"ok": True, "raw": body.decode("utf-8", errors="replace")}
    if json_mode:
        emit_result(decoded, json_mode=True)
    else:
        filename = decoded.get("filename") or "<unknown>"
        url = decoded.get("url") or ""
        print(f"published {filename} → {url}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    path: Path = args.path
    if not path.exists() or not path.is_file():
        print(f"auntie publish: file not found: {path}", file=sys.stderr)
        return 2
    parsed = parse_filename(path.name)
    if parsed is None:
        print(
            f"auntie publish: not a recognized distribution filename: {path.name}",
            file=sys.stderr,
        )
        return 2
    project, version = parsed

    cfg = load_local_config()
    user, password = _resolve_creds(args)

    file_bytes = path.read_bytes()
    body, ctype = build_multipart(file_bytes, path.name, project, version)
    url = _build_url(cfg.host, cfg.port, tls=cfg.tls_enabled)

    if cfg.tls_enabled and insecure_skip_verify_enabled():
        print(
            "auntie publish: AUNTIE_INSECURE_SKIP_VERIFY=1 — TLS "
            "verification disabled for this upload",
            file=sys.stderr,
        )

    try:
        status, resp_body = post(
            url,
            body,
            ctype,
            user,
            password,
            verify=not insecure_skip_verify_enabled(),
        )
    except urllib.error.URLError as err:
        print(f"auntie publish: transport error: {err.reason}", file=sys.stderr)
        return 2

    if 200 <= status < 300:
        return _emit_success(resp_body, json_mode)
    return _emit_failure(status, resp_body, json_mode)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "publish",
        help="Upload a wheel or sdist to the configured local index.",
        description=(
            "Upload a wheel/sdist to [tool.auntiepypi.local] via the "
            "twine-shape POST protocol. Credentials come from "
            "$AUNTIE_PUBLISH_USER / $AUNTIE_PUBLISH_PASSWORD or "
            "interactive prompt."
        ),
    )
    p.add_argument(
        "path",
        type=Path,
        help="path to the wheel (.whl) or sdist (.tar.gz / .zip) to upload",
    )
    p.add_argument("--json", action="store_true", help="emit structured JSON")
    p.set_defaults(func=cmd_publish)
