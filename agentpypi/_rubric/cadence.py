"""Cadence dimension — median gap (days) between the last 5 releases."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score


def _nonyanked_uploads(pypi: dict) -> list[datetime]:
    out: list[datetime] = []
    for files in (pypi.get("releases") or {}).values():
        for f in files or []:
            if f.get("yanked"):
                continue
            ts = f.get("upload_time_iso_8601") or f.get("upload_time")
            if not ts:
                continue
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            out.append(t)
    return sorted(out)


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    uploads = _nonyanked_uploads(pypi)
    if not uploads:
        return DimensionResult(Score.UNKNOWN, "—", "no non-yanked releases")
    if len(uploads) == 1:
        return DimensionResult(Score.FAIL, "1 release", "only one non-yanked release")
    last5 = uploads[-5:]
    gaps_days = [(b - a).days for a, b in zip(last5, last5[1:])]
    med = median(gaps_days)
    value = f"{med:.0f}d median ({len(uploads)} releases)"
    reason = f"gaps over last {len(last5)}: {gaps_days}"
    if med < 15:
        return DimensionResult(Score.PASS, value, reason)
    if med <= 60:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="cadence",
    description="Median gap (days) between the last 5 non-yanked releases",
    evaluate=_evaluate,
)
