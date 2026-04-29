"""Recency dimension — days since the last non-yanked release."""

from __future__ import annotations

from datetime import datetime, timezone

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_nonyanked(pypi: dict) -> datetime | None:
    releases = pypi.get("releases") or {}
    latest: datetime | None = None
    for files in releases.values():
        for f in files or []:
            if f.get("yanked"):
                continue
            ts = f.get("upload_time_iso_8601") or f.get("upload_time")
            if not ts:
                continue
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if latest is None or t > latest:
                latest = t
    return latest


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
