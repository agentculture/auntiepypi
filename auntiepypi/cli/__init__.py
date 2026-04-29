"""Unified CLI entry point for auntiepypi.

Noun-based command groups and globals are registered here. Top-level globals
(``learn``, ``explain``, ``overview``, ``doctor``, ``whoami``) live under
:mod:`auntiepypi.cli._commands`.

Error-propagation contract: every handler raises
:class:`auntiepypi.cli._errors.AfiError` on failure; :func:`main` catches it
via :func:`_dispatch` and routes through :mod:`auntiepypi.cli._output`.
Unknown exceptions are wrapped so no Python traceback leaks.
"""

from __future__ import annotations

import argparse
import sys

from auntiepypi import __version__
from auntiepypi.cli._commands import doctor as _doctor_cmd
from auntiepypi.cli._commands import explain as _explain_cmd
from auntiepypi.cli._commands import learn as _learn_cmd
from auntiepypi.cli._commands import overview as _overview_cmd
from auntiepypi.cli._commands import whoami as _whoami_cmd
from auntiepypi.cli._commands._packages import overview as _packages_overview_cmd
from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError
from auntiepypi.cli._output import emit_error


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that emits errors via our structured format."""

    def error(self, message: str) -> None:  # type: ignore[override]
        err = AfiError(
            code=EXIT_USER_ERROR,
            message=message,
            remediation=f"run '{self.prog} --help' to see valid arguments",
        )
        emit_error(err, json_mode=False)
        raise SystemExit(err.code)


def _build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="auntiepypi",
        description="auntiepypi — agent-first CLI for the AgentCulture Python distribution pipe.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    _learn_cmd.register(sub)
    _explain_cmd.register(sub)
    _overview_cmd.register(sub)
    _doctor_cmd.register(sub)
    _whoami_cmd.register(sub)
    _packages_overview_cmd.register(sub)

    return parser


def _dispatch(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        return args.func(args)
    except AfiError as err:
        emit_error(err, json_mode=json_mode)
        return err.code
    except Exception as err:  # noqa: BLE001 - last-resort  # pragma: no cover
        wrapped = AfiError(
            code=EXIT_USER_ERROR,
            message=f"unexpected: {err.__class__.__name__}: {err}",
            remediation="file a bug",
        )
        emit_error(wrapped, json_mode=json_mode)
        return wrapped.code


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return _dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
