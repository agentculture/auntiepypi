"""Tests for the recency dimension."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auntiepypi._rubric import recency
from auntiepypi._rubric._dimension import Score

_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze(monkeypatch):
    monkeypatch.setattr(recency, "_now", lambda: _NOW)


def _release(days_ago: int, *, yanked: bool = False) -> dict:
    ts = (_NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return {"upload_time_iso_8601": ts, "yanked": yanked}


def _pypi(*release_days: int) -> dict:
    return {"releases": {f"1.{i}.0": [_release(d)] for i, d in enumerate(release_days)}}


def test_pass_under_30_days():
    r = recency.DIMENSION.evaluate(_pypi(10), None)
    assert r.score is Score.PASS
    assert "10" in r.value


def test_warn_30_to_90_days():
    r = recency.DIMENSION.evaluate(_pypi(45), None)
    assert r.score is Score.WARN


def test_warn_at_30_days_exact_boundary():
    """30 is in the warn band per spec ('< 30' = pass, '30–90' = warn)."""
    r = recency.DIMENSION.evaluate(_pypi(30), None)
    assert r.score is Score.WARN


def test_fail_over_90_days():
    r = recency.DIMENSION.evaluate(_pypi(120), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_is_none():
    r = recency.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_no_releases():
    r = recency.DIMENSION.evaluate({"releases": {}}, None)
    assert r.score is Score.UNKNOWN


def test_yanked_releases_filtered():
    pypi = {
        "releases": {
            "1.0.0": [_release(10, yanked=True)],
            "0.9.0": [_release(120)],  # latest non-yanked is 120 days old
        }
    }
    r = recency.DIMENSION.evaluate(pypi, None)
    assert r.score is Score.FAIL


def test_dimension_metadata():
    assert recency.DIMENSION.name == "recency"
    assert recency.DIMENSION.description
