"""Recency dimension — days since the last non-yanked release."""

from __future__ import annotations

from datetime import datetime, timezone

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score
from agentpypi._rubric._releases import max_nonyanked_upload


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_nonyanked(pypi: dict) -> datetime | None:
    """Latest non-yanked upload across all versions of *pypi*."""
    per_version = [max_nonyanked_upload(files) for files in (pypi.get("releases") or {}).values()]
    times = [t for t in per_version if t is not None]
    return max(times) if times else None


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    latest = _latest_nonyanked(pypi)
    if latest is None:
        return DimensionResult(Score.UNKNOWN, "—", "no non-yanked releases")
    days = (_now() - latest).days
    value = f"{days}d"
    reason = f"last release {latest.date().isoformat()}"
    if days < 30:
        return DimensionResult(Score.PASS, value, reason)
    if days <= 90:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="recency",
    description="Days since the last non-yanked release",
    evaluate=_evaluate,
)
