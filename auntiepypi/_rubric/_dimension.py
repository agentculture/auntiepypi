"""Type vocabulary for the rubric.

A ``Dimension`` is a pure scoring function over the two source dicts
(PyPI Warehouse JSON, pypistats recent JSON), each of which may be
``None`` when the corresponding fetch failed. The function returns a
``DimensionResult`` carrying a ``Score`` plus a short observation string
(``value``) and a short explanation (``reason``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class Score(Enum):
    """Per-dimension score. Stable string values are emitted to JSON."""

    PASS = "pass"  # nosec B105 — not a password, it's a score enum value  # noqa: S105
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DimensionResult:
    """Outcome of evaluating one dimension against one package's data."""

    score: Score
    value: str
    reason: str


EvaluateFn = Callable[[dict | None, dict | None], DimensionResult]


@dataclass(frozen=True)
class Dimension:
    """One rubric dimension. ``evaluate`` must be pure."""

    name: str
    description: str
    evaluate: EvaluateFn
