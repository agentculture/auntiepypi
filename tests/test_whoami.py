"""Tests for `agentpypi whoami`."""

from __future__ import annotations

import json

import pytest

from agentpypi.cli import main


def test_whoami_text(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force a known env shape so the test is deterministic regardless of the
    # developer's actual pip/uv config.
    for k in (
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    rc = main(["whoami"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "agentpypi whoami" in out
    assert "indexes" in out


def test_whoami_json_default_index(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    for k in (
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    # Point HOME at a guaranteed-empty pytest tmp dir so neither
    # ~/.config/pip/pip.conf nor ~/.pip/pip.conf can be picked up. This
    # exercises the env-only resolution path deterministically.
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = main(["whoami", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "agentpypi whoami"
    assert payload["defaults"]["pypi"] == "https://pypi.org/simple"
    indexes_section = next(s for s in payload["sections"] if s["name"] == "indexes")
    assert indexes_section["summary"].endswith("https://pypi.org/simple")


def test_whoami_picks_up_pip_index_url_env(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PIP_INDEX_URL", "https://example.test/simple")
    rc = main(["whoami", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    indexes_section = next(s for s in payload["sections"] if s["name"] == "indexes")
    assert "https://example.test/simple" in indexes_section["summary"]
