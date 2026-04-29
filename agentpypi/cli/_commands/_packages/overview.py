"""``agentpypi packages overview [PKG]`` — informational, not gating.

No arg → roll-up over the configured list (``[tool.agentpypi].packages``).
With arg → deep-dive over the rubric for one package.

JSON envelope: ``{"subject", "sections": [...]}``. Each section carries
``category="packages"``, a ``title``, a rolled-up ``light``, and ``fields``.
Read-only. Exit code 0 regardless of how many packages roll up red.
"""

from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor

from agentpypi._packages_config import ConfigError, load_package_names
from agentpypi._rubric import DIMENSIONS
from agentpypi._rubric._fetch import FetchError
from agentpypi._rubric._runtime import evaluate_package, roll_up
from agentpypi._rubric._sources import fetch_pypi, fetch_pypistats
from agentpypi.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, AfiError
from agentpypi.cli._output import emit_diagnostic, emit_result

# PEP 508 normalised name regex (per packaging.utils.canonicalize_name input).
_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
_INDEX_VALUE = "pypi.org"


def _validate_name(pkg: str) -> None:
    if not _NAME_RE.match(pkg):
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"invalid package name: {pkg!r}",
            remediation="package names match PEP 508; letters, digits, '.', '-', '_'",
        )


def _fetch_pair(pkg: str) -> tuple[dict | None, dict | None, list[str]]:
    """Fetch both sources for one package; return (pypi, stats, warnings)."""
    warnings: list[str] = []
    pypi: dict | None = None
    stats: dict | None = None
    try:
        pypi = fetch_pypi(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypi.org {err.reason}")
        if err.status == 404:
            # Don't bother pypistats for a package PyPI doesn't know.
            return pypi, stats, warnings
    try:
        stats = fetch_pypistats(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypistats.org {err.reason}")
    return pypi, stats, warnings


def _section_for_package(pkg: str, pypi: dict | None, stats: dict | None) -> dict:
    results = evaluate_package(pypi, stats)
    light = roll_up(results)
    info = (pypi or {}).get("info") or {}
    version = info.get("version", "—")
    # Released-age field
    released = "—"
    for r in results:
        if r.score.value == "unknown":
            continue
        if r.value and r.value.endswith("d"):
            released = f"{r.value} ago"
            break
    # Downloads field
    downloads_w = "—"
    for r in results:
        if r.value.endswith("/wk"):
            downloads_w = r.value.removesuffix("/wk")
            break
    return {
        "category": "packages",
        "title": pkg,
        "light": light,
        "fields": [
            {"name": "version", "value": version},
            {"name": "index", "value": _INDEX_VALUE},
            {"name": "released", "value": released},
            {"name": "downloads_w", "value": downloads_w},
        ],
    }


def _section_for_dimension(pkg: str, pypi, stats, dimension) -> dict:
    result = dimension.evaluate(pypi, stats)
    return {
        "category": "packages",
        "title": dimension.name,
        "light": result.score.value,
        "fields": [
            {"name": "value", "value": result.value},
            {"name": "reason", "value": result.reason},
        ],
    }


def _deep_dive(pkg: str, pypi: dict | None, stats: dict | None) -> dict:
    sections = [_section_for_dimension(pkg, pypi, stats, d) for d in DIMENSIONS]
    rolled = roll_up([d.evaluate(pypi, stats) for d in DIMENSIONS])
    sections.append(
        {
            "category": "packages",
            "title": "_summary",
            "light": rolled,
            "fields": [{"name": "package", "value": pkg}],
        }
    )
    return {"subject": pkg, "sections": sections}


def _dashboard(names: list[str]) -> tuple[dict, list[str], int]:
    """Return (payload, warnings, fetch_failures)."""
    # Validate up-front so a malformed name surfaces as exit 1 (user error)
    # rather than confusing fetch failures.
    for n in names:
        _validate_name(n)
    sections: list[dict] = []
    warnings: list[str] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_pair, n): n for n in names}
        results: dict[str, tuple[dict | None, dict | None, list[str]]] = {}
        for fut, n in futures.items():
            try:
                results[n] = fut.result()
            except Exception as err:  # noqa: BLE001 - per-package isolation
                warnings.append(f"{n}: unexpected fetch error: {err.__class__.__name__}: {err}")
                results[n] = (None, None, [])
    for n in names:
        pypi, stats, warns = results[n]
        warnings.extend(warns)
        if pypi is None and stats is None:
            failures += 1
        sections.append(_section_for_package(n, pypi, stats))
    return {"subject": "packages", "sections": sections}, warnings, failures


def _render_text(payload: dict) -> str:
    lines = [f"# {payload['subject']}"]
    for s in payload["sections"]:
        lines.append("")
        lines.append(f"## {s['title']}  [{s['light']}]")
        for f in s["fields"]:
            lines.append(f"  {f['name']:<12}  {f['value']}")
    return "\n".join(lines)


def _emit(payload: dict, json_mode: bool) -> None:
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload), json_mode=False)


def cmd_packages_overview(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    pkg = args.pkg
    if pkg is None:
        try:
            names = load_package_names()
        except ConfigError as err:
            raise AfiError(
                code=EXIT_USER_ERROR,
                message=str(err),
                remediation=(
                    "add a [tool.agentpypi] table to pyproject.toml with a "
                    "non-empty `packages = [...]` list"
                ),
            ) from err
        payload, warnings, failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        if failures == len(names) and len(names) > 0:
            _emit(payload, json_mode)
            return EXIT_ENV_ERROR
        _emit(payload, json_mode)
        return 0

    _validate_name(pkg)
    pypi, stats, warnings = _fetch_pair(pkg)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    payload = _deep_dive(pkg, pypi, stats)
    _emit(payload, json_mode)
    return 0


def register(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "packages",
        help="Manage and report on PyPI packages.",
    )
    sp = p.add_subparsers(dest="packages_verb")
    ov = sp.add_parser(
        "overview",
        help="Roll-up dashboard or per-package deep-dive (informational, not gating).",
    )
    ov.add_argument(
        "pkg",
        nargs="?",
        default=None,
        help="Package name; omit for the dashboard over [tool.agentpypi].packages.",
    )
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_packages_overview)

    def _packages_no_verb(args: argparse.Namespace) -> int:
        p.print_help()
        return EXIT_USER_ERROR

    p.set_defaults(func=_packages_no_verb)
