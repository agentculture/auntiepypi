"""Tests for `agentpypi overview` (AFI rubric bundle 6)."""

from __future__ import annotations

import json

import pytest

from agentpypi.cli import main


def test_overview_text_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["overview"]) == 0
    out = capsys.readouterr().out
    assert out.strip()
    assert "agentpypi overview" in out
    assert "local-pypi-servers" in out


def test_overview_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    """AFI rubric: top-level keys `subject` and `sections` are required."""
    assert main(["overview", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    assert payload["subject"] == "agentpypi overview"
    assert isinstance(payload["sections"], list)
    assert len(payload["sections"]) >= 1
    section = payload["sections"][0]
    assert section["name"] == "local-pypi-servers"
    assert "items" in section
    for item in section["items"]:
        assert {"name", "port", "url", "status"} <= set(item.keys())
        assert item["status"] in {"up", "down", "absent"}


def test_overview_graceful_on_unknown_target(
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    """AFI rubric: unknown target -> exit 0, zero-target report, warning."""
    bogus = str(tmp_path / "no-such-path-zzz")  # never created; pytest cleans the parent
    rc = main(["overview", bogus])
    assert rc == 0
    captured = capsys.readouterr()
    assert "warning" in captured.err.lower()
    assert "agentpypi overview" in captured.out


def test_overview_graceful_on_unknown_target_json(
    capsys: pytest.CaptureFixture[str],
    tmp_path,
) -> None:
    bogus = str(tmp_path / "no-such-path-zzz")
    rc = main(["overview", "--json", bogus])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert "note" in payload
