"""``agentpypi doctor`` — probe + diagnose; ``--fix`` starts configured servers.

Default is dry-run: prints which servers would be started, returns the
overview-style payload but with a ``diagnoses`` field per item. ``--fix``
runs each ``down``/``absent`` server's ``start_command`` via
``subprocess.run`` and re-probes.

Mutating verbs default to dry-run (per CLAUDE.md "every write verb defaults
to dry-run"). ``--fix`` is doctor's apply gate.

Exit codes:

* ``0`` — every server is up (or ``--fix`` brought every down/absent server up).
* ``2`` — a ``--fix`` attempt failed (start_command not on PATH, non-zero exit, …).
"""

from __future__ import annotations

import argparse
import subprocess
from typing import Callable

from agentpypi._probes import PROBES, probe_status
from agentpypi._probes._probe import Probe
from agentpypi._probes._runtime import ProbeResult
from agentpypi.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, AfiError
from agentpypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "agentpypi doctor"

# Indirection for tests: monkey-patch this to a FakeRunner instead of subprocess.run.
RUN: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run


def _diagnose(item: ProbeResult, probe: Probe) -> dict[str, object]:
    out: dict[str, object] = dict(item)
    if item["status"] == "up":
        out["diagnosis"] = "healthy"
        out["remediation"] = None
        return out
    if not probe.start_command:
        out["diagnosis"] = f"{item['status']}; no start_command configured"
        out["remediation"] = "configure start_command in the probe definition"
        return out
    out["diagnosis"] = f"{item['status']}; would run start_command"
    out["remediation"] = list(probe.start_command)
    return out


def _try_start(probe: Probe) -> tuple[bool, str]:
    """Run ``probe.start_command``; return (ok, detail)."""
    try:
        completed = RUN(
            list(probe.start_command),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as err:
        return False, f"command not found: {err.filename}"
    except (OSError, subprocess.SubprocessError) as err:
        return False, f"{err.__class__.__name__}: {err}"
    if completed.returncode != 0:
        snippet = (completed.stderr or completed.stdout or "").strip().splitlines()
        msg = snippet[0] if snippet else f"exit {completed.returncode}"
        return False, f"exit {completed.returncode}: {msg}"
    return True, "started"


def _apply_fix(item: dict[str, object], probe: Probe) -> None:
    """Run ``probe.start_command`` and re-probe, updating ``item`` in place."""
    ok, detail = _try_start(probe)
    item["fix_attempted"] = True
    item["fix_ok"] = ok
    item["fix_detail"] = detail
    if not ok:
        return
    rechecked = probe_status(probe)
    item["status"] = rechecked["status"]
    item["url"] = rechecked["url"]
    if rechecked.get("detail"):
        item["detail"] = rechecked["detail"]
    if rechecked["status"] == "up":
        item["diagnosis"] = "fixed"


def _process_probe(probe: Probe, *, fix: bool) -> dict[str, object]:
    """Diagnose one probe; under ``--fix``, attempt remediation and re-probe."""
    item = _diagnose(probe_status(probe), probe)
    if item["status"] == "up":
        return item
    if fix and probe.start_command:
        _apply_fix(item, probe)
    else:
        item["fix_attempted"] = False
    return item


def _build_payload(*, fix: bool) -> tuple[dict[str, object], bool]:
    """Return (payload, ok). When ``fix`` is True, runs start_commands.

    ``ok`` is computed from the **final post-fix probe statuses**, not from
    the start_command return codes. This is the contract `learn` /
    `explain doctor` document: a `--fix` attempt is only successful if the
    server is `up` after the re-probe.
    """
    items = [_process_probe(probe, fix=fix) for probe in PROBES]
    section = {"name": "local-pypi-servers", "summary": _summary(items), "items": items}
    payload = {
        "subject": _SUBJECT,
        "sections": [section],
        "fix_applied": fix,
    }
    ok = all(item["status"] == "up" for item in items)
    return payload, ok


def _summary(items: list[dict[str, object]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        counts[str(item["status"])] = counts.get(str(item["status"]), 0) + 1
    return ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))


def _render_text(payload: dict[str, object]) -> str:
    lines = [f"# {payload['subject']}"]
    for section in payload["sections"]:
        lines.append("")
        lines.append(f"## {section['name']}")
        lines.append(f"summary: {section['summary']}")
        lines.append("")
        for item in section["items"]:
            lines.append(f"  {item['name']:<12}  {item['status']:<7}  {item['diagnosis']}")
            rem = item.get("remediation")
            if isinstance(rem, list):
                lines.append(f"      remediation: {' '.join(rem)}")
            elif isinstance(rem, str):
                lines.append(f"      remediation: {rem}")
            if item.get("fix_attempted"):
                ok = "ok" if item.get("fix_ok") else "FAILED"
                lines.append(f"      fix: {ok} ({item.get('fix_detail')})")
    if not payload["fix_applied"]:
        lines.append("")
        lines.append("(dry-run; pass --fix to apply remediations)")
    return "\n".join(lines)


def cmd_doctor(args: argparse.Namespace) -> int:
    fix = bool(getattr(args, "fix", False))
    json_mode = bool(getattr(args, "json", False))
    payload, ok = _build_payload(fix=fix)

    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload), json_mode=False)

    if fix and not ok:
        # `--fix` did not bring every server up (either start_command itself
        # failed, or it returned 0 but the post-fix re-probe still reports
        # down/absent). Either case violates the documented contract.
        # Dry-run never escalates: doctor's job is to surface, not enforce.
        emit_diagnostic("doctor: at least one server is still not up after --fix")
        raise AfiError(
            code=EXIT_ENV_ERROR,
            message="doctor: --fix did not bring every server up",
            remediation=(
                "inspect the JSON payload's fix_detail field (when present) and"
                " each item's final status to identify the failing server"
            ),
        )
    return EXIT_SUCCESS


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "doctor",
        help="Probe + diagnose local PyPI servers; with --fix, start them.",
    )
    p.add_argument("--fix", action="store_true", help="Apply remediations (start servers).")
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_doctor)
