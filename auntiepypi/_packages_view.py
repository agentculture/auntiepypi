"""Helpers for rendering package overview sections (used by `auntie overview`).

Provides ``_dashboard``, ``_deep_dive``, ``_emit``, and ``_fetch_pair`` —
the same rendering logic that was previously in
``auntiepypi.cli._commands._packages.overview``, extracted so that the top-level
``auntie overview`` command can import them without pulling in the deleted
``packages`` CLI noun.

Read-only. No CLI entry points here.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from auntiepypi._packages_config import ConfigError  # noqa: F401 — re-exported for callers
from auntiepypi._rubric import DIMENSIONS, Dimension
from auntiepypi._rubric._fetch import FetchError
from auntiepypi._rubric._runtime import evaluate_package, roll_up
from auntiepypi._rubric._sources import fetch_pypi, fetch_pypistats
from auntiepypi.cli._output import emit_result

# PEP 508 normalised name regex (per packaging.utils.canonicalize_name input).
_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
_INDEX_VALUE = "pypi.org"


def _validate_name(pkg: str) -> None:
    from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError

    if not _NAME_RE.match(pkg):
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"invalid package name: {pkg!r}",
            remediation="package names match PEP 508; letters, digits, '.', '-', '_'",
        )


def _fetch_pair(
    pkg: str,
) -> tuple[dict | None, dict | None, list[str], bool]:
    """Fetch both sources for one package.

    Returns ``(pypi, stats, warnings, env_failure)``. ``env_failure`` is True
    iff every attempted fetch failed for a *non-data* reason (network, 5xx,
    timeout). A 404 is treated as data — "package not on PyPI" — and never
    raises ``env_failure``.
    """
    warnings: list[str] = []
    pypi: dict | None = None
    stats: dict | None = None
    pypi_env_error = False
    stats_env_error = False

    try:
        pypi = fetch_pypi(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypi.org {err.reason}")
        if err.status == 404:
            # 404 is data, not env failure. Skip pypistats for this package.
            return pypi, stats, warnings, False
        pypi_env_error = True

    try:
        stats = fetch_pypistats(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypistats.org {err.reason}")
        if err.status != 404:
            stats_env_error = True

    env_failure = pypi_env_error and stats_env_error
    return pypi, stats, warnings, env_failure


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


def _section_for_dimension(pypi: dict | None, stats: dict | None, dimension: Dimension) -> dict:
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
    sections = [_section_for_dimension(pypi, stats, d) for d in DIMENSIONS]
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
    """Return (payload, warnings, env_failures).

    ``env_failures`` counts packages where both upstream fetches failed for
    non-data reasons (network/5xx). A 404 from pypi.org is treated as data
    and does not contribute to the count.
    """
    # Validate up-front so a malformed name surfaces as exit 1 (user error)
    # rather than confusing fetch failures.
    for n in names:
        _validate_name(n)
    sections: list[dict] = []
    warnings: list[str] = []
    env_failures = 0
    Result = tuple[dict | None, dict | None, list[str], bool]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_pair, n): n for n in names}
        results: dict[str, Result] = {}
        for fut, n in futures.items():
            try:
                results[n] = fut.result()
            except Exception as err:  # noqa: BLE001 - per-package isolation
                warnings.append(f"{n}: unexpected fetch error: {err.__class__.__name__}: {err}")
                results[n] = (None, None, [], True)
    for n in names:
        pypi, stats, warns, env_failure = results[n]
        warnings.extend(warns)
        if env_failure:
            env_failures += 1
        sections.append(_section_for_package(n, pypi, stats))
    return {"subject": "packages", "sections": sections}, warnings, env_failures


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
