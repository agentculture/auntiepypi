"""Tests for ActionResult dataclass."""
from __future__ import annotations

import pytest

from auntiepypi._actions._action import ActionResult


def test_action_result_required_fields():
    r = ActionResult(ok=True, detail="started")
    assert r.ok is True
    assert r.detail == "started"
    assert r.log_path is None
    assert r.pid is None


def test_action_result_all_fields():
    r = ActionResult(ok=False, detail="oops", log_path="/tmp/x.log", pid=42)
    assert r.ok is False
    assert r.log_path == "/tmp/x.log"
    assert r.pid == 42


def test_action_result_is_frozen():
    r = ActionResult(ok=True, detail="x")
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError subclasses Exception
        r.ok = False  # type: ignore[misc]
