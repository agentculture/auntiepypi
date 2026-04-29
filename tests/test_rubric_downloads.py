"""Tests for the downloads dimension — pypistats last_week."""

from __future__ import annotations

from auntiepypi._rubric import downloads
from auntiepypi._rubric._dimension import Score


def _stats(last_week: int) -> dict:
    return {"data": {"last_day": 0, "last_week": last_week, "last_month": 0}}


def test_pass_at_threshold():
    r = downloads.DIMENSION.evaluate(None, _stats(10))
    assert r.score is Score.PASS


def test_pass_well_above():
    r = downloads.DIMENSION.evaluate(None, _stats(1000))
    assert r.score is Score.PASS


def test_warn_3_to_9():
    r = downloads.DIMENSION.evaluate(None, _stats(5))
    assert r.score is Score.WARN


def test_warn_at_lower_boundary():
    r = downloads.DIMENSION.evaluate(None, _stats(3))
    assert r.score is Score.WARN


def test_fail_under_3():
    r = downloads.DIMENSION.evaluate(None, _stats(2))
    assert r.score is Score.FAIL


def test_unknown_when_stats_none():
    r = downloads.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_data_key_missing():
    r = downloads.DIMENSION.evaluate(None, {"unexpected": "shape"})
    assert r.score is Score.UNKNOWN


def test_unknown_when_last_week_missing():
    r = downloads.DIMENSION.evaluate(None, {"data": {"last_day": 5}})
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert downloads.DIMENSION.name == "downloads"
    assert downloads.DIMENSION.description
