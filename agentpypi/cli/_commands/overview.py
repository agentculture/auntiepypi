"""``agentpypi overview`` — composite of packages + servers sections.

v0.0.1 ran the server-flavor probes; v0.1.0 promotes this verb to a
*composite* report:

- No arg → emit a packages section group (rolled-up dashboard from
  ``[tool.agentpypi].packages``) followed by a servers section group
  (the existing ``_probes/`` flavor probes).
- With arg → resolve in priority: server flavor → existing single-probe
  semantics; configured package → delegate to ``packages overview``;
  otherwise zero-target stderr warning + exit 0.

Each section carries an explicit ``category`` key (``"packages"`` or
``"servers"``) so agents can group by domain.
"""

from __future__ import annotations

import argparse

from agentpypi._packages_config import ConfigError, load_package_names
from agentpypi._probes import PROBES, probe_status
from agentpypi.cli._commands._packages.overview import (
    _dashboard,
    _deep_dive,
    _emit,
    _fetch_pair,
)
from agentpypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "agentpypi overview"


def _server_section(probe_result: dict) -> dict:
    fields = [
        {"name": "port", "value": str(probe_result.get("port", ""))},
        {"name": "url", "value": probe_result.get("url", "")},
        {"name": "status", "value": probe_result.get("status", "")},
    ]
    if probe_result.get("detail"):
        fields.append({"name": "detail", "value": probe_result["detail"]})
    light_map = {"up": "green", "down": "red", "absent": "unknown"}
    return {
        "category": "servers",
        "title": probe_result.get("name", "?"),
        "light": light_map.get(probe_result.get("status", ""), "unknown"),
        "fields": fields,
    }


def _all_servers_sections() -> list[dict]:
    return [_server_section(probe_status(p)) for p in PROBES]


def _server_target(target: str) -> dict | None:
    for p in PROBES:
        if p.name == target:
            return _server_section(probe_status(p))
    return None


def _try_package_target(target: str) -> dict | None:
    """Return the deep-dive payload if `target` is a configured package."""
    try:
        names = load_package_names()
    except ConfigError:
        return None
    if target not in names:
        return None
    pypi, stats, warnings = _fetch_pair(target)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    return _deep_dive(target, pypi, stats)


def _composite_no_arg(json_mode: bool) -> int:
    sections: list[dict] = []
    # Packages: only when configured; otherwise omit silently and warn.
    try:
        names = load_package_names()
    except ConfigError:
        names = []
        emit_diagnostic("warning: no [tool.agentpypi].packages configured; " "showing servers only")
    if names:
        payload, warnings, _failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        sections.extend(payload["sections"])
    sections.extend(_all_servers_sections())

    payload = {"subject": _SUBJECT, "sections": sections}
    _emit(payload, json_mode)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    target = args.target if args.target else None
    json_mode = bool(getattr(args, "json", False))

    if target is None:
        return _composite_no_arg(json_mode)

    # Priority 1: server flavor.
    server = _server_target(target)
    if server is not None:
        payload = {"subject": _SUBJECT, "sections": [server]}
        _emit(payload, json_mode)
        return 0

    # Priority 2: configured package.
    pkg_payload = _try_package_target(target)
    if pkg_payload is not None:
        # Use the package subject so consumers can route on it.
        _emit(pkg_payload, json_mode)
        return 0

    # Priority 3: zero-target report (preserved v0.0.1 semantics).
    payload = {
        "subject": _SUBJECT,
        "sections": [],
        "target": target,
        "note": (
            f"target {target!r} not recognised; emitting zero-target report "
            "(use `agentpypi overview` with no arg for the default scan)"
        ),
    }
    emit_diagnostic(f"warning: {payload['note']}")
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(f"# {_SUBJECT}\n\n(no targets scanned)", json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "overview",
        help="Composite report: packages dashboard + local PyPI server probes.",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Optional target: a server flavor (devpi / pypiserver) or a "
            "configured package name. Omit for the full composite."
        ),
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_overview)
