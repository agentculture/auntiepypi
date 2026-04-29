"""Smoke tests for agentpypi's CLI (AFI rubric)."""

from __future__ import annotations

import json

import pytest

from agentpypi import __version__
from agentpypi.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_no_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "agentpypi" in out
    assert "learn" in out


def test_learn_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["learn"]) == 0
    out = capsys.readouterr().out
    assert len(out) >= 200
    for marker in ["purpose", "commands", "exit", "--json", "explain"]:
        assert marker.lower() in out.lower()


def test_learn_json_parseable(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["learn", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool"] == "agentpypi"
    assert payload["version"] == __version__
    assert payload["json_support"] is True
    assert payload["exit_codes"]["0"] == "success"
    paths = {tuple(c["path"]) for c in payload["commands"]}
    assert {("learn",), ("explain",), ("overview",), ("doctor",), ("whoami",)} <= paths
    planned = {tuple(p["path"]) for p in payload["planned"]}
    assert ("online", "status") in planned
    assert ("local", "serve") in planned


def test_explain_self(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "agentpypi"]) == 0
    assert capsys.readouterr().out.lstrip().startswith("#")


def test_explain_root_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain"]) == 0
    assert capsys.readouterr().out.lstrip().startswith("#")


def test_explain_each_registered_verb(capsys: pytest.CaptureFixture[str]) -> None:
    for verb in ("learn", "explain", "overview", "doctor", "whoami"):
        capsys.readouterr()  # drain
        assert main(["explain", verb]) == 0, f"explain {verb} failed"
        out = capsys.readouterr().out
        assert verb in out.lower()


def test_explain_planned_nouns(capsys: pytest.CaptureFixture[str]) -> None:
    for noun in ("online", "local"):
        capsys.readouterr()
        assert main(["explain", noun]) == 0
        out = capsys.readouterr().out
        assert "planned" in out.lower()


def test_explain_unknown_path_fails_with_hint(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["explain", "zzz-not-a-real-noun"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "error:" in err
    assert "hint:" in err


def test_explain_unknown_path_json_mode(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["explain", "--json", "zzz-not-a-real-noun"])
    assert rc != 0
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1
    assert "no explain entry" in err["message"]
    assert err["remediation"]


def test_module_main_dispatches() -> None:
    """`python -m agentpypi --version` should also work."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "agentpypi", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_unknown_top_level_verb_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """`agentpypi online ...` is in the catalog but not registered as a subcommand."""
    with pytest.raises(SystemExit) as exc:
        main(["online", "status", "shushu"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "error:" in err
    assert "hint:" in err


def test_explain_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    """Cover explain's --json branch (line 21 of explain.py)."""
    rc = main(["explain", "--json", "agentpypi"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "markdown" in payload
    assert "path" in payload
    assert payload["path"] == ["agentpypi"]


def test_explain_known_paths() -> None:
    """Cover the known_paths() function in explain/__init__.py (line 24)."""
    from agentpypi.explain import known_paths

    paths = known_paths()
    assert isinstance(paths, list)
    assert len(paths) > 0
    # Root and all registered verbs should be present.
    assert any(p == () for p in paths)
    assert any("learn" in p for p in paths)
