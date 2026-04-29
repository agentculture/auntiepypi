"""Tests for the distribution dimension — wheel/sdist artifacts."""

from __future__ import annotations

from agentpypi._rubric import distribution
from agentpypi._rubric._dimension import Score


def _pypi(*packagetypes: str) -> dict:
    return {"urls": [{"packagetype": pt} for pt in packagetypes]}


def test_pass_with_wheel_and_sdist():
    r = distribution.DIMENSION.evaluate(_pypi("bdist_wheel", "sdist"), None)
    assert r.score is Score.PASS


def test_pass_with_wheel_only_is_actually_warn():
    """Per spec: pass = wheel + sdist; sdist-only = warn; no artifacts = fail."""
    r = distribution.DIMENSION.evaluate(_pypi("bdist_wheel"), None)
    assert r.score is Score.WARN


def test_warn_with_sdist_only():
    r = distribution.DIMENSION.evaluate(_pypi("sdist"), None)
    assert r.score is Score.WARN


def test_fail_with_no_artifacts():
    r = distribution.DIMENSION.evaluate({"urls": []}, None)
    assert r.score is Score.FAIL


def test_fail_with_only_legacy_egg():
    r = distribution.DIMENSION.evaluate(_pypi("bdist_egg"), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_none():
    r = distribution.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert distribution.DIMENSION.name == "distribution"
    assert distribution.DIMENSION.description
