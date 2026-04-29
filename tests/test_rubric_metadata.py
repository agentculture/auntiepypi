"""Tests for the metadata dimension — five metadata signals."""

from __future__ import annotations

from auntiepypi._rubric import metadata
from auntiepypi._rubric._dimension import Score


def _info(**kwargs) -> dict:
    base = {
        "license": None,
        "requires_python": None,
        "project_urls": None,
        "description": "",
    }
    base.update(kwargs)
    return {"info": base}


def _all_present_info() -> dict:
    return _info(
        license="MIT",
        requires_python=">=3.9",
        project_urls={"Homepage": "h", "Source": "s"},
        description="x" * 250,
    )


def test_pass_with_all_5_signals():
    r = metadata.DIMENSION.evaluate(_all_present_info(), None)
    assert r.score is Score.PASS


def test_warn_with_4_of_5():
    info = _all_present_info()
    info["info"]["description"] = "short"  # under 200 chars → drops one
    r = metadata.DIMENSION.evaluate(info, None)
    assert r.score is Score.WARN


def test_warn_with_3_of_5():
    info = _all_present_info()
    info["info"]["description"] = "short"
    info["info"]["requires_python"] = None
    r = metadata.DIMENSION.evaluate(info, None)
    assert r.score is Score.WARN


def test_fail_with_2_of_5():
    info = _all_present_info()
    info["info"]["description"] = "short"
    info["info"]["requires_python"] = None
    info["info"]["license"] = None
    r = metadata.DIMENSION.evaluate(info, None)
    assert r.score is Score.FAIL


def test_fail_when_project_urls_missing_homepage_and_source():
    info = _all_present_info()
    info["info"]["project_urls"] = {"Documentation": "d"}  # no Homepage/Source
    info["info"]["license"] = None
    info["info"]["requires_python"] = None
    info["info"]["description"] = "short"
    r = metadata.DIMENSION.evaluate(info, None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_none():
    r = metadata.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert metadata.DIMENSION.name == "metadata"
    assert metadata.DIMENSION.description
