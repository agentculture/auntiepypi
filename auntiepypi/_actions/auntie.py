"""Strategy for `managed_by = "auntie"`: the first-party PEP 503 server.

Builds the argv at call time from ``[tool.auntiepypi.local]`` (or
defaults when the table is absent) and delegates to the ``command``
strategy. The bare-form CLI (``auntie up`` / ``down`` / ``restart``)
synthesizes a ``ServerSpec(name="auntie", managed_by="auntie", ...)``
that lacks a literal ``command`` field; this module fills it in by
shelling out to ``sys.executable -m auntiepypi._server …``.

Why delegate rather than duplicate command.py: the v0.5.0 lifecycle
contract (PID file + sidecar + reprobe + SIGTERM/SIGKILL escalation +
port-walk fallback + argv-match guard) is already covered by
``command``; reproducing it here would be ~150 lines of drift-prone
copy. The ``auntie`` strategy is "command with a derived argv."
"""

from __future__ import annotations

import sys
from dataclasses import replace

from auntiepypi._actions import command as _command
from auntiepypi._actions._action import ActionResult
from auntiepypi._detect._config import ServerSpec, load_local_config
from auntiepypi._detect._detection import Detection
from auntiepypi._server._config import LocalConfig


def _argv(cfg: LocalConfig) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "auntiepypi._server",
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "--root",
        str(cfg.root),
    )


def _materialize(declaration: ServerSpec) -> ServerSpec:
    """Fill in ``command`` from current ``[tool.auntiepypi.local]`` and
    flip ``managed_by`` so command.py recognizes it.

    The detection's ``host``/``port`` already came from the same
    config in the bare-form path, so they should agree — but the
    config is the source of truth on each call (handles the user
    editing pyproject between start and restart).
    """
    cfg = load_local_config()
    return replace(
        declaration,
        host=cfg.host,
        port=cfg.port,
        managed_by="command",
        command=_argv(cfg),
    )


def start(detection: Detection, declaration: ServerSpec) -> ActionResult:
    materialized = _materialize(declaration)
    # Ensure the wheelhouse exists; the server itself tolerates missing
    # roots (returns empty index), but the operator probably wants the
    # directory created on first ``auntie up``.
    cfg = load_local_config()
    try:
        cfg.root.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return ActionResult(
            ok=False,
            detail=f"could not create wheelhouse {cfg.root}: {err}",
        )
    return _command.start(detection, materialized)


def stop(detection: Detection, declaration: ServerSpec) -> ActionResult:
    return _command.stop(detection, _materialize(declaration))


def restart(detection: Detection, declaration: ServerSpec) -> ActionResult:
    return _command.restart(detection, _materialize(declaration))
