"""Lifecycle dimension — Trove ``Development Status`` classifier."""

from __future__ import annotations

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score

_PASS = {"4 - Beta", "5 - Production/Stable", "6 - Mature"}
_WARN = {"3 - Alpha"}
_FAIL = {"1 - Planning", "2 - Pre-Alpha"}

_PREFIX = "Development Status :: "


def _extract_status(pypi: dict) -> str | None:
    classifiers = (pypi.get("info") or {}).get("classifiers") or []
    for c in classifiers:
        if c.startswith(_PREFIX):
            return c[len(_PREFIX) :].strip()
    return None


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    status = _extract_status(pypi)
    if status is None:
        return DimensionResult(Score.FAIL, "absent", "no Development Status classifier")
    value = status
    reason = f"classifier: Development Status :: {status}"
    if status in _PASS:
        return DimensionResult(Score.PASS, value, reason)
    if status in _WARN:
        return DimensionResult(Score.WARN, value, reason)
    if status in _FAIL:
        return DimensionResult(Score.FAIL, value, reason)
    # Unknown classifier label — treat as fail (rubric specifies a closed set).
    return DimensionResult(Score.FAIL, value, "unrecognised Development Status")


DIMENSION = Dimension(
    name="lifecycle",
    description="Trove Development Status classifier",
    evaluate=_evaluate,
)
