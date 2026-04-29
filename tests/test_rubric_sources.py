"""Tests for fetch_pypi / fetch_pypistats — thin wrappers over get_json."""

from __future__ import annotations

import pytest

from auntiepypi._rubric import _sources
from auntiepypi._rubric._fetch import FetchError


def test_fetch_pypi_calls_get_json_with_correct_url(monkeypatch):
    captured = {}

    def fake_get_json(url, *, timeout=5.0):
        captured["url"] = url
        captured["timeout"] = timeout
        return {"info": {"name": "requests"}}

    monkeypatch.setattr(_sources, "get_json", fake_get_json)
    result = _sources.fetch_pypi("requests")
    assert captured["url"] == "https://pypi.org/pypi/requests/json"
    assert result == {"info": {"name": "requests"}}


def test_fetch_pypistats_calls_get_json_with_correct_url(monkeypatch):
    captured = {}

    def fake_get_json(url, *, timeout=5.0):
        captured["url"] = url
        return {"data": {"last_week": 100}}

    monkeypatch.setattr(_sources, "get_json", fake_get_json)
    _sources.fetch_pypistats("requests")
    assert captured["url"] == "https://pypistats.org/api/packages/requests/recent"


def test_fetch_pypi_propagates_fetcherror(monkeypatch):
    def boom(url, *, timeout=5.0):
        raise FetchError("http 404", status=404)

    monkeypatch.setattr(_sources, "get_json", boom)
    with pytest.raises(FetchError):
        _sources.fetch_pypi("nope")
