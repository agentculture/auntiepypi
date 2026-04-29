"""Tests for `auntiepypi overview` (AFI rubric bundle 6)."""

from __future__ import annotations

import json

import pytest

from auntiepypi.cli import main


def test_overview_text_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["overview"]) == 0
    out = capsys.readouterr().out
    assert out.strip()
    assert "# auntie" in out
    # v0.1.0: servers appear by their probe name (devpi / pypiserver), not
    # as the legacy "local-pypi-servers" aggregate section header.
    assert any(name in out for name in ("devpi", "pypiserver"))


def test_overview_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    """AFI rubric: top-level keys `subject` and `sections` are required."""
    assert main(["overview", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, dict)
    assert payload["subject"] == "auntie"
    assert isinstance(payload["sections"], list)
    # v0.1.0 shape: each section carries category / title / light / fields.
    # [tool.auntiepypi].packages is now configured so the composite emits
    # packages sections first, followed by servers sections.
    assert len(payload["sections"]) >= 1
    categories = {s["category"] for s in payload["sections"]}
    assert "servers" in categories
    # Spot-check a servers section for the expected field shape.
    server_section = next(s for s in payload["sections"] if s["category"] == "servers")
    assert "title" in server_section
    assert "light" in server_section
    assert "fields" in server_section
    field_names = {f["name"] for f in server_section["fields"]}
    assert {"port", "url", "status"} <= field_names


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
    assert "# auntie" in captured.out


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
