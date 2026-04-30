"""Lifecycle strategies, keyed on `managed_by`.

Each strategy module under this package exposes an ``apply(detection,
declaration) -> ActionResult`` function. ``dispatch()`` is the only
caller-facing entry point; it never raises — unimplemented or "manual"
modes return a uniform ``ActionResult`` so doctor's loop can handle
every case the same way.

Adding a strategy: drop a new file under ``_actions/<managed_by>.py``
exposing ``apply``, then add it to ``ACTIONS`` below. No other surgery
needed.
"""

from __future__ import annotations

from typing import Callable

from auntiepypi._actions._action import ActionResult
from auntiepypi._actions.command import apply as _command_apply
from auntiepypi._actions.systemd_user import apply as _systemd_user_apply
from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

Strategy = Callable[[Detection, ServerSpec], ActionResult]

ACTIONS: dict[str, Strategy] = {
    "systemd-user": _systemd_user_apply,
    "command": _command_apply,
}

# Modes that are validated as legal but are intentionally "no strategy".
_NOT_IMPLEMENTED: frozenset[str] = frozenset({"docker", "compose"})

__all__ = ["ACTIONS", "ActionResult", "dispatch"]


def dispatch(detection: Detection, declaration: ServerSpec) -> ActionResult:
    """Route to the strategy for ``declaration.managed_by``.

    Never raises. Unknown / unsupervised modes return a uniform result.
    """
    mode = declaration.managed_by
    if mode in ACTIONS:
        return ACTIONS[mode](detection, declaration)
    if mode in _NOT_IMPLEMENTED:
        return ActionResult(
            ok=False,
            detail=f"managed_by={mode!r} not implemented in v0.4.0",
        )
    # mode is None ("manual" by spec) or "manual"
    return ActionResult(
        ok=False,
        detail="manual / unset — auntie does not supervise; you do",
    )
