"""Tests for _rubric/_runtime.roll_up — pure logic over Score lists."""

from __future__ import annotations

import pytest

from auntiepypi._rubric._dimension import DimensionResult, Score
from auntiepypi._rubric._runtime import roll_up


def _r(score: Score) -> DimensionResult:
    return DimensionResult(score=score, value="x", reason="x")


def test_empty_results_is_unknown():
    assert roll_up([]) == "unknown"


def test_all_unknown_is_unknown():
    assert roll_up([_r(Score.UNKNOWN), _r(Score.UNKNOWN)]) == "unknown"


def test_any_fail_is_red():
    assert roll_up([_r(Score.PASS), _r(Score.FAIL), _r(Score.PASS)]) == "red"


def test_two_warns_is_yellow():
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.WARN)]) == "yellow"


def test_one_warn_one_unknown_is_yellow():
    """Unknown counts as warn for the yellow threshold."""
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.UNKNOWN)]) == "yellow"


def test_one_warn_zero_unknown_is_green():
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.PASS)]) == "green"


def test_all_pass_is_green():
    assert roll_up([_r(Score.PASS), _r(Score.PASS)]) == "green"


def test_fail_takes_priority_over_unknown():
    assert roll_up([_r(Score.UNKNOWN), _r(Score.UNKNOWN), _r(Score.FAIL)]) == "red"


@pytest.mark.parametrize(
    "score,expected_value",
    [(Score.PASS, "pass"), (Score.WARN, "warn"), (Score.FAIL, "fail"), (Score.UNKNOWN, "unknown")],
)
def test_score_enum_values(score, expected_value):
    assert score.value == expected_value


def test_evaluate_package_returns_one_result_per_dimension():
    from auntiepypi._rubric import DIMENSIONS, _runtime

    minimal_pypi = {
        "info": {
            "version": "1.0.0",
            "license": "MIT",
            "requires_python": ">=3.10",
            "project_urls": {"Homepage": "h", "Source": "s"},
            "description": "x" * 250,
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        },
        "releases": {"1.0.0": [{"upload_time_iso_8601": "2026-04-25T00:00:00Z", "yanked": False}]},
        "urls": [{"packagetype": "bdist_wheel"}, {"packagetype": "sdist"}],
    }
    minimal_stats = {"data": {"last_week": 100}}

    results = _runtime.evaluate_package(minimal_pypi, minimal_stats)
    assert len(results) == len(DIMENSIONS)
    assert {r.score.value for r in results} <= {"pass", "warn", "fail", "unknown"}


def test_dimensions_registry_has_seven_entries():
    from auntiepypi._rubric import DIMENSIONS

    names = [d.name for d in DIMENSIONS]
    assert names == [
        "recency",
        "cadence",
        "downloads",
        "lifecycle",
        "distribution",
        "metadata",
        "versioning",
    ]
