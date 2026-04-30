"""``auntie doctor`` — diagnose declared inventory; ``--apply`` acts on it.

Doctor consumes ``_detect/.detect_all`` (same source as ``overview``),
groups detections into action classes (``actionable``,
``half_supervised``, ``ambiguous``, ``skip``), and emits a structured
payload with per-entry ``diagnosis`` and ``remediation``.

T11 scope: detection wiring + diagnosis.
T12 scope: --apply path — dispatch actionable, delete half-supervised, exit 2 on failure.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from auntiepypi import _actions
from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._config_edit import delete_entry, snapshot
from auntiepypi._detect import detect_all
from auntiepypi._detect._config import (
    ConfigGap,
    ServerSpec,
    load_servers_lenient,
)
from auntiepypi._detect._detection import Detection
from auntiepypi._packages_config import find_pyproject
from auntiepypi.cli._commands._decide import Decisions, parse_decisions
from auntiepypi.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, AfiError
from auntiepypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "auntie doctor"


@dataclass
class _Item:
    detection: Detection
    spec: ServerSpec | None
    config_gaps: list[ConfigGap]
    action_class: str  # "actionable" | "half_supervised" | "ambiguous" | "skip"
    diagnosis: str
    remediation: str


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg, gaps = load_servers_lenient()
    detections = detect_all(cfg)
    decisions = parse_decisions(getattr(args, "decide", None) or [])

    items = _build_items(detections, cfg.specs, gaps, decisions)

    target = getattr(args, "target", None)
    if target:
        items = [it for it in items if it.detection.name == target]
        if not items:
            emit_diagnostic(
                f"doctor: unknown TARGET {target!r}; run `auntie doctor` to see all entries"
            )
            return EXIT_SUCCESS

    apply_mode = bool(getattr(args, "apply", False))
    json_mode = bool(getattr(args, "json", False))

    action_results: dict[str, ActionResult] = {}
    if apply_mode:
        action_results = _apply(items, decisions)

    payload = _build_payload(items, applied=apply_mode, action_results=action_results)

    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload, items, apply_mode), json_mode=False)

    if apply_mode:
        bad = [
            it.detection.name
            for it in items
            if it.action_class == "actionable"
            and not action_results.get(it.detection.name, ActionResult(ok=True, detail="")).ok
        ]
        if bad:
            emit_diagnostic(f"doctor: --apply did not bring every actionable server up: {bad}")
            raise AfiError(
                code=EXIT_ENV_ERROR,
                message="doctor: --apply did not bring every actionable server up",
                remediation="inspect the JSON payload's fix_detail field for each failing entry",
            )

    return EXIT_SUCCESS


def _apply(items: list[_Item], decisions: Decisions) -> dict[str, ActionResult]:
    """Run the mutating apply path. Returns action_results keyed by detection.name.

    Order: stage all pending config-mutations → snapshot once → execute deletions
    → dispatch actionable entries.
    """
    half_sup = [it for it in items if it.action_class == "half_supervised"]

    # For each duplicate gap with a decision, compute (name, original_idx) pairs
    # to delete — everything except the kept index.  Iterate ALL items (not just
    # "ambiguous") because when a decision is supplied the item may already be
    # re-classified (e.g. "skip/healthy").  Deduplicate by (name, original_idx)
    # and sort DESCENDING so later deletions don't shift earlier indices.
    duplicate_deletions: list[tuple[str, int]] = []
    seen_names: set[str] = set()
    for it in items:
        for gap in it.config_gaps:
            if gap.kind != "duplicate":
                continue
            if gap.name in seen_names:
                continue  # already processed this duplicate group
            chosen = decisions.for_key("duplicate", gap.name)
            if chosen is None:
                continue
            try:
                keep_idx = int(chosen) - 1
            except ValueError:
                continue
            seen_names.add(gap.name)
            for occ_idx in gap.occurrences:
                if occ_idx != keep_idx:
                    duplicate_deletions.append((gap.name, occ_idx))

    # Descending by occ_idx so each deletion leaves earlier occurrences intact.
    duplicate_deletions.sort(key=lambda p: -p[1])

    pyproject = find_pyproject()
    pending_mutations = bool(half_sup or duplicate_deletions)
    if pending_mutations and pyproject is not None:
        bak = snapshot(pyproject)
        emit_diagnostic(f"wrote {bak.name} (rollback: mv {bak.name} {pyproject.name})")

    if pyproject is not None:
        for it in half_sup:
            result = delete_entry(pyproject, it.detection.name)
            if result.ok:
                lines = result.lines_removed
                lines_str = f"{lines[0]}-{lines[1]}" if lines else "?"
                emit_diagnostic(
                    f"wrote {pyproject.name}: removed [[tool.auntiepypi.servers]] entry "
                    f"{it.detection.name!r} (lines {lines_str})"
                )
            else:
                emit_diagnostic(f"could not auto-delete {it.detection.name!r}: {result.reason}")

        for name, which in duplicate_deletions:
            result = delete_entry(pyproject, name, which=which)
            if result.ok:
                lines = result.lines_removed
                lines_str = f"{lines[0]}-{lines[1]}" if lines else "?"
                emit_diagnostic(
                    f"wrote {pyproject.name}: removed [[tool.auntiepypi.servers]] entry "
                    f"{name!r} occurrence {which} (lines {lines_str})"
                )
            else:
                emit_diagnostic(f"could not auto-delete {name!r} (which={which}): {result.reason}")

    action_results: dict[str, ActionResult] = {}
    for it in items:
        if it.action_class != "actionable" or it.spec is None:
            continue
        result = _actions.dispatch(it.detection, it.spec)
        action_results[it.detection.name] = result

    return action_results


def _build_items(detections, specs, gaps, decisions: Decisions) -> list[_Item]:
    by_name: dict[str, list[ServerSpec]] = {}
    for spec in specs:
        by_name.setdefault(spec.name, []).append(spec)

    gaps_by_name: dict[str, list[ConfigGap]] = {}
    for g in gaps:
        gaps_by_name.setdefault(g.name, []).append(g)

    # Track per-name consumption so duplicates pair with detections in order.
    consumed: dict[str, int] = {}

    items: list[_Item] = []
    for det in detections:
        idx = consumed.get(det.name, 0)
        spec_list = by_name.get(det.name, [])
        spec = spec_list[idx] if idx < len(spec_list) else None
        if spec is not None:
            consumed[det.name] = idx + 1
        item_gaps = gaps_by_name.get(det.name, []) if spec else []
        action_class, diagnosis, remediation = _classify(det, spec, item_gaps, decisions)
        items.append(
            _Item(
                detection=det,
                spec=spec,
                config_gaps=item_gaps,
                action_class=action_class,
                diagnosis=diagnosis,
                remediation=remediation,
            )
        )
    return items


def _classify(
    det: Detection,
    spec: ServerSpec | None,
    gaps: list[ConfigGap],
    decisions: Decisions,
) -> tuple[str, str, str]:
    if spec is None:
        return _classify_undeclared(det)

    half_sup = next((g for g in gaps if g.kind == "missing-companion"), None)
    duplicate = next((g for g in gaps if g.kind == "duplicate"), None)

    if duplicate is not None and decisions.for_key("duplicate", det.name) is None:
        return (
            "ambiguous",
            f"ambiguous: duplicate name {det.name!r}",
            f"auntie doctor --apply --decide=duplicate:{det.name}=1   # or =2",
        )

    if half_sup is not None:
        return (
            "half_supervised",
            "half-supervised; --apply would delete this entry",
            (
                f'add `{_companion_field(half_sup)} = "…"` to keep supervision, '
                "or run `auntie doctor --apply` to demote to manual by deletion"
            ),
        )

    if det.status == "up":
        return ("skip", "healthy", "")

    mode = spec.managed_by
    if mode in _actions.ACTIONS:
        return (
            "actionable",
            f"{det.status}; would dispatch managed_by={mode!r}",
            "auntie doctor --apply",
        )
    if mode in {"docker", "compose"}:
        return ("skip", f"managed_by={mode} not implemented in v0.4.0", "")
    return ("skip", "manual / unset — auntie does not supervise", "")


def _classify_undeclared(det: Detection) -> tuple[str, str, str]:
    stub = (
        "[[tool.auntiepypi.servers]]\n"
        'name = "…"\n'
        f'flavor = "{det.flavor}"\n'
        f"port = {det.port}\n"
        'managed_by = "manual"'
    )
    return ("skip", "observed; not declared", stub)


def _companion_field(gap: ConfigGap) -> str:
    if "`" in gap.detail:
        return gap.detail.split("`")[1]
    return "?"


def _build_payload(
    items: list[_Item],
    applied: bool,
    action_results: dict[str, ActionResult] | None = None,
) -> dict[str, object]:
    """Build the output payload; merges apply-time results when provided."""
    action_results = action_results or {}
    sections = []
    for it in items:
        fields = [
            {"name": "flavor", "value": it.detection.flavor},
            {"name": "host", "value": it.detection.host},
            {"name": "port", "value": str(it.detection.port)},
            {"name": "url", "value": it.detection.url},
            {"name": "status", "value": it.detection.status},
            {"name": "source", "value": it.detection.source},
        ]
        if it.spec and it.spec.managed_by:
            fields.append({"name": "managed_by", "value": it.spec.managed_by})
        for gap in it.config_gaps:
            if gap.kind == "missing-companion":
                fields.append({"name": "config_gap", "value": gap.detail})
        fields.append({"name": "diagnosis", "value": it.diagnosis})
        if it.remediation:
            fields.append({"name": "remediation", "value": it.remediation})

        # Apply-time additions
        if it.detection.name in action_results:
            r = action_results[it.detection.name]
            fields.append({"name": "fix_attempted", "value": "true"})
            fields.append({"name": "fix_ok", "value": "true" if r.ok else "false"})
            fields.append({"name": "fix_detail", "value": r.detail})
            if r.log_path:
                fields.append({"name": "log_path", "value": r.log_path})
            if r.pid is not None:
                fields.append({"name": "pid", "value": str(r.pid)})

        if applied and it.action_class == "half_supervised":
            fields.append({"name": "deleted", "value": "true"})

        sections.append(
            {
                "category": "servers",
                "title": it.detection.name,
                "light": _light_for(it),
                "fields": fields,
            }
        )

    by_status: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for it in items:
        by_status[it.detection.status] = by_status.get(it.detection.status, 0) + 1
        by_class[it.action_class] = by_class.get(it.action_class, 0) + 1

    return {
        "subject": _SUBJECT,
        "sections": sections,
        "summary": {
            "total": len(items),
            "by_status": by_status,
            "by_action_class": by_class,
            "applied": applied,
        },
    }


def _light_for(item: _Item) -> str:
    if item.action_class == "half_supervised":
        return "yellow"
    if item.action_class == "skip" and "not implemented" in item.diagnosis:
        return "yellow"
    if item.detection.status == "up":
        return "green"
    if item.detection.status == "down":
        return "red"
    return "unknown"


def _render_text(payload: dict, items: list[_Item], apply_mode: bool) -> str:
    lines = [f"# {payload['subject']}"]
    summary = payload["summary"]
    by_class = summary["by_action_class"]
    parts = [
        f"{by_class.get('actionable', 0)} actionable",
        f"{by_class.get('half_supervised', 0)} half-supervised",
        f"{by_class.get('skip', 0)} skip",
        f"{by_class.get('ambiguous', 0)} ambiguous",
    ]
    lines.append(f"summary: {', '.join(parts)} ({summary['total']} total)")
    lines.append("")

    for it in items:
        det = it.detection
        managed = it.spec.managed_by if it.spec and it.spec.managed_by else "—"
        lines.append(f"  {det.name:<20}  {det.status:<7}  {det.source:<10}  managed_by={managed}")
        for gap in it.config_gaps:
            if gap.kind == "missing-companion":
                lines.append(f"      config_gap: {gap.detail}")
        lines.append(f"      diagnosis: {it.diagnosis}")
        if it.remediation:
            if "\n" in it.remediation:
                lines.append("      remediation:")
                for r in it.remediation.splitlines():
                    lines.append(f"          {r}")
            else:
                lines.append(f"      remediation: {it.remediation}")

    actionable_count = by_class.get("actionable", 0) + by_class.get("half_supervised", 0)
    if not apply_mode and actionable_count:
        lines.append("")
        lines.append(f"(dry-run; pass --apply to act on {actionable_count} remediations)")
    elif not apply_mode:
        lines.append("")
        lines.append("(dry-run; nothing to apply)")
    return "\n".join(lines)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "doctor",
        help="Diagnose declared inventory; --apply to act (start servers, delete half-supervised).",
    )
    p.add_argument("target", nargs="?", help="Drill into one declared entry by name.")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (start servers + edit pyproject.toml).",
    )
    p.add_argument(
        "--decide",
        action="append",
        default=[],
        help="Resolve an ambiguous case. Format: kind:name=value.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_doctor)
