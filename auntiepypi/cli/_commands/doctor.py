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
from dataclasses import replace as dc_replace
from pathlib import Path

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
from auntiepypi.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, EXIT_USER_ERROR, AfiError
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
    deleted_names: set[str] = set()
    if apply_mode:
        action_results, deleted_names = _apply(items, decisions)

    payload = _build_payload(
        items, applied=apply_mode, action_results=action_results, deleted_names=deleted_names
    )

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


def _stage_deletions(
    items: list[_Item], decisions: Decisions
) -> tuple[list[str], list[tuple[str, int]]]:
    """Return staged deletion work as ``(half_sup_names, duplicate_dels)``.

    ``half_sup_names`` — detection names whose entries should be deleted
    (half-supervised action class).

    ``duplicate_dels`` — ``(name, occurrence_idx)`` pairs sorted descending
    by occurrence so later deletions don't shift earlier indices.
    """
    half_sup_names = [it.detection.name for it in items if it.action_class == "half_supervised"]
    duplicate_dels = _stage_duplicate_deletions(items, decisions)
    return half_sup_names, duplicate_dels


def _stage_duplicate_deletions(items: list[_Item], decisions: Decisions) -> list[tuple[str, int]]:
    """Compute ``(name, occurrence_idx)`` pairs to delete for decided duplicates.

    Iterates ALL items (not just "ambiguous") because when a decision is
    supplied the item may already be re-classified (e.g. "skip/healthy").
    Deduplicates by name; returns the list sorted descending by occurrence
    index so later deletions don't shift earlier indices.
    """
    out: list[tuple[str, int]] = []
    seen_names: set[str] = set()
    for it in items:
        for gap in it.config_gaps:
            out.extend(_pairs_for_decided_duplicate(gap, decisions, seen_names))
    out.sort(key=lambda p: -p[1])
    return out


def _pairs_for_decided_duplicate(
    gap: ConfigGap, decisions: Decisions, seen_names: set[str]
) -> list[tuple[str, int]]:
    """For a single gap, return the ``(name, occ_idx)`` pairs to delete (or [])."""
    if gap.kind != "duplicate" or gap.name in seen_names:
        return []
    chosen = decisions.for_key("duplicate", gap.name)
    if chosen is None:
        return []
    keep_idx = int(chosen) - 1  # validated upstream by parse_decisions
    seen_names.add(gap.name)
    return [(gap.name, occ) for occ in gap.occurrences if occ != keep_idx]


def _format_lines(lines_removed: tuple[int, int] | None) -> str:
    """Format a ``lines_removed`` pair as ``"first-last"`` or ``"?"``."""
    return f"{lines_removed[0]}-{lines_removed[1]}" if lines_removed else "?"


_DELETE_REFUSAL_REMEDIATION = (
    "the block uses inline-table or multi-line-string syntax that the "
    "stdlib edit cannot safely parse; remove the entry manually"
)


def _execute_deletions(
    pyproject: Path,
    half_sup_names: list[str],
    duplicate_dels: list[tuple[str, int]],
) -> set[str]:
    """Execute staged deletions; raises ``AfiError(1)`` on refusal.

    Returns the set of names that were successfully deleted.
    """
    # Unify the two deletion lists: ``which=None`` means half-supervised
    # (delete first match); ``which=int`` means duplicate occurrence index.
    targets: list[tuple[str, int | None]] = [(name, None) for name in half_sup_names]
    targets.extend((name, which) for name, which in duplicate_dels)

    deleted: set[str] = set()
    for name, which in targets:
        _execute_one_deletion(pyproject, name, which)
        deleted.add(name)
    return deleted


def _execute_one_deletion(pyproject: Path, name: str, which: int | None) -> None:
    """Run a single ``delete_entry`` and emit the audit line; raise on refusal."""
    if which is None:
        result = delete_entry(pyproject, name)
        descriptor = f"{name!r}"
        which_msg = ""
    else:
        result = delete_entry(pyproject, name, which=which)
        descriptor = f"{name!r} occurrence {which}"
        which_msg = f" (which={which})"

    if not result.ok:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"refused to delete entry {name!r}{which_msg}: {result.reason}",
            remediation=_DELETE_REFUSAL_REMEDIATION,
        )
    emit_diagnostic(
        f"wrote {pyproject.name}: removed [[tool.auntiepypi.servers]] entry "
        f"{descriptor} (lines {_format_lines(result.lines_removed)})"
    )


def _dispatch_actionable(items: list[_Item]) -> dict[str, ActionResult]:
    """Dispatch each actionable item and reflect status on success.

    Returns ``dict[name -> ActionResult]`` for every item dispatched.
    """
    results: dict[str, ActionResult] = {}
    for it in items:
        if it.action_class != "actionable" or it.spec is None:
            continue
        result = _actions.dispatch(it.detection, it.spec)
        results[it.detection.name] = result
        if result.ok:
            # Strategy's re-probe confirmed the server is now up. Reflect
            # that in the item so JSON status and rendered text match fix_ok=true.
            it.detection = dc_replace(it.detection, status="up")
    return results


def _apply(items: list[_Item], decisions: Decisions) -> tuple[dict[str, ActionResult], set[str]]:
    """Run the mutating apply path.

    Returns ``(action_results, deleted_names)`` where ``deleted_names`` is
    the set of detection names that were *successfully* removed from
    pyproject.toml. Entries that were refused (inline-table, multi-line
    string) cause an immediate ``AfiError(code=1)`` rather than a silent
    skip.

    Order: stage all pending config-mutations → snapshot once → execute
    deletions → dispatch actionable entries.
    """
    half_sup_names, duplicate_dels = _stage_deletions(items, decisions)
    pyproject = find_pyproject()
    deleted: set[str] = set()
    if (half_sup_names or duplicate_dels) and pyproject is not None:
        bak = snapshot(pyproject)
        emit_diagnostic(f"wrote {bak.name} (rollback: mv {bak.name} {pyproject.name})")
        deleted = _execute_deletions(pyproject, half_sup_names, duplicate_dels)
    action_results = _dispatch_actionable(items)
    return action_results, deleted


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
        # Build option list from occurrences, e.g. "=1 or =2 or =3" for a 3-way duplicate.
        options = " or ".join(f"={i + 1}" for i in range(len(duplicate.occurrences)))
        return (
            "ambiguous",
            f"ambiguous: duplicate name {det.name!r}",
            f"auntie doctor --apply --decide=duplicate:{det.name}{options}",
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


def _detection_fields(it: _Item) -> list[dict[str, str]]:
    """Return the base detection fields for an item."""
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
    return fields


def _gap_fields(gaps: list[ConfigGap]) -> list[dict[str, str]]:
    """Return config-gap fields (only missing-companion entries are surfaced)."""
    return [
        {"name": "config_gap", "value": gap.detail}
        for gap in gaps
        if gap.kind == "missing-companion"
    ]


def _action_fields(it: _Item, action_results: dict[str, ActionResult]) -> list[dict[str, str]]:
    """Return apply-time action fields, or an empty list when not dispatched."""
    if it.detection.name not in action_results:
        return []
    r = action_results[it.detection.name]
    fields: list[dict[str, str]] = [
        {"name": "fix_attempted", "value": "true"},
        {"name": "fix_ok", "value": "true" if r.ok else "false"},
        {"name": "fix_detail", "value": r.detail},
    ]
    if r.log_path:
        fields.append({"name": "log_path", "value": r.log_path})
    if r.pid is not None:
        fields.append({"name": "pid", "value": str(r.pid)})
    return fields


def _section_for_item(
    it: _Item,
    action_results: dict[str, ActionResult],
    deleted_names: set[str],
    applied: bool,
) -> dict[str, object]:
    """Build the payload section dict for a single item."""
    fields = _detection_fields(it)
    fields.extend(_gap_fields(it.config_gaps))
    fields.append({"name": "diagnosis", "value": it.diagnosis})
    if it.remediation:
        fields.append({"name": "remediation", "value": it.remediation})
    fields.extend(_action_fields(it, action_results))
    if applied and it.detection.name in deleted_names:
        fields.append({"name": "deleted", "value": "true"})
    return {
        "category": "servers",
        "title": it.detection.name,
        "light": _light_for(it),
        "fields": fields,
    }


def _build_payload(
    items: list[_Item],
    applied: bool,
    action_results: dict[str, ActionResult] | None = None,
    deleted_names: set[str] | None = None,
) -> dict[str, object]:
    """Build the output payload; merges apply-time results when provided."""
    action_results = action_results or {}
    deleted_names = deleted_names or set()
    sections = [_section_for_item(it, action_results, deleted_names, applied) for it in items]
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


def _summary_line(by_class: dict[str, int], total: int) -> str:
    """Return the one-line summary string."""
    parts = [
        f"{by_class.get('actionable', 0)} actionable",
        f"{by_class.get('half_supervised', 0)} half-supervised",
        f"{by_class.get('skip', 0)} skip",
        f"{by_class.get('ambiguous', 0)} ambiguous",
    ]
    return f"summary: {', '.join(parts)} ({total} total)"


def _render_item(it: _Item) -> list[str]:
    """Return the rendered lines for a single item (no trailing newline)."""
    det = it.detection
    managed = it.spec.managed_by if it.spec and it.spec.managed_by else "—"
    lines = [f"  {det.name:<20}  {det.status:<7}  {det.source:<10}  managed_by={managed}"]
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
    return lines


def _render_text(payload: dict, items: list[_Item], apply_mode: bool) -> str:
    summary = payload["summary"]
    by_class = summary["by_action_class"]
    out = [f"# {payload['subject']}", _summary_line(by_class, summary["total"]), ""]
    for it in items:
        out.extend(_render_item(it))
    actionable_count = by_class.get("actionable", 0) + by_class.get("half_supervised", 0)
    if not apply_mode:
        out.append("")
        if actionable_count:
            out.append(f"(dry-run; pass --apply to act on {actionable_count} remediations)")
        else:
            out.append("(dry-run; nothing to apply)")
    return "\n".join(out)


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
