"""Roll-up over a list of ``DimensionResult`` → traffic light.

Rules:

- Empty list → ``unknown`` (no data is no signal).
- All ``unknown`` → ``unknown``.
- Any ``FAIL`` → ``red``.
- Else if 2+ of ``WARN`` ∪ ``UNKNOWN`` → ``yellow``.
- Else → ``green``.

The ``unknown`` light short-circuits before ``red`` only when the entire
list is ``unknown``; a single ``FAIL`` overrides any number of unknowns.
"""

from __future__ import annotations

from typing import Iterable

from agentpypi._rubric._dimension import DimensionResult, Score

LIGHT_GREEN = "green"
LIGHT_YELLOW = "yellow"
LIGHT_RED = "red"
LIGHT_UNKNOWN = "unknown"


def roll_up(results: Iterable[DimensionResult]) -> str:
    items = list(results)
    if not items:
        return LIGHT_UNKNOWN
    if all(r.score is Score.UNKNOWN for r in items):
        return LIGHT_UNKNOWN
    if any(r.score is Score.FAIL for r in items):
        return LIGHT_RED
    warn_or_unknown = sum(1 for r in items if r.score in (Score.WARN, Score.UNKNOWN))
    if warn_or_unknown >= 2:
        return LIGHT_YELLOW
    return LIGHT_GREEN
