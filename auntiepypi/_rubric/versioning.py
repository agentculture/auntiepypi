"""Versioning dimension — current PEP 440 version maturity."""

from __future__ import annotations

import re

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score

# Loose PEP 440 regex sufficient for our needs:
# epoch! major.minor[.patch] [pre] [.devN] [.postN] [+local]
_PEP440 = re.compile(
    r"^(?P<epoch>\d+!)?(?P<major>\d+)\.(?P<minor>\d+)(?:\.\d+)?"
    r"(?P<pre>(a|b|rc)\d+)?(?:\.dev\d+)?(?:\.post\d+)?"
    r"(?:\+(?:[a-zA-Z0-9]+(?:[-_.][a-zA-Z0-9]+)*))?$"
)


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    info = pypi.get("info") or {}
    version = info.get("version", "")
    match = _PEP440.match(version)
    if not match:
        return DimensionResult(Score.UNKNOWN, version or "—", "non-PEP-440 version string")
    major = int(match.group("major"))
    is_pre = match.group("pre") is not None
    n_releases = len(pypi.get("releases") or {})
    value = version
    if major >= 1 and not is_pre:
        return DimensionResult(Score.PASS, value, f"stable {major}.x line")
    # major == 0 OR pre-release of any major
    reason = f"0.x or pre-release; {n_releases} releases"
    if n_releases > 5:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="versioning",
    description="PEP 440 version maturity (>= 1.0.0 stable, else release count)",
    evaluate=_evaluate,
)
