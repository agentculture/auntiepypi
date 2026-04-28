"""``agentpypi learn`` — the learnability affordance (shape-adapt).

Self-teaching prompt for an agent that wants to use agentpypi. Generated
from the same explain catalog so it can never describe a command that
isn't registered.

Must satisfy the agent-first rubric: >=200 chars and mention purpose,
command map, exit codes, --json, explain.
"""

from __future__ import annotations

import argparse

from agentpypi import __version__
from agentpypi.cli._output import emit_result

# Roadmap milestones — kept as constants so `learn`'s `planned` array
# can never drift out of sync with `agentpypi explain online` /
# `... explain local`. Update together when a milestone slides.
_M_ONLINE = "v0.1.0"
_M_LOCAL = "v0.2.0"

_TEXT = """\
agentpypi — both ends of the Python distribution pipe for the AgentCulture mesh.

Purpose
-------
Manage local and online PyPI surfaces for AgentCulture siblings. v0.0.1
ships local-host introspection and the agent-affordance verbs; the
`online` (sibling release orchestration) and `local` (mesh-resident
private index) noun groups are planned for later milestones.

Commands
--------
  agentpypi learn              Print this self-teaching prompt. Supports --json.
  agentpypi explain <path>...  Print markdown docs for any noun/verb path.
                               Supports --json.
  agentpypi overview           Probe localhost for known PyPI server flavors
                               (devpi:3141, pypiserver:8080); report up/down.
                               Read-only. Supports --json.
  agentpypi doctor [--fix]     Same probes plus diagnoses; with --fix, start
                               configured servers. Default is dry-run.
                               Supports --json.
  agentpypi whoami             Auth/env probe — which PyPI / TestPyPI /
                               local index is the active environment pointing
                               at? Supports --json.

Planned (not yet registered)
----------------------------
  agentpypi online status SIBLING       (v0.1.0)
  agentpypi online release SIBLING      (v0.1.0)
  agentpypi local serve | upload | mirror (v0.2.0)

Use `agentpypi explain online` or `agentpypi explain local` to read the
roadmap entry for either noun.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr are never
mixed.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  agentpypi explain agentpypi
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "agentpypi",
        "version": __version__,
        "purpose": (
            "Manage local and online PyPI surfaces for AgentCulture siblings; "
            "v0.0.1 ships local-host introspection and agent-affordance verbs."
        ),
        "commands": [
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {
                "path": ["overview"],
                "summary": "Probe localhost for PyPI server processes; report up/down.",
            },
            {
                "path": ["doctor"],
                "summary": ("Probe + diagnose local PyPI servers; with --fix, start them."),
            },
            {
                "path": ["whoami"],
                "summary": "Report configured PyPI / TestPyPI / local index.",
            },
        ],
        "planned": [
            {"path": ["online", "status"], "milestone": _M_ONLINE},
            {"path": ["online", "release"], "milestone": _M_ONLINE},
            {"path": ["local", "serve"], "milestone": _M_LOCAL},
            {"path": ["local", "upload"], "milestone": _M_LOCAL},
            {"path": ["local", "mirror"], "milestone": _M_LOCAL},
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "agentpypi explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
