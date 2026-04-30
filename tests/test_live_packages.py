"""Live-network tests against pypi.org and pypistats.org.

Opt-in via `pytest -m live`. Default test runs do NOT collect these.
A fixture wraps each test: any URLError / socket.timeout / 5xx triggers
`pytest.skip()` so upstream hiccups do not turn the build red.

Targets are stable third-party packages (requests, pip, setuptools).
Assertions are schema-only: "the dict has these keys with these types".
Values drift over time and are not asserted.
"""

from __future__ import annotations

import socket
import time

import pytest

from auntiepypi._rubric._fetch import FetchError
from auntiepypi._rubric._sources import fetch_pypi, fetch_pypistats

_TARGETS = ["requests", "pip", "setuptools"]


@pytest.fixture(autouse=True)
def _slow_down():
    """One second between live tests — be polite to upstreams."""
    yield
    time.sleep(1.0)


def _skip_on_network_error(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FetchError as err:
        if err.status is not None and 500 <= err.status < 600:
            pytest.skip(f"upstream {err.reason}")
        if err.status == 429:
            pytest.skip(f"upstream rate-limited: {err.reason}")
        if err.status is None:
            pytest.skip(f"network error: {err.reason}")
        raise
    except socket.timeout:  # pragma: no cover
        pytest.skip("network timeout")


@pytest.mark.live
@pytest.mark.parametrize("pkg", _TARGETS)
def test_pypi_response_has_required_shape(pkg):
    payload = _skip_on_network_error(fetch_pypi, pkg)
    assert isinstance(payload, dict)
    assert "info" in payload and isinstance(payload["info"], dict)
    assert isinstance(payload["info"].get("version"), str)
    assert payload["info"]["version"]
    assert "releases" in payload and isinstance(payload["releases"], dict)
    assert "urls" in payload and isinstance(payload["urls"], list)


@pytest.mark.live
@pytest.mark.parametrize("pkg", _TARGETS)
def test_pypistats_response_has_required_shape(pkg):
    payload = _skip_on_network_error(fetch_pypistats, pkg)
    assert isinstance(payload, dict)
    data = payload.get("data")
    assert isinstance(data, dict)
    assert isinstance(data.get("last_week"), int)


@pytest.mark.live
def test_overview_package_drilldown_against_real_api(monkeypatch, tmp_path, capsys):
    """End-to-end: run the v0.4.0 CLI verb (`auntie overview <pkg>`) against live APIs.

    The `packages` noun was removed in v0.4.0; package drill-down is now
    reached via TARGET resolution path 3 ("configured package") on the
    top-level `overview` verb.
    """
    import json

    from auntiepypi.cli import main

    (tmp_path / "pyproject.toml").write_text('[tool.auntiepypi]\npackages = ["requests"]\n')
    monkeypatch.chdir(tmp_path)

    try:
        rc = main(["overview", "requests", "--json"])
    except FetchError as err:  # pragma: no cover
        pytest.skip(f"upstream {err.reason}")

    if rc == 2:
        pytest.skip("all upstreams unreachable")
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    sections = payload["sections"]
    pkg_sections = [s for s in sections if s.get("title") == "requests"]
    assert len(pkg_sections) == 1
    assert pkg_sections[0]["light"] in {"green", "yellow", "red", "unknown"}
