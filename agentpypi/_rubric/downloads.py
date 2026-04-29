"""Downloads dimension — pypistats `last_week` count."""

from __future__ import annotations

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score


def _evaluate(_pypi: dict | None, stats: dict | None) -> DimensionResult:
    if stats is None:
        return DimensionResult(Score.UNKNOWN, "—", "no pypistats data")
    data = stats.get("data")
    if not isinstance(data, dict):
        return DimensionResult(Score.UNKNOWN, "—", "pypistats response missing 'data'")
    if "last_week" not in data or not isinstance(data["last_week"], int):
        return DimensionResult(Score.UNKNOWN, "—", "pypistats 'last_week' missing")
    n = data["last_week"]
    value = f"{n}/wk"
    reason = "pypistats last_week"
    if n >= 10:
        return DimensionResult(Score.PASS, value, reason)
    if n >= 3:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="downloads",
    description="Last-week download count from pypistats.org",
    evaluate=_evaluate,
)
