"""Distribution dimension — current release artifacts (wheel, sdist)."""

from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    urls = pypi.get("urls") or []
    types = {u.get("packagetype") for u in urls if isinstance(u, dict)}
    has_wheel = "bdist_wheel" in types
    has_sdist = "sdist" in types
    value = ",".join(sorted(t for t in types if t)) or "none"
    if has_wheel and has_sdist:
        return DimensionResult(Score.PASS, value, "both wheel and sdist present")
    if has_wheel or has_sdist:
        only = "wheel" if has_wheel else "sdist"
        return DimensionResult(Score.WARN, value, f"only {only} available")
    return DimensionResult(Score.FAIL, value, "no wheel or sdist artifacts")


DIMENSION = Dimension(
    name="distribution",
    description="Wheel and sdist artifact availability for the current release",
    evaluate=_evaluate,
)
