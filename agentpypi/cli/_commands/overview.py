"""``agentpypi overview`` — probe localhost for known PyPI server flavors.

Read-only descriptive verb. Iterates :data:`agentpypi._probes.PROBES` and
emits a structured report (one section per scanned target).

Surface contract (AFI rubric, bundle 6):

* ``agentpypi overview`` — exit 0, non-empty stdout, full localhost probe.
* ``agentpypi overview --json`` — exit 0, ``{"subject", "sections"}`` shape.
* ``agentpypi overview <unknown-target>`` — exit 0, zero-target report,
  warning on stderr (the descriptive verb falls back gracefully; hard
  failure is ``verify``'s job).

v0.0.1 recognises no targets — a positional argument always degrades to
the zero-target report. Future milestones may interpret targets as
``host[:port]`` or probe-name selectors.
"""

from __future__ import annotations

import argparse

from agentpypi._probes import PROBES, probe_status
from agentpypi._probes._runtime import ProbeResult
from agentpypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "agentpypi overview"


def _probe_section() -> dict[str, object]:
    items: list[ProbeResult] = [probe_status(p) for p in PROBES]
    counts = {"up": 0, "down": 0, "absent": 0}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in counts.items())
    return {
        "name": "local-pypi-servers",
        "summary": summary,
        "items": list(items),
    }


def _build_payload(target: str | None) -> dict[str, object]:
    if target is None:
        return {"subject": _SUBJECT, "sections": [_probe_section()]}
    return {
        "subject": _SUBJECT,
        "sections": [],
        "target": target,
        "note": (
            f"target {target!r} not recognised at v0.0.1; emitting zero-target "
            "report (use `agentpypi overview` with no arg for the default scan)"
        ),
    }


def _render_text(payload: dict[str, object]) -> str:
    lines = [f"# {payload['subject']}"]
    sections = payload["sections"]
    if not sections:
        lines.append("")
        lines.append("(no targets scanned)")
        return "\n".join(lines)
    for section in sections:
        lines.append("")
        lines.append(f"## {section['name']}")
        lines.append(f"summary: {section['summary']}")
        lines.append("")
        for item in section.get("items", []):
            detail = f" ({item['detail']})" if item.get("detail") else ""
            lines.append(f"  {item['name']:<12}  {item['status']:<7}  {item['url']}{detail}")
    return "\n".join(lines)


def cmd_overview(args: argparse.Namespace) -> int:
    target = args.target if args.target else None
    payload = _build_payload(target)
    json_mode = bool(getattr(args, "json", False))
    if target is not None:
        emit_diagnostic(f"warning: {payload['note']}")
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload), json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "overview",
        help="Probe localhost for known PyPI server flavors; report up/down.",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help="(reserved) future selector for a custom host or probe; ignored at v0.0.1.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_overview)
