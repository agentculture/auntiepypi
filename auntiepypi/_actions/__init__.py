"""Lifecycle strategies, keyed on `managed_by` and lifecycle action.

Each strategy module under this package exposes three functions —
``start(detection, declaration)``, ``stop(detection, declaration)``,
``restart(detection, declaration)`` — each returning ``ActionResult``.
``dispatch(action, ...)`` is the only caller-facing entry point; it
never raises — unimplemented or "manual" modes return a uniform
``ActionResult`` so callers can handle every case the same way.

Adding a strategy: drop a new file under ``_actions/<managed_by>.py``
exposing ``start``, ``stop``, ``restart``, then add it to ``ACTIONS``
below. No other surgery needed.
"""

from __future__ import annotations

from typing import Callable, Literal

from auntiepypi._actions import command as _command
from auntiepypi._actions import systemd_user as _systemd_user
from auntiepypi._actions._action import ActionResult
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

Action = Literal["start", "stop", "restart"]
Strategy = Callable[[Detection, ServerSpec], ActionResult]
StrategyMap = dict[str, Strategy]

ACTIONS: dict[str, StrategyMap] = {
    "systemd-user": {
        "start": _systemd_user.start,
        "stop": _systemd_user.stop,
        "restart": _systemd_user.restart,
    },
    "command": {
        "start": _command.start,
        "stop": _command.stop,
        "restart": _command.restart,
    },
}

# Modes that are validated as legal but are intentionally "no strategy".
_NOT_IMPLEMENTED: frozenset[str] = frozenset({"docker", "compose"})

__all__ = ["ACTIONS", "ActionResult", "dispatch"]


def dispatch(action: Action, detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Route to the strategy/action for ``declaration.managed_by``.

    Never raises. Unknown / unsupervised modes return a uniform result.
    """
    mode = declaration.managed_by
    if mode in ACTIONS:
        return ACTIONS[mode][action](detection, declaration)
    if mode in _NOT_IMPLEMENTED:
        return ActionResult(
            ok=False,
            detail=f"managed_by={mode!r} not implemented",
        )
    # mode is None ("manual" by spec) or "manual"
    return ActionResult(
        ok=False,
        detail="manual / unset — auntie does not supervise; you do",
    )
