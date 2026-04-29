"""``agentpypi whoami`` — auth/env probe.

Reports which PyPI / TestPyPI / local index the current shell environment
is pointing at, and which Python virtualenv is active. Read-only.

Sources inspected (in priority order):

* ``$PIP_INDEX_URL`` / ``$PIP_EXTRA_INDEX_URL``
* ``$UV_INDEX_URL`` / ``$UV_EXTRA_INDEX_URL``
* ``~/.config/pip/pip.conf`` ``[global]`` ``index-url`` / ``extra-index-url``
* ``$VIRTUAL_ENV`` and ``$UV_PROJECT_ENVIRONMENT`` (active env locator)
"""

from __future__ import annotations

import argparse
import configparser
import os
from pathlib import Path

from agentpypi._probes import PROBES, probe_status
from agentpypi.cli._output import emit_result

_SUBJECT = "agentpypi whoami"

_DEFAULT_PYPI = "https://pypi.org/simple"
_DEFAULT_TESTPYPI = "https://test.pypi.org/simple"


def _read_pip_conf() -> dict[str, str]:
    """Return ``{global.index-url, global.extra-index-url, ...}`` from pip.conf, or ``{}``.

    ``interpolation=None`` (RawConfigParser semantics) is required because
    pip.conf URLs commonly contain percent-encoded characters in credentials
    (e.g. ``%3A`` for ``:``); the default ``BasicInterpolation`` raises
    ``InterpolationSyntaxError`` on bare ``%``.
    """
    candidates = [
        Path.home() / ".config" / "pip" / "pip.conf",
        Path.home() / ".pip" / "pip.conf",  # legacy on some distros
    ]
    parser = configparser.ConfigParser(interpolation=None)
    for path in candidates:
        if path.exists():
            try:
                parser.read(path)
            except configparser.Error:
                continue
            break
    out: dict[str, str] = {}
    if parser.has_section("global"):
        for key in ("index-url", "extra-index-url"):
            try:
                if parser.has_option("global", key):
                    out[key] = parser.get("global", key)
            except configparser.Error:  # pragma: no cover - unreachable with interpolation=None
                # Defensive: any residual parser error here (interpolation,
                # malformed value, encoding) is treated as "value not present"
                # rather than crashing whoami. The verb is read-only and
                # advisory; degrading gracefully is the right call.
                continue
    return out


def _resolved_index() -> dict[str, object]:
    pip_conf = _read_pip_conf()
    return {
        "pip": {
            "index_url_env": os.environ.get("PIP_INDEX_URL"),
            "extra_index_url_env": os.environ.get("PIP_EXTRA_INDEX_URL"),
            "index_url_conf": pip_conf.get("index-url"),
            "extra_index_url_conf": pip_conf.get("extra-index-url"),
        },
        "uv": {
            "index_url_env": os.environ.get("UV_INDEX_URL"),
            "extra_index_url_env": os.environ.get("UV_EXTRA_INDEX_URL"),
        },
        "active_env": {
            "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV"),
            "UV_PROJECT_ENVIRONMENT": os.environ.get("UV_PROJECT_ENVIRONMENT"),
        },
    }


def _effective_default(idx: dict[str, dict[str, object]]) -> str:
    pip = idx["pip"]
    uv = idx["uv"]
    return (
        pip.get("index_url_env")
        or uv.get("index_url_env")
        or pip.get("index_url_conf")
        or _DEFAULT_PYPI
    )


def _local_indexes_seen() -> list[dict[str, object]]:
    """Cross-reference: which configured local PyPI servers are *also* up right now?"""
    return [dict(probe_status(p)) for p in PROBES]


def _build_payload() -> dict[str, object]:
    indexes = _resolved_index()
    return {
        "subject": _SUBJECT,
        "sections": [
            {
                "name": "indexes",
                "summary": f"effective default: {_effective_default(indexes)}",
                "items": [indexes],
            },
            {
                "name": "local-pypi-servers",
                "summary": "cross-reference with `overview` probes",
                "items": _local_indexes_seen(),
            },
        ],
        "defaults": {"pypi": _DEFAULT_PYPI, "testpypi": _DEFAULT_TESTPYPI},
    }


def _render_text(payload: dict[str, object]) -> str:
    lines = [f"# {payload['subject']}"]
    for section in payload["sections"]:
        lines.append("")
        lines.append(f"## {section['name']}")
        lines.append(f"summary: {section['summary']}")
    return "\n".join(lines)


def cmd_whoami(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    payload = _build_payload()
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "whoami",
        help="Report configured PyPI / TestPyPI / local index from pip/uv config.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_whoami)
