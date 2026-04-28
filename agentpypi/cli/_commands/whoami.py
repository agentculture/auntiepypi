"""``agentpypi whoami`` — placeholder; real implementation lands in step 5."""

from __future__ import annotations

import argparse

from agentpypi.cli._errors import EXIT_ENV_ERROR, AfiError


def cmd_whoami(args: argparse.Namespace) -> int:  # pragma: no cover - replaced in step 5
    raise AfiError(
        code=EXIT_ENV_ERROR,
        message="whoami is not yet wired (step 3 placeholder)",
        remediation="finish step 5 of the v0.0.1 plan",
    )


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "whoami",
        help="Report configured PyPI / TestPyPI / local index from pip/uv config.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_whoami)
