"""Two source fetchers: pypi.org (Warehouse JSON) and pypistats.org.

Stays a single module until a third source enters scope (osv.dev, GH
API). YAGNI; do not pre-split.
"""

from __future__ import annotations

from auntiepypi._rubric._fetch import get_json

_PYPI_URL = "https://pypi.org/pypi/{pkg}/json"
_PYPISTATS_URL = "https://pypistats.org/api/packages/{pkg}/recent"


def fetch_pypi(pkg: str) -> dict:
    """Fetch ``info`` + ``releases`` + ``urls`` for *pkg* from pypi.org."""
    return get_json(_PYPI_URL.format(pkg=pkg))


def fetch_pypistats(pkg: str) -> dict:
    """Fetch ``last_day``/``last_week``/``last_month`` for *pkg*."""
    return get_json(_PYPISTATS_URL.format(pkg=pkg))
