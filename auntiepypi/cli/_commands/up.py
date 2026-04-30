"""``auntie up`` — start a declared server (or all supervised, with --all)."""

from __future__ import annotations

import argparse

from auntiepypi.cli._commands._lifecycle import add_lifecycle_parser, run_lifecycle


def cmd_up(args: argparse.Namespace) -> int:
    return run_lifecycle(args, verb="up", action="start")


def register(sub: argparse._SubParsersAction) -> None:
    p = add_lifecycle_parser(
        sub,
        verb="up",
        help_summary="Start a declared server (or all supervised with --all).",
    )
    p.set_defaults(func=cmd_up)
