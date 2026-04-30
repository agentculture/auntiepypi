"""Tests for the `--decide` registry: parsing, validation, and resolution."""

from __future__ import annotations

import pytest

from auntiepypi.cli._commands._decide import (
    Decisions,
    parse_decisions,
)
from auntiepypi.cli._errors import AfiError


def test_parse_decisions_empty():
    d = parse_decisions([])
    assert isinstance(d, Decisions)
    assert d.for_key("duplicate", "main") is None


def test_parse_decisions_duplicate():
    d = parse_decisions(["duplicate:main=2"])
    assert d.for_key("duplicate", "main") == "2"


def test_parse_decisions_multiple():
    d = parse_decisions(["duplicate:main=1", "duplicate:other=2"])
    assert d.for_key("duplicate", "main") == "1"
    assert d.for_key("duplicate", "other") == "2"


def test_parse_decisions_unknown_key_exits_1():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["unknown:foo=1"])
    assert excinfo.value.code == 1
    assert "duplicate" in excinfo.value.remediation


def test_parse_decisions_malformed_value_exits_1():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["bogus-no-equals"])
    assert excinfo.value.code == 1


def test_parse_decisions_malformed_key_exits_1():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["duplicate=1"])  # missing the colon-name
    assert excinfo.value.code == 1


def test_for_key_returns_none_when_unspecified():
    d = parse_decisions(["duplicate:main=1"])
    assert d.for_key("duplicate", "other") is None


def test_stale_decision_value_silently_ignored():
    """A stale `--decide=duplicate:main=1` (when the duplicate is already resolved)
    is parsed without error; callers' for_key() lookups stay idempotent."""
    d = parse_decisions(["duplicate:main=1"])
    assert d.for_key("duplicate", "main") == "1"


def test_parse_decisions_duplicate_value_must_be_int():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["duplicate:main=abc"])
    assert excinfo.value.code == 1
    assert "positive integer" in excinfo.value.message


def test_parse_decisions_duplicate_value_must_be_positive():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["duplicate:main=0"])
    assert excinfo.value.code == 1
    assert "1" in excinfo.value.message  # mentions the >= 1 lower bound


def test_parse_decisions_duplicate_value_negative_rejected():
    with pytest.raises(AfiError) as excinfo:
        parse_decisions(["duplicate:main=-2"])
    assert excinfo.value.code == 1
