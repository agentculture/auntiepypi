"""Smoke tests for auntiepypi's CLI (AFI rubric)."""

from __future__ import annotations

import json

import pytest

from auntiepypi import __version__
from auntiepypi.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_no_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auntiepypi" in out
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
    assert payload["tool"] == "auntie"
    assert payload["package"] == "auntiepypi"
    assert payload["version"] == __version__
    assert payload["json_support"] is True
    assert payload["exit_codes"]["0"] == "success"
    paths = {tuple(c["path"]) for c in payload["commands"]}
    assert {("learn",), ("explain",), ("overview",), ("doctor",), ("whoami",)} <= paths
    # v0.2.0: `planned` is empty — `local` noun dropped, `servers` not added.
    assert payload["planned"] == []


def test_explain_self(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "auntiepypi"]) == 0
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


def test_explain_local_is_no_longer_in_catalog(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """v0.2.0: `local` noun was permanently dropped, not just unregistered."""
    rc = main(["explain", "local"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "no explain entry" in err


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


def test_auntie_alias_console_script_registered() -> None:
    """Both `auntie` and `auntiepypi` are registered to auntiepypi.cli:main."""
    from importlib.metadata import entry_points

    eps = entry_points(group="console_scripts")
    names = {ep.name: ep.value for ep in eps}
    assert names.get("auntie") == "auntiepypi.cli:main"
    assert names.get("auntiepypi") == "auntiepypi.cli:main"


def test_module_main_dispatches() -> None:
    """`python -m auntiepypi --version` should also work."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "auntiepypi", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_unknown_top_level_verb_fails(capsys: pytest.CaptureFixture[str]) -> None:
    """`auntie online ...` is neither in the catalog nor registered, so argparse rejects it."""
    with pytest.raises(SystemExit) as exc:
        main(["online", "status", "shushu"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "error:" in err
    assert "hint:" in err


def test_explain_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    """Cover explain's --json branch (line 21 of explain.py)."""
    rc = main(["explain", "--json", "auntiepypi"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "markdown" in payload
    assert "path" in payload
    assert payload["path"] == ["auntiepypi"]


def test_explain_known_paths() -> None:
    """Cover the known_paths() function in explain/__init__.py (line 24)."""
    from auntiepypi.explain import known_paths

    paths = known_paths()
    assert isinstance(paths, list)
    assert len(paths) > 0
    # Root and all registered verbs should be present.
    assert any(p == () for p in paths)
    assert any("learn" in p for p in paths)


def test_catalog_has_packages_entry():
    from auntiepypi.explain.catalog import ENTRIES

    assert ("packages",) in ENTRIES
    assert ("packages", "overview") in ENTRIES
    assert ("online",) not in ENTRIES


def test_catalog_root_mentions_packages_overview():
    from auntiepypi.explain.catalog import ENTRIES

    root = ENTRIES[("auntiepypi",)]
    assert "auntie packages overview" in root


def test_catalog_drops_local_noun():
    """v0.2.0: `local` is permanently removed from the catalog."""
    from auntiepypi.explain.catalog import ENTRIES

    assert ("local",) not in ENTRIES
    assert ("local", "serve") not in ENTRIES


def test_catalog_supports_auntie_alias():
    """The new `auntie` name resolves to the same root entry as `auntiepypi`."""
    from auntiepypi.explain.catalog import ENTRIES

    assert ENTRIES[("auntie",)] == ENTRIES[("auntiepypi",)]


def test_learn_json_drops_online_adds_packages():
    import contextlib
    from io import StringIO

    from auntiepypi.cli import main

    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    paths = [tuple(c["path"]) for c in payload["commands"]]
    assert ("packages", "overview") in paths
    # planned is empty in v0.2.0
    assert payload["planned"] == []
