"""``auntie overview`` — composite of packages + detected servers.

v0.2.0 swaps the server section group's data source from ``_probes/``
to ``_detect/``. Declared servers, default-port scan results, and
``--proc`` finds all surface here. ``_probes/`` and ``doctor --fix``
are deliberately untouched.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from auntiepypi._detect import (
    Detection,
    ServerConfigError,
    ServersConfig,
    detect_all,
    load_servers,
)
from auntiepypi._packages_config import ConfigError, load_package_names
from auntiepypi.cli._commands._packages.overview import (
    _dashboard,
    _deep_dive,
    _emit,
    _fetch_pair,
)
from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError
from auntiepypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "auntie"


def _load_config_or_raise(scan_processes_override: bool) -> ServersConfig:
    try:
        cfg = load_servers()
    except ServerConfigError as err:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=str(err),
            remediation=(
                "fix [[tool.auntiepypi.servers]] in pyproject.toml; see "
                "docs/superpowers/specs/2026-04-29-auntie-overview-detection-design.md"
            ),
        ) from err
    if scan_processes_override:
        cfg = replace(cfg, scan_processes=True)
    return cfg


def _server_sections(detections: list[Detection]) -> list[dict]:
    return [d.to_section() for d in detections]


def _try_package_target(target: str) -> dict | None:
    try:
        names = load_package_names()
    except ConfigError:
        return None
    if target not in names:
        return None
    pypi, stats, warnings, _env_failure = _fetch_pair(target)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    return _deep_dive(target, pypi, stats)


def _detection_target(
    detections: list[Detection], target: str
) -> Detection | None:
    """Return the matching Detection or None.

    Resolution priority:
      1. Exact name match.
      2. Bare flavor alias — first detection with `flavor == target`.
    """
    for d in detections:
        if d.name == target:
            return d
    for d in detections:
        if d.flavor == target:
            return d
    return None


def _composite_no_arg(json_mode: bool, detections: list[Detection]) -> int:
    sections: list[dict] = []
    try:
        names = load_package_names()
    except ConfigError:
        names = []
        emit_diagnostic(
            "warning: no [tool.auntiepypi].packages configured; showing servers only"
        )
    if names:
        payload, warnings, _failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        sections.extend(payload["sections"])
    sections.extend(_server_sections(detections))
    payload = {"subject": _SUBJECT, "sections": sections}
    _emit(payload, json_mode)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    cfg = _load_config_or_raise(
        scan_processes_override=bool(getattr(args, "proc", False))
    )
    detections = detect_all(cfg)
    target = args.target if args.target else None

    if target is None:
        return _composite_no_arg(json_mode, detections)

    match = _detection_target(detections, target)
    if match is not None:
        payload = {"subject": match.name, "sections": [match.to_section()]}
        _emit(payload, json_mode)
        return 0

    pkg_payload = _try_package_target(target)
    if pkg_payload is not None:
        _emit(pkg_payload, json_mode)
        return 0

    note = (
        f"target {target!r} not recognised; emitting zero-target report "
        "(use `auntie overview` with no arg for the default scan)"
    )
    emit_diagnostic(f"warning: {note}")
    payload = {"subject": _SUBJECT, "sections": [], "target": target, "note": note}
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(f"# {_SUBJECT}\n\n(no targets scanned)", json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "overview",
        help="Composite report: packages dashboard + detected PyPI servers.",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Optional target: a detection name (declared or `<flavor>:<port>`), "
            "a bare flavor (`devpi` / `pypiserver`), or a configured package name."
        ),
    )
    p.add_argument(
        "--proc",
        action="store_true",
        help="Opt-in /proc scan for running PyPI servers (Linux only; no-op elsewhere).",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_overview)
