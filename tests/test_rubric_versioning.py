"""Tests for the versioning dimension — PEP 440 maturity by major version."""

from __future__ import annotations

from agentpypi._rubric import versioning
from agentpypi._rubric._dimension import Score


def _pypi(version: str, n_releases: int = 1) -> dict:
    return {
        "info": {"version": version},
        "releases": {
            f"x{i}": [{"upload_time_iso_8601": "2025-01-01T00:00:00Z"}] for i in range(n_releases)
        },
    }


def test_pass_for_1_x():
    r = versioning.DIMENSION.evaluate(_pypi("1.2.3"), None)
    assert r.score is Score.PASS


def test_pass_for_2_x_with_one_release():
    r = versioning.DIMENSION.evaluate(_pypi("2.0.0", n_releases=1), None)
    assert r.score is Score.PASS


def test_warn_for_0_x_with_more_than_5_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.5.0", n_releases=10), None)
    assert r.score is Score.WARN


def test_warn_for_0_x_at_6_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.5.0", n_releases=6), None)
    assert r.score is Score.WARN


def test_fail_for_0_x_with_5_or_fewer_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.1.0", n_releases=5), None)
    assert r.score is Score.FAIL


def test_pre_release_of_1_x_stays_0_x():
    """A 1.0.0rc1 with no stable 1.0.0 stays effectively 0.x."""
    r = versioning.DIMENSION.evaluate(_pypi("1.0.0rc1", n_releases=2), None)
    assert r.score is Score.FAIL


def test_unknown_for_non_pep440_version():
    r = versioning.DIMENSION.evaluate(_pypi("not-a-version"), None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_pypi_none():
    r = versioning.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert versioning.DIMENSION.name == "versioning"
    assert versioning.DIMENSION.description


def test_pass_for_pep440_with_local_segment():
    """`1.2.3+cpu` is valid PEP 440 — should not be UNKNOWN."""
    r = versioning.DIMENSION.evaluate(_pypi("1.2.3+cpu"), None)
    assert r.score is Score.PASS


def test_warn_for_0_x_with_local_segment():
    r = versioning.DIMENSION.evaluate(_pypi("0.5.0+abc.1", n_releases=10), None)
    assert r.score is Score.WARN
