"""Tests for _rubric/_runtime.roll_up — pure logic over Score lists."""

from __future__ import annotations

import pytest

from agentpypi._rubric._dimension import DimensionResult, Score
from agentpypi._rubric._runtime import roll_up


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
