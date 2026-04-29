"""Tests for the cadence dimension — median gap between last 5 releases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentpypi._rubric import cadence
from agentpypi._rubric._dimension import Score

_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago: int) -> str:
    return (_NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _pypi_with_release_ages(*ages_days: int) -> dict:
    """Build a `releases` dict with one upload per given age (days ago)."""
    return {
        "releases": {
            f"1.{i}.0": [{"upload_time_iso_8601": _ts(age), "yanked": False}]
            for i, age in enumerate(ages_days)
        }
    }


def test_pass_under_15_day_median():
    # 5 releases, gaps are 5, 5, 5, 5 → median 5
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 5, 10, 15, 20), None)
    assert r.score is Score.PASS


def test_warn_15_to_60_day_median():
    # 5 releases, gaps 30, 30, 30, 30 → median 30
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 30, 60, 90, 120), None)
    assert r.score is Score.WARN


def test_fail_over_60_day_median():
    # 5 releases, gaps 90, 90, 90, 90 → median 90
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 90, 180, 270, 360), None)
    assert r.score is Score.FAIL


def test_fail_with_only_one_release():
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(10), None)
    assert r.score is Score.FAIL


def test_uses_only_last_5_releases():
    # 7 releases: oldest two should not influence the median.
    # Last 5: ages 0,5,10,15,20 → gaps 5,5,5,5 → median 5 → PASS.
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 5, 10, 15, 20, 500, 1000), None)
    assert r.score is Score.PASS


def test_yanked_releases_excluded():
    pypi = {
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": _ts(0), "yanked": False}],
            "1.1.0": [{"upload_time_iso_8601": _ts(100), "yanked": True}],
            "1.2.0": [{"upload_time_iso_8601": _ts(200), "yanked": False}],
        }
    }
    # Only 2 non-yanked → cadence over 1 gap = 200 days → FAIL
    r = cadence.DIMENSION.evaluate(pypi, None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_is_none():
    r = cadence.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_no_releases():
    r = cadence.DIMENSION.evaluate({"releases": {}}, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert cadence.DIMENSION.name == "cadence"
    assert cadence.DIMENSION.description
