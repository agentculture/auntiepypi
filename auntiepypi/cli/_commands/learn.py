"""``auntie learn`` — the learnability affordance (shape-adapt).

Self-teaching prompt for an agent that wants to use auntie. Generated
from the same explain catalog so it can never describe a command that
isn't registered.

Must satisfy the agent-first rubric: >=200 chars and mention purpose,
command map, exit codes, --json, explain.
"""

from __future__ import annotations

import argparse

from auntiepypi import __version__
from auntiepypi.cli._output import emit_result

_TEXT = """\
auntie — CLI and agent for managing PyPI packages across the AgentCulture mesh.

Purpose
-------
auntie is both a CLI and an agent that maintains, uses, and serves the
CLI for managing PyPI packages. It surfaces remote (pypi.org) package
data and a detect-only view of locally running PyPI servers. It overviews
packages and servers — informational, not gating.

Commands
--------
  auntie learn                 Print this self-teaching prompt. Supports --json.
  auntie explain <path>...     Print markdown docs for any noun/verb path.
                               Supports --json.
  auntie overview [TARGET]     Composite: packages dashboard + detected
                               local servers. With TARGET, drills into one
                               detection name, bare flavor alias, or
                               configured package. --proc opts into a
                               /proc-based scan (Linux). Read-only.
                               Supports --json.
  auntie doctor [TARGET]       Probe + diagnose declared inventory; with
    [--apply]                  --apply, starts servers and deletes half-
    [--decide KEY=VALUE]       supervised entries. --decide resolves
                               ambiguous cases (duplicate names). Default
                               is dry-run. Supports --json.
  auntie whoami                Auth/env probe — which PyPI / TestPyPI /
                               local index is the active environment
                               pointing at? Supports --json.

Configuration
-------------
  pyproject.toml [tool.auntiepypi]
    packages = [...]                      # for overview package sections
    scan_processes = false                # opt into /proc scan; same as --proc

  pyproject.toml [[tool.auntiepypi.servers]]   # one block per server
    name = "main"
    flavor = "pypiserver"                 # | "devpi" | "unknown"
    port = 8080
    managed_by = "systemd-user"          # | "command" | "manual" | (unset)
    unit = "pypi-server.service"         # required for managed_by=systemd-user
    command = ["pypi-server", "run", "-p", "8080", "/srv/wheels"]
                                         # required for managed_by=command

The CLI registers two console scripts: `auntie` (preferred) and
`auntiepypi` (alias).

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr are never
mixed.

Exit-code policy
----------------
  0 success / dry-run / ambiguous --decide deferred / unknown TARGET
  1 configuration or usage error (cross-field validation, unknown --decide key,
    unparseable block, .bak slot exhaustion)
  2 --apply ran but at least one actionable server is still not up

More detail
-----------
  auntie explain auntiepypi
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "auntie",
        "package": "auntiepypi",
        "version": __version__,
        "purpose": (
            "CLI and agent for managing PyPI packages; surfaces remote (pypi.org) "
            "package data and a detect-only view of locally running PyPI servers."
        ),
        "commands": [
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {
                "path": ["overview"],
                "summary": (
                    "Composite: packages dashboard + detected servers. "
                    "TARGET drills into one detection, flavor, or package. "
                    "--proc opts into /proc scan."
                ),
            },
            {
                "path": ["doctor"],
                "summary": (
                    "Diagnose declared inventory; --apply to act (start servers, "
                    "delete half-supervised). Use --decide for ambiguous duplicates."
                ),
            },
            {
                "path": ["whoami"],
                "summary": "Report configured PyPI / TestPyPI / local index.",
            },
        ],
        "planned": [],
        "exit_codes": {
            "0": "success / dry-run / ambiguous --decide deferred / unknown TARGET",
            "1": "configuration or usage error",
            "2": "--apply ran but at least one actionable server is still not up",
        },
        "json_support": True,
        "explain_pointer": "auntie explain <path>",
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
