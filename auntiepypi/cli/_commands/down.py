"""``auntie down`` — stop a declared server (or all supervised, with --all)."""

from __future__ import annotations

import argparse

from auntiepypi.cli._commands._lifecycle import add_lifecycle_parser, run_lifecycle


def cmd_down(args: argparse.Namespace) -> int:
    return run_lifecycle(args, verb="down", action="stop")


def register(sub: argparse._SubParsersAction) -> None:
    p = add_lifecycle_parser(
        sub,
        verb="down",
        help_summary="Stop a declared server (or all supervised with --all).",
    )
    p.set_defaults(func=cmd_down)
