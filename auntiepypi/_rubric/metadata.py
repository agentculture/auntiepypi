"""Metadata dimension — license, requires_python, homepage, source, README."""

from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _signals_present(info: dict) -> dict[str, bool]:
    project_urls = info.get("project_urls") or {}
    description = info.get("description") or ""
    return {
        "license": bool(info.get("license")),
        "requires_python": bool(info.get("requires_python")),
        "homepage": bool(project_urls.get("Homepage")),
        "source": bool(project_urls.get("Source")),
        "readme": len(description) > 200,
    }


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    info = pypi.get("info") or {}
    signals = _signals_present(info)
    present = sum(signals.values())
    value = f"{present}/5"
    missing = [k for k, v in signals.items() if not v]
    reason = f"present: {[k for k, v in signals.items() if v]}; missing: {missing}"
    if present == 5:
        return DimensionResult(Score.PASS, value, reason)
    if present >= 3:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="metadata",
    description="License, requires_python, Homepage, Source, README >= 200 chars",
    evaluate=_evaluate,
)
