"""Tests for the lifecycle dimension — Trove Development Status."""

from __future__ import annotations

import pytest

from auntiepypi._rubric import lifecycle
from auntiepypi._rubric._dimension import Score


def _pypi(classifier: str | None) -> dict:
    return {"info": {"classifiers": [classifier] if classifier else []}}


@pytest.mark.parametrize(
    "c",
    [
        "Development Status :: 4 - Beta",
        "Development Status :: 5 - Production/Stable",
        "Development Status :: 6 - Mature",
    ],
)
def test_pass_for_mature_states(c):
    assert lifecycle.DIMENSION.evaluate(_pypi(c), None).score is Score.PASS


def test_warn_for_alpha():
    r = lifecycle.DIMENSION.evaluate(_pypi("Development Status :: 3 - Alpha"), None)
    assert r.score is Score.WARN


@pytest.mark.parametrize(
    "c",
    [
        "Development Status :: 1 - Planning",
        "Development Status :: 2 - Pre-Alpha",
    ],
)
def test_fail_for_early_states(c):
    assert lifecycle.DIMENSION.evaluate(_pypi(c), None).score is Score.FAIL


def test_fail_when_no_dev_status_classifier():
    """No Development Status classifier counts as fail per spec."""
    r = lifecycle.DIMENSION.evaluate(_pypi(None), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_none():
    r = lifecycle.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert lifecycle.DIMENSION.name == "lifecycle"
    assert lifecycle.DIMENSION.description
