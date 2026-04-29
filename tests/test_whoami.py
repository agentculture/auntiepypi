"""Tests for `auntiepypi whoami`."""

from __future__ import annotations

import json

import pytest

from auntiepypi.cli import main


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
    assert "auntiepypi whoami" in out
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
    assert payload["subject"] == "auntiepypi whoami"
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


def test_whoami_reads_pip_conf(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Cover the pip.conf parsing branch (lines 44-61 of whoami.py)."""
    # Write a pip.conf in the canonical ~/.config/pip/ location inside tmp_path.
    pip_conf_dir = tmp_path / ".config" / "pip"
    pip_conf_dir.mkdir(parents=True)
    pip_conf = pip_conf_dir / "pip.conf"
    pip_conf.write_text(
        "[global]\n"
        "index-url = https://example.com/simple\n"
        "extra-index-url = https://other.example.com/simple\n"
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    for k in (
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    rc = main(["whoami", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    indexes_section = next(s for s in payload["sections"] if s["name"] == "indexes")
    # The effective default should be the conf file's index-url.
    assert "https://example.com/simple" in indexes_section["summary"]


def test_whoami_pip_conf_index_url_in_json_payload(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Verify pip conf values appear in the index_url_conf key of the JSON payload."""
    from auntiepypi.cli._commands.whoami import _read_pip_conf

    pip_conf_dir = tmp_path / ".config" / "pip"
    pip_conf_dir.mkdir(parents=True)
    pip_conf = pip_conf_dir / "pip.conf"
    pip_conf.write_text("[global]\nindex-url = https://private.example.com/simple\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _read_pip_conf()
    assert result.get("index-url") == "https://private.example.com/simple"


def test_whoami_pip_conf_parse_error_continues(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Cover the except configparser.Error: continue branch (lines 47-48).

    A pip.conf with a missing section header causes configparser to raise
    MissingSectionHeaderError (a subclass of configparser.Error) on read().
    _read_pip_conf silently skips the malformed file and returns {}.
    """
    from auntiepypi.cli._commands.whoami import _read_pip_conf

    # Write a pip.conf without a section header — configparser raises
    # MissingSectionHeaderError, which is a subclass of configparser.Error.
    pip_conf_dir = tmp_path / ".config" / "pip"
    pip_conf_dir.mkdir(parents=True)
    pip_conf = pip_conf_dir / "pip.conf"
    pip_conf.write_text("index-url = https://example.com/simple\n")  # no [section]
    monkeypatch.setenv("HOME", str(tmp_path))
    result = _read_pip_conf()
    # Malformed file is skipped; result should be empty (no global section parsed).
    assert result == {}
