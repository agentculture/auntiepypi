"""Shared core for the v0.5.0 lifecycle verbs (`up`, `down`, `restart`).

All three verbs share resolution logic, supervision filtering, exit-code
derivation, and output shape. Each verb-specific module is a thin
wrapper that supplies its action ("start", "stop", "restart") and a few
strings for help text.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Literal

from auntiepypi import _actions
from auntiepypi._actions._action import ActionResult
from auntiepypi._detect import detect_all
from auntiepypi._detect._config import ServerSpec, load_servers_lenient
from auntiepypi._detect._detection import Detection
from auntiepypi.cli._commands._decide import Decisions, parse_decisions
from auntiepypi.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, EXIT_USER_ERROR, AfiError
from auntiepypi.cli._output import emit_result

Action = Literal["start", "stop", "restart"]
SUPERVISED_MODES: frozenset[str] = frozenset({"systemd-user", "command"})


@dataclass(frozen=True)
class _Pair:
    """One target to act on."""

    name: str
    detection: Detection
    spec: ServerSpec


def _bare_invocation_message(verb: str) -> str:
    """The forward-pointing error for `auntie up` / `auntie down` /
    `auntie restart` invoked with no target and no --all.
    """
    return (
        f"auntie {verb}: the first-party auntie server lands in v0.6.0; for now "
        f"use `auntie {verb} <name>` or `auntie {verb} --all`"
    )


def _detection_for_spec(detections: list[Detection], spec: ServerSpec) -> Detection:
    """Pair each spec with its matching detection; synthesize one if missing."""
    for det in detections:
        if det.name == spec.name and det.source == "declared":
            return det
    # Fallback: build a synthetic Detection from the spec. detect_all
    # already covers this for known declarations, but if the user adds a
    # declaration after `auntie overview` ran, this keeps the action path
    # robust.
    host = spec.host or "127.0.0.1"
    # HTTP is by design here (matches _detect/_proc.py:169 and the rest
    # of the detection layer). HTTPS is deferred to v0.6.0+; see
    # docs/superpowers/specs/2026-04-30-auntiepypi-v0.5.0-...md.
    url = f"http://{host}:{spec.port}/"  # NOSONAR python:S5332
    return Detection(
        name=spec.name,
        flavor=spec.flavor or "unknown",
        host=host,
        port=spec.port,
        url=url,
        status="absent",
        source="declared",
    )


def _resolve_one_spec(target: str, specs: list[ServerSpec], decisions: Decisions) -> ServerSpec:
    """Resolve one ``<name>`` argument against `specs`, with duplicate handling."""
    matching = [s for s in specs if s.name == target]
    if not matching:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"unknown TARGET {target!r}",
            remediation=(
                "list declared servers with `auntie overview`; "
                "names come from [[tool.auntiepypi.servers]].name"
            ),
        )
    if len(matching) == 1:
        return matching[0]
    # Ambiguous: require --decide=duplicate:NAME=N
    decided = decisions.for_key("duplicate", target)
    if decided is None:
        options = " or ".join(f"={i + 1}" for i in range(len(matching)))
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=(
                f"target {target!r} is ambiguous "
                + f"({len(matching)} declarations share the name)"
            ),
            remediation=f"re-run with --decide=duplicate:{target}{options}",
        )
    idx_1based = int(decided)
    if idx_1based < 1 or idx_1based > len(matching):
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=(
                f"--decide=duplicate:{target}={decided}: index out of range "
                f"(expected 1..{len(matching)})"
            ),
            remediation="run `auntie overview` to count declarations",
        )
    return matching[idx_1based - 1]


def _supervised_specs(
    specs: list[ServerSpec],
    *,
    skipped_out: list[ServerSpec] | None = None,
) -> list[ServerSpec]:
    """Filter to supervised modes; record skipped specs in `skipped_out` if given."""
    out: list[ServerSpec] = []
    for s in specs:
        if (s.managed_by or "manual") in SUPERVISED_MODES:
            out.append(s)
        elif skipped_out is not None:
            skipped_out.append(s)
    return out


def _refuse_unsupervised(spec: ServerSpec) -> None:
    """Raise AfiError(EXIT_USER_ERROR) when an explicit target isn't supervised."""
    mode = spec.managed_by or "manual"
    raise AfiError(
        code=EXIT_USER_ERROR,
        message=(
            f"server {spec.name!r} has managed_by={mode!r} — auntie does not "
            f"supervise this mode; refusing lifecycle operation"
        ),
        remediation=(
            "use a supervised mode (systemd-user or command) in "
            "[[tool.auntiepypi.servers]] if you want auntie to act on this server"
        ),
    )


def _build_payload(verb: str, results: list[tuple[str, ActionResult]]) -> dict:
    """Uniform JSON envelope for up/down/restart."""
    return {
        "verb": verb,
        "results": [
            {
                "name": name,
                "ok": res.ok,
                "detail": res.detail,
                **({"pid": res.pid} if res.pid is not None else {}),
                **({"log_path": res.log_path} if res.log_path else {}),
            }
            for name, res in results
        ],
    }


def _render_text(verb: str, results: list[tuple[str, ActionResult]]) -> str:
    """Plain-text rendering of the lifecycle payload."""
    if not results:
        return f"auntie {verb}: nothing to do"
    lines: list[str] = []
    for name, res in results:
        marker = "ok" if res.ok else "FAIL"
        line = f"  [{marker}] {name}: {res.detail}"
        if res.pid is not None:
            line += f"  (pid={res.pid})"
        lines.append(line)
    return f"auntie {verb}:\n" + "\n".join(lines)


def _bare_invocation_error(verb: str) -> AfiError:
    return AfiError(
        code=EXIT_USER_ERROR,
        message=_bare_invocation_message(verb),
        remediation=(
            f"give a server name (`auntie {verb} <name>`) or use "
            f"`auntie {verb} --all` to act on every supervised declaration"
        ),
    )


def _collect_pairs(
    target: str | None,
    all_servers: bool,
    cfg,
    detections: list[Detection],
    decisions: Decisions,
    skipped: list[ServerSpec],
) -> list[_Pair]:
    """Build the (name, detection, spec) list for the lifecycle dispatch loop."""
    if all_servers:
        return [
            _Pair(name=s.name, detection=_detection_for_spec(detections, s), spec=s)
            for s in _supervised_specs(cfg.specs, skipped_out=skipped)
        ]
    spec = _resolve_one_spec(target or "", cfg.specs, decisions)
    if (spec.managed_by or "manual") not in SUPERVISED_MODES:
        _refuse_unsupervised(spec)
    return [_Pair(name=spec.name, detection=_detection_for_spec(detections, spec), spec=spec)]


def _emit_lifecycle_output(
    verb: str, results: list[tuple[str, ActionResult]], *, json_mode: bool
) -> None:
    payload = _build_payload(verb, results) if json_mode else _render_text(verb, results)
    emit_result(payload, json_mode=json_mode)


def run_lifecycle(args: argparse.Namespace, *, verb: str, action: Action) -> int:
    """Shared entry point for the three lifecycle verbs."""
    target = getattr(args, "target", None)
    all_servers = bool(getattr(args, "all_servers", False))
    json_mode = bool(getattr(args, "json", False))
    decisions = parse_decisions(getattr(args, "decide", None) or [])

    if target is None and not all_servers:
        raise _bare_invocation_error(verb)

    cfg, _gaps = load_servers_lenient()
    detections = detect_all(cfg)

    skipped: list[ServerSpec] = []
    pairs = _collect_pairs(target, all_servers, cfg, detections, decisions, skipped)

    results: list[tuple[str, ActionResult]] = [
        (pair.name, _actions.dispatch(action, pair.detection, pair.spec)) for pair in pairs
    ]

    _emit_lifecycle_output(verb, results, json_mode=json_mode)

    if all_servers and skipped:
        from auntiepypi.cli._output import emit_diagnostic

        names = ", ".join(f"{s.name} (managed_by={s.managed_by or 'manual'})" for s in skipped)
        emit_diagnostic(f"auntie {verb}: skipped {len(skipped)} unsupervised: {names}")

    if any(not r[1].ok for r in results):
        # Don't raise — exit 2 cleanly. Output already emitted.
        return EXIT_ENV_ERROR
    return EXIT_SUCCESS


def add_lifecycle_parser(
    sub: argparse._SubParsersAction, *, verb: str, help_summary: str
) -> argparse.ArgumentParser:
    """Build a subparser shape that's identical across up/down/restart."""
    p = sub.add_parser(verb, help=help_summary)
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help="server name; omit and pass --all to act on every supervised declaration",
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="all_servers",
        help="act on every supervised declaration (managed_by=systemd-user|command)",
    )
    p.add_argument(
        "--decide",
        action="append",
        default=[],
        help="resolve ambiguity, e.g. duplicate:NAME=N",
    )
    p.add_argument("--json", action="store_true", help="emit structured JSON")
    return p
