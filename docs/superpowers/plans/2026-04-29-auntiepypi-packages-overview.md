# auntiepypi v0.1.0 — `packages overview` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `packages` noun with one verb (`packages overview [PKG]`), promote the top-level `overview` to a composite of `packages` + `servers` sections, and harden the test/CI posture (95% coverage, opt-in live tests, pre/post-deploy smoke).

**Architecture:** Per-dimension plugin under `auntiepypi/_rubric/`, parallel to the existing `auntiepypi/_probes/`. Read-only, stdlib-only HTTP against pypi.org JSON + pypistats.org. Section JSON shape standardises on `{category, title, light, fields}` (breaking change vs v0.0.1's `{name, summary, items}` — only this PR has both shapes in flight).

**Tech Stack:** Python ≥ 3.12 stdlib only (`urllib.request`, `tomllib`, `concurrent.futures`, `dataclasses`, `enum`); pytest + pytest-xdist + pytest-cov; argparse.

**Spec:** `docs/superpowers/specs/2026-04-29-auntiepypi-packages-overview-design.md`.

---

## File map

**New files:**

- `auntiepypi/_packages_config.py` — load `[tool.auntiepypi].packages` from `pyproject.toml` (walks up from CWD).
- `auntiepypi/_rubric/__init__.py` — `DIMENSIONS` registry.
- `auntiepypi/_rubric/_dimension.py` — `Score`, `DimensionResult`, `Dimension` types.
- `auntiepypi/_rubric/_runtime.py` — `roll_up`, `evaluate_package`, deep-dive renderer.
- `auntiepypi/_rubric/_fetch.py` — `get_json`, `FetchError`.
- `auntiepypi/_rubric/_sources.py` — `fetch_pypi`, `fetch_pypistats`.
- `auntiepypi/_rubric/recency.py`
- `auntiepypi/_rubric/cadence.py`
- `auntiepypi/_rubric/downloads.py`
- `auntiepypi/_rubric/lifecycle.py`
- `auntiepypi/_rubric/distribution.py`
- `auntiepypi/_rubric/metadata.py`
- `auntiepypi/_rubric/versioning.py`
- `auntiepypi/cli/_commands/_packages/__init__.py`
- `auntiepypi/cli/_commands/_packages/overview.py`
- `tests/_fixtures/__init__.py`
- `tests/_fixtures/online/__init__.py`
- `tests/_fixtures/online/pypi_requests.json` — trimmed real Warehouse JSON
- `tests/_fixtures/online/pypistats_requests.json`
- `tests/test_packages_config.py`
- `tests/test_rubric_fetch.py`
- `tests/test_rubric_sources.py`
- `tests/test_rubric_runtime.py`
- `tests/test_rubric_recency.py`
- `tests/test_rubric_cadence.py`
- `tests/test_rubric_downloads.py`
- `tests/test_rubric_lifecycle.py`
- `tests/test_rubric_distribution.py`
- `tests/test_rubric_metadata.py`
- `tests/test_rubric_versioning.py`
- `tests/test_cli_packages.py`
- `tests/test_cli_overview_composite.py`
- `tests/test_live_packages.py` — `@pytest.mark.live`
- `docs/about.md`

**Modified files:**

- `pyproject.toml` — version bump 0.0.2 → 0.1.0; add `[tool.auntiepypi]`; bump coverage gate to 95; register `live` marker.
- `auntiepypi/cli/__init__.py` — register the `packages` subparser.
- `auntiepypi/cli/_commands/overview.py` — promote to composite (packages + servers) with new section shape.
- `auntiepypi/cli/_commands/learn.py` — drop `online …` from `planned`; add packages overview to commands.
- `auntiepypi/explain/catalog.py` — replace `("online",)` with `("packages",)` and `("packages", "overview")`; update `_ROOT`.
- `tests/test_overview.py` — update for new `{category, title, light, fields}` section shape.
- `tests/test_cli.py` — update for new section shape if any assertions touch envelope keys.
- `.github/workflows/tests.yml` — add live job (soft on PR, blocking on main).
- `.github/workflows/publish.yml` — add pre-upload and post-upload smoke jobs.
- `CHANGELOG.md` — `## [0.1.0]` entry (handled by version-bump skill).
- `CLAUDE.md` — promote v0.1.0 surface; statement of purpose; pointer to `docs/about.md`.
- `README.md` — opening paragraph adopts statement of purpose; example block.

---

## Task 1: Bump version + open CHANGELOG entry

**Files:**

- Modify: `pyproject.toml:3`
- Modify: `CHANGELOG.md` (top)

- [ ] **Step 1: Bump version**

Edit `pyproject.toml`, change line 3:

```toml
version = "0.1.0"
```

- [ ] **Step 2: Prepend CHANGELOG entry**

Edit `CHANGELOG.md`, prepend (above the existing `## [0.0.2]` block) a placeholder for v0.1.0 that we will fill in as tasks land:

```markdown
## [0.1.0] - 2026-04-29

### Added
- `auntiepypi packages overview [PKG]` — read-only PyPI maturity dashboard / deep-dive (informational, not gating).
- Top-level `auntiepypi overview` promoted to composite of `packages` + `servers` sections.
- `_rubric/` plugin point (parallels `_probes/`) with seven dimensions: recency, cadence, downloads, lifecycle, distribution, metadata, versioning.
- `[tool.auntiepypi].packages` config block in `pyproject.toml`.
- `@pytest.mark.live` opt-in network suite + CI wiring (soft on PR, blocking on main).
- Pre/post-deploy smoke jobs in `publish.yml`.
- `docs/about.md` — non-technical explainer.

### Changed
- Section JSON shape standardises on `{category, title, light, fields}`. Existing v0.0.1 server-flavor sections gain `category: "servers"`.
- Coverage gate: 60% → 95%.
```

- [ ] **Step 3: Run tests, confirm clean**

```bash
uv run pytest -n auto -q
```

Expected: 32 passed.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "v0.1.0: open milestone (version + CHANGELOG entry)"
```

---

## Task 2: Bump coverage gate to 95% with documented allowlist

**Files:**

- Modify: `pyproject.toml:55-62`
- Modify: `auntiepypi/__main__.py` (add pragma)
- Modify: `auntiepypi/cli/__init__.py:65-72` (add pragma)
- Modify: `auntiepypi/_probes/_runtime.py:74-80` (add pragma; defensive OSError fallback)

- [ ] **Step 1: Bump fail_under and broaden exclude_lines**

Edit `pyproject.toml`, replace lines 55-62:

```toml
[tool.coverage.report]
fail_under = 95
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if __name__ == .__main__.",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

- [ ] **Step 2: Add pragma to last-resort exception handler**

Edit `auntiepypi/cli/__init__.py`, the `except Exception` block at lines 65-72. Replace:

```python
    except Exception as err:  # noqa: BLE001 - last-resort
        wrapped = AfiError(
            code=EXIT_USER_ERROR,
            message=f"unexpected: {err.__class__.__name__}: {err}",
            remediation="file a bug",
        )
        emit_error(wrapped, json_mode=json_mode)
        return wrapped.code
```

with:

```python
    except Exception as err:  # noqa: BLE001 - last-resort  # pragma: no cover
        wrapped = AfiError(
            code=EXIT_USER_ERROR,
            message=f"unexpected: {err.__class__.__name__}: {err}",
            remediation="file a bug",
        )
        emit_error(wrapped, json_mode=json_mode)
        return wrapped.code
```

- [ ] **Step 3: Add pragma to `_probes/_runtime.py` OSError fallback**

In `auntiepypi/_probes/_runtime.py`, the `except OSError as err` block (lines 74-86). Add `# pragma: no cover` to the `except` line:

```python
    except OSError as err:  # pragma: no cover
        # OSError is the umbrella class here:
        #   - urllib.error.URLError derives from OSError (covers DNS, refused, …)
        #   - TimeoutError derives from OSError (covers urllib timeout=…)
        # Catching just OSError keeps SonarRule python:S5713 happy and is
        # exactly equivalent to the prior tuple.
        return {
            "name": probe.name,
            "port": p,
            "url": url,
            "status": "down",
            "detail": str(err),
        }
```

- [ ] **Step 4: Backfill `whoami` test coverage (highest miss)**

Read `auntiepypi/cli/_commands/whoami.py` lines 45-61. These are pip-conf parsing branches. Add a test at `tests/test_whoami.py`:

```python
def test_whoami_reads_pip_conf(tmp_path, monkeypatch):
    """Cover the pip.conf parsing branch (currently uncovered)."""
    from auntiepypi.cli._commands.whoami import cmd_whoami
    from argparse import Namespace
    pip_conf = tmp_path / "pip.conf"
    pip_conf.write_text(
        "[global]\n"
        "index-url = https://example.com/simple\n"
        "extra-index-url = https://other.example.com/simple\n"
    )
    monkeypatch.setenv("PIP_CONFIG_FILE", str(pip_conf))
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    monkeypatch.delenv("UV_INDEX_URL", raising=False)
    rc = cmd_whoami(Namespace(json=True))
    assert rc == 0
```

If `whoami.py` does not honor `PIP_CONFIG_FILE`, instead read the file directly via the function it uses (inspect the module). Adapt accordingly.

- [ ] **Step 5: Backfill `doctor` test coverage**

Read `auntiepypi/cli/_commands/doctor.py` lines 42-44, 60-63, 83, 85, 139, 141-142. These are `--fix` failure paths and the rendering of `down` items. Add a parametrised test at `tests/test_doctor.py`:

```python
def test_doctor_renders_down_with_detail(monkeypatch, capsys):
    """Cover the down-with-detail rendering branch."""
    from auntiepypi._probes._runtime import ProbeResult
    from argparse import Namespace
    from auntiepypi.cli._commands.doctor import cmd_doctor

    fake = [
        {"name": "devpi", "port": 3141, "url": "http://x", "status": "down", "detail": "http 500"},
        {"name": "pypiserver", "port": 8080, "url": "http://y", "status": "up"},
    ]
    monkeypatch.setattr("auntiepypi.cli._commands.doctor.probe_status",
                        lambda p, **kw: ProbeResult(**fake.pop(0)))
    rc = cmd_doctor(Namespace(fix=False, json=False))
    assert rc == 0
    out = capsys.readouterr().out
    assert "down" in out
    assert "http 500" in out
```

(If module-level imports differ, adapt the monkeypatch target. The intent is to drive the dry-run renderer through a `down` item with a `detail` field.)

- [ ] **Step 6: Run coverage; confirm ≥ 95%**

```bash
uv run pytest -n auto --cov=auntiepypi --cov-report=term -q
```

Expected: PASS, coverage line `Required test coverage of 95.0% reached. Total coverage: ≥95.00%`.

If coverage is still under 95%, identify remaining gaps from the `Missing` column and either add narrowly targeted tests or `# pragma: no cover` on truly unreachable defensive branches. **Do not add pragma to anything testable.**

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml auntiepypi/cli/__init__.py auntiepypi/_probes/_runtime.py tests/test_whoami.py tests/test_doctor.py
git commit -m "ci: bump coverage gate 60% → 95% with documented allowlist"
```

---

## Task 3: Register pytest `live` marker (default-skipped)

**Files:**

- Modify: `pyproject.toml:77-79`

- [ ] **Step 1: Edit `[tool.pytest.ini_options]`**

Replace lines 77-79 with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -m 'not live'"
markers = [
    "live: opt-in tests that hit pypi.org / pypistats.org over the network",
]
```

- [ ] **Step 2: Run tests, confirm marker is registered and live tests are NOT collected by default**

```bash
uv run pytest -n auto -q
```

Expected: 32+ passed (no errors about unknown markers; the existing tests still pass).

- [ ] **Step 3: Confirm opt-in works**

```bash
uv run pytest -m live -q
```

Expected: `no tests ran in 0.0Xs` (or similar — no live tests exist yet).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "test: register @pytest.mark.live marker (default-skipped)"
```

---

## Task 4: Config loader — `[tool.auntiepypi].packages`

**Files:**

- Create: `auntiepypi/_packages_config.py`
- Test: `tests/test_packages_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_packages_config.py`:

```python
"""Tests for [tool.auntiepypi].packages loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from auntiepypi._packages_config import (
    ConfigError,
    find_pyproject,
    load_package_names,
)


def _write_toml(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body)
    return p


def test_loads_simple_list(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["foo", "bar"]\n')
    assert load_package_names(tmp_path) == ["foo", "bar"]


def test_missing_table_raises(tmp_path):
    _write_toml(tmp_path, '[project]\nname = "x"\n')
    with pytest.raises(ConfigError, match="no .tool.auntiepypi..packages"):
        load_package_names(tmp_path)


def test_empty_list_raises(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = []\n')
    with pytest.raises(ConfigError, match="empty"):
        load_package_names(tmp_path)


def test_walks_up_to_find_pyproject(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["root-pkg"]\n')
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    assert load_package_names(nested) == ["root-pkg"]


def test_no_pyproject_anywhere_raises(tmp_path, monkeypatch):
    nested = tmp_path / "sub"
    nested.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ConfigError, match="no pyproject.toml"):
        load_package_names(nested)


def test_find_pyproject_returns_none_when_missing(tmp_path, monkeypatch):
    nested = tmp_path / "sub"
    nested.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    assert find_pyproject(nested) is None


def test_rejects_non_string_entries(tmp_path):
    _write_toml(tmp_path, '[tool.auntiepypi]\npackages = ["good", 42]\n')
    with pytest.raises(ConfigError, match="non-string"):
        load_package_names(tmp_path)
```

- [ ] **Step 2: Run tests; confirm fail with ImportError**

```bash
uv run pytest tests/test_packages_config.py -q
```

Expected: collection error / `ModuleNotFoundError: auntiepypi._packages_config`.

- [ ] **Step 3: Implement the loader**

Create `auntiepypi/_packages_config.py`:

```python
"""Read ``[tool.auntiepypi].packages`` from the nearest ``pyproject.toml``.

Walks up from a starting directory (default: CWD) until it finds a
``pyproject.toml`` containing the ``[tool.auntiepypi]`` table, or until it
hits ``$HOME``. No global fallback — the user's home directory is the
ceiling.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path


class ConfigError(Exception):
    """Raised when the configured package list is missing or malformed."""


def find_pyproject(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` looking for a ``pyproject.toml`` with our table.

    Returns the path or ``None`` if nothing is found before ``$HOME``.
    """
    cwd = Path(start) if start is not None else Path.cwd()
    home = Path(os.environ.get("HOME", "/"))
    cur = cwd.resolve()
    while True:
        candidate = cur / "pyproject.toml"
        if candidate.exists():
            try:
                with candidate.open("rb") as f:
                    data = tomllib.load(f)
            except (OSError, tomllib.TOMLDecodeError):
                pass
            else:
                if "tool" in data and "auntiepypi" in data["tool"]:
                    return candidate
        if cur == cur.parent or cur == home:
            return None
        cur = cur.parent


def load_package_names(start: Path | None = None) -> list[str]:
    """Return the configured list of package names.

    :raises ConfigError: when no ``pyproject.toml`` is found, the table is
        missing, the list is empty, or any entry is not a string.
    """
    found = find_pyproject(start)
    if found is None:
        raise ConfigError("no pyproject.toml with [tool.auntiepypi] found")
    with found.open("rb") as f:
        data = tomllib.load(f)
    table = data.get("tool", {}).get("auntiepypi", {})
    if "packages" not in table:
        raise ConfigError("no [tool.auntiepypi].packages key")
    pkgs = table["packages"]
    if not isinstance(pkgs, list) or not pkgs:
        raise ConfigError("[tool.auntiepypi].packages is empty or not a list")
    bad = [p for p in pkgs if not isinstance(p, str)]
    if bad:
        raise ConfigError(f"non-string entry in [tool.auntiepypi].packages: {bad!r}")
    return list(pkgs)
```

- [ ] **Step 4: Run tests; confirm pass**

```bash
uv run pytest tests/test_packages_config.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_packages_config.py tests/test_packages_config.py
git commit -m "feat(packages): config loader for [tool.auntiepypi].packages"
```

---

## Task 5: `_rubric/_dimension.py` types + `_runtime.py` roll-up

**Files:**

- Create: `auntiepypi/_rubric/__init__.py` (placeholder; later tasks fill `DIMENSIONS`)
- Create: `auntiepypi/_rubric/_dimension.py`
- Create: `auntiepypi/_rubric/_runtime.py`
- Test: `tests/test_rubric_runtime.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_runtime.py`:

```python
"""Tests for _rubric/_runtime.roll_up — pure logic over Score lists."""
from __future__ import annotations

import pytest

from auntiepypi._rubric._dimension import DimensionResult, Score
from auntiepypi._rubric._runtime import roll_up


def _r(score: Score) -> DimensionResult:
    return DimensionResult(score=score, value="x", reason="x")


def test_empty_results_is_unknown():
    assert roll_up([]) == "unknown"


def test_all_unknown_is_unknown():
    assert roll_up([_r(Score.UNKNOWN), _r(Score.UNKNOWN)]) == "unknown"


def test_any_fail_is_red():
    assert roll_up([_r(Score.PASS), _r(Score.FAIL), _r(Score.PASS)]) == "red"


def test_two_warns_is_yellow():
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.WARN)]) == "yellow"


def test_one_warn_one_unknown_is_yellow():
    """Unknown counts as warn for the yellow threshold."""
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.UNKNOWN)]) == "yellow"


def test_one_warn_zero_unknown_is_green():
    assert roll_up([_r(Score.PASS), _r(Score.WARN), _r(Score.PASS)]) == "green"


def test_all_pass_is_green():
    assert roll_up([_r(Score.PASS), _r(Score.PASS)]) == "green"


def test_fail_takes_priority_over_unknown():
    assert roll_up([_r(Score.UNKNOWN), _r(Score.UNKNOWN), _r(Score.FAIL)]) == "red"


@pytest.mark.parametrize(
    "score,expected_value",
    [(Score.PASS, "pass"), (Score.WARN, "warn"), (Score.FAIL, "fail"), (Score.UNKNOWN, "unknown")],
)
def test_score_enum_values(score, expected_value):
    assert score.value == expected_value
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_runtime.py -q
```

Expected: collection error / `ModuleNotFoundError: auntiepypi._rubric`.

- [ ] **Step 3: Create `_rubric/__init__.py` (empty placeholder)**

Create `auntiepypi/_rubric/__init__.py`:

```python
"""Rubric for ``auntiepypi packages overview`` — per-dimension plugin point.

Each module under this package exposes one ``DIMENSION``. The tuple
:data:`DIMENSIONS` is the canonical iteration order; agents see results
in this order.
"""
from __future__ import annotations

# Filled in once individual dimensions land (Tasks 8-14).
DIMENSIONS: tuple = ()
```

- [ ] **Step 4: Create `_rubric/_dimension.py`**

```python
"""Type vocabulary for the rubric.

A ``Dimension`` is a pure scoring function over the two source dicts
(PyPI Warehouse JSON, pypistats recent JSON), each of which may be
``None`` when the corresponding fetch failed. The function returns a
``DimensionResult`` carrying a ``Score`` plus a short observation string
(``value``) and a short explanation (``reason``).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Score(Enum):
    """Per-dimension score. Stable string values are emitted to JSON."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DimensionResult:
    """Outcome of evaluating one dimension against one package's data."""

    score: Score
    value: str
    reason: str


EvaluateFn = Callable[[Optional[dict], Optional[dict]], DimensionResult]


@dataclass(frozen=True)
class Dimension:
    """One rubric dimension. ``evaluate`` must be pure."""

    name: str
    description: str
    evaluate: EvaluateFn
```

- [ ] **Step 5: Create `_rubric/_runtime.py`**

```python
"""Roll-up over a list of ``DimensionResult`` → traffic light.

Rules:

- Empty list → ``unknown`` (no data is no signal).
- All ``unknown`` → ``unknown``.
- Any ``FAIL`` → ``red``.
- Else if 2+ of ``WARN`` ∪ ``UNKNOWN`` → ``yellow``.
- Else → ``green``.

The ``unknown`` light short-circuits before ``red`` only when the entire
list is ``unknown``; a single ``FAIL`` overrides any number of unknowns.
"""
from __future__ import annotations

from typing import Iterable

from auntiepypi._rubric._dimension import DimensionResult, Score

LIGHT_GREEN = "green"
LIGHT_YELLOW = "yellow"
LIGHT_RED = "red"
LIGHT_UNKNOWN = "unknown"


def roll_up(results: Iterable[DimensionResult]) -> str:
    items = list(results)
    if not items:
        return LIGHT_UNKNOWN
    if all(r.score is Score.UNKNOWN for r in items):
        return LIGHT_UNKNOWN
    if any(r.score is Score.FAIL for r in items):
        return LIGHT_RED
    warn_or_unknown = sum(1 for r in items if r.score in (Score.WARN, Score.UNKNOWN))
    if warn_or_unknown >= 2:
        return LIGHT_YELLOW
    return LIGHT_GREEN
```

- [ ] **Step 6: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_runtime.py -q
```

Expected: 12 passed (9 individual + 4 parametrised - dedupe = 12 collected items).

- [ ] **Step 7: Commit**

```bash
git add auntiepypi/_rubric/ tests/test_rubric_runtime.py
git commit -m "feat(rubric): Score / DimensionResult / Dimension types + roll-up"
```

---

## Task 6: `_rubric/_fetch.py` — stdlib HTTP helper

**Files:**

- Create: `auntiepypi/_rubric/_fetch.py`
- Test: `tests/test_rubric_fetch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_fetch.py`:

```python
"""Tests for _rubric/_fetch.get_json — stdlib urllib wrapper."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from auntiepypi._rubric._fetch import FetchError, get_json


class _Handler(BaseHTTPRequestHandler):
    """Configurable handler. Behavior set by class attrs before each test."""

    status: int = 200
    body: bytes = b'{"ok": true}'
    sleep: float = 0.0

    def do_GET(self) -> None:  # noqa: N802
        if self.sleep:
            time.sleep(self.sleep)
        self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *_: object) -> None:  # silence
        pass


@pytest.fixture
def server():
    """Start a localhost HTTP server on an ephemeral port."""
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{srv.server_address[0]}:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        thread.join(timeout=2)


def test_200_returns_dict(server):
    _Handler.status = 200
    _Handler.body = b'{"hello": "world"}'
    _Handler.sleep = 0.0
    assert get_json(server + "/x") == {"hello": "world"}


def test_404_raises_fetcherror_with_status(server):
    _Handler.status = 404
    _Handler.body = b"not found"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError) as excinfo:
        get_json(server + "/x")
    assert excinfo.value.status == 404


def test_500_raises_fetcherror_with_status(server):
    _Handler.status = 500
    _Handler.body = b"server error"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError) as excinfo:
        get_json(server + "/x")
    assert excinfo.value.status == 500


def test_malformed_json_raises_fetcherror(server):
    _Handler.status = 200
    _Handler.body = b"not json at all"
    _Handler.sleep = 0.0
    with pytest.raises(FetchError, match="unexpected response shape"):
        get_json(server + "/x")


def test_timeout_raises_fetcherror(server):
    _Handler.status = 200
    _Handler.body = b'{"ok": true}'
    _Handler.sleep = 0.5
    with pytest.raises(FetchError, match="fetch failed"):
        get_json(server + "/x", timeout=0.1)


def test_connection_refused_raises_fetcherror():
    """Use a free port that nothing is listening on."""
    with pytest.raises(FetchError, match="fetch failed"):
        get_json("http://127.0.0.1:1/", timeout=1.0)


def test_user_agent_sent(server):
    """Confirm the UA header is what we promise downstream."""
    received_ua: dict[str, str] = {}

    class CaptureHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received_ua["ua"] = self.headers.get("User-Agent", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *_: object) -> None:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), CaptureHandler)
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        url = f"http://{srv.server_address[0]}:{srv.server_address[1]}"
        get_json(url + "/x")
    finally:
        srv.shutdown()
        thr.join(timeout=2)

    assert received_ua["ua"].startswith("auntiepypi/")
    assert "github.com/agentculture/auntiepypi" in received_ua["ua"]
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_fetch.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `_fetch.py`**

Create `auntiepypi/_rubric/_fetch.py`:

```python
"""Stdlib JSON fetch helper.

One job: GET a URL with a sensible timeout and return decoded JSON, or
raise :class:`FetchError` carrying a short reason and (when applicable)
the HTTP status. No retries, no on-disk cache.
"""
from __future__ import annotations

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from auntiepypi import __version__

_UA = f"auntiepypi/{__version__} (+https://github.com/agentculture/auntiepypi)"


class FetchError(Exception):
    """Raised when the fetch failed. Carries a short reason and status."""

    def __init__(self, reason: str, *, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def get_json(url: str, *, timeout: float = 5.0) -> dict:
    """GET ``url``, return decoded JSON dict, or raise :class:`FetchError`."""
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        # URL is constructed by callers from constants + URL-safe package
        # names; no caller-controlled scheme.
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 # nosec B310
            raw = resp.read()
    except HTTPError as err:
        raise FetchError(f"http {err.code}", status=err.code) from err
    except (URLError, socket.timeout, OSError) as err:
        raise FetchError(f"fetch failed: {err.__class__.__name__}: {err}") from err

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise FetchError(f"unexpected response shape: {err}") from err
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_fetch.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/_fetch.py tests/test_rubric_fetch.py
git commit -m "feat(rubric): stdlib JSON fetch helper with FetchError"
```

---

## Task 7: `_rubric/_sources.py` — fetch_pypi + fetch_pypistats

**Files:**

- Create: `auntiepypi/_rubric/_sources.py`
- Test: `tests/test_rubric_sources.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_sources.py`:

```python
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
    result = _sources.fetch_pypistats("requests")
    assert captured["url"] == "https://pypistats.org/api/packages/requests/recent"


def test_fetch_pypi_propagates_fetcherror(monkeypatch):
    def boom(url, *, timeout=5.0):
        raise FetchError("http 404", status=404)

    monkeypatch.setattr(_sources, "get_json", boom)
    with pytest.raises(FetchError):
        _sources.fetch_pypi("nope")
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_sources.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `_sources.py`**

Create `auntiepypi/_rubric/_sources.py`:

```python
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
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_sources.py -q
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/_sources.py tests/test_rubric_sources.py
git commit -m "feat(rubric): fetch_pypi + fetch_pypistats source wrappers"
```

---

## Task 8: Dimension — `recency`

**Files:**

- Create: `auntiepypi/_rubric/recency.py`
- Test: `tests/test_rubric_recency.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_recency.py`:

```python
"""Tests for the recency dimension."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auntiepypi._rubric import recency
from auntiepypi._rubric._dimension import Score


_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze(monkeypatch):
    monkeypatch.setattr(recency, "_now", lambda: _NOW)


def _release(days_ago: int, *, yanked: bool = False) -> dict:
    ts = (_NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
    return {"upload_time_iso_8601": ts, "yanked": yanked}


def _pypi(*release_days: int) -> dict:
    return {
        "releases": {
            f"1.{i}.0": [_release(d)] for i, d in enumerate(release_days)
        }
    }


def test_pass_under_30_days():
    r = recency.DIMENSION.evaluate(_pypi(10), None)
    assert r.score is Score.PASS
    assert "10" in r.value


def test_warn_30_to_90_days():
    r = recency.DIMENSION.evaluate(_pypi(45), None)
    assert r.score is Score.WARN


def test_warn_at_30_days_exact_boundary():
    """30 is in the warn band per spec ('< 30' = pass, '30–90' = warn)."""
    r = recency.DIMENSION.evaluate(_pypi(30), None)
    assert r.score is Score.WARN


def test_fail_over_90_days():
    r = recency.DIMENSION.evaluate(_pypi(120), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_is_none():
    r = recency.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_no_releases():
    r = recency.DIMENSION.evaluate({"releases": {}}, None)
    assert r.score is Score.UNKNOWN


def test_yanked_releases_filtered():
    pypi = {
        "releases": {
            "1.0.0": [_release(10, yanked=True)],
            "0.9.0": [_release(120)],  # latest non-yanked is 120 days old
        }
    }
    r = recency.DIMENSION.evaluate(pypi, None)
    assert r.score is Score.FAIL


def test_dimension_metadata():
    assert recency.DIMENSION.name == "recency"
    assert recency.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_recency.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `recency.py`**

```python
"""Recency dimension — days since the last non-yanked release."""
from __future__ import annotations

from datetime import datetime, timezone

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _latest_nonyanked(pypi: dict) -> datetime | None:
    releases = pypi.get("releases") or {}
    latest: datetime | None = None
    for files in releases.values():
        for f in files or []:
            if f.get("yanked"):
                continue
            ts = f.get("upload_time_iso_8601") or f.get("upload_time")
            if not ts:
                continue
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if latest is None or t > latest:
                latest = t
    return latest


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    latest = _latest_nonyanked(pypi)
    if latest is None:
        return DimensionResult(Score.UNKNOWN, "—", "no non-yanked releases")
    days = (_now() - latest).days
    value = f"{days}d"
    reason = f"last release {latest.date().isoformat()}"
    if days < 30:
        return DimensionResult(Score.PASS, value, reason)
    if days <= 90:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="recency",
    description="Days since the last non-yanked release",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_recency.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/recency.py tests/test_rubric_recency.py
git commit -m "feat(rubric): recency dimension"
```

---

## Task 9: Dimension — `cadence`

**Files:**

- Create: `auntiepypi/_rubric/cadence.py`
- Test: `tests/test_rubric_cadence.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_cadence.py`:

```python
"""Tests for the cadence dimension — median gap between last 5 releases."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from auntiepypi._rubric import cadence
from auntiepypi._rubric._dimension import Score

_NOW = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


def _ts(days_ago: int) -> str:
    return (_NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def _pypi_with_release_ages(*ages_days: int) -> dict:
    """Build a `releases` dict with one upload per given age (days ago)."""
    return {
        "releases": {
            f"1.{i}.0": [{"upload_time_iso_8601": _ts(age), "yanked": False}]
            for i, age in enumerate(ages_days)
        }
    }


def test_pass_under_15_day_median():
    # 5 releases, gaps are 5, 5, 5, 5 → median 5
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 5, 10, 15, 20), None)
    assert r.score is Score.PASS


def test_warn_15_to_60_day_median():
    # 5 releases, gaps 30, 30, 30, 30 → median 30
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 30, 60, 90, 120), None)
    assert r.score is Score.WARN


def test_fail_over_60_day_median():
    # 5 releases, gaps 90, 90, 90, 90 → median 90
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(0, 90, 180, 270, 360), None)
    assert r.score is Score.FAIL


def test_fail_with_only_one_release():
    r = cadence.DIMENSION.evaluate(_pypi_with_release_ages(10), None)
    assert r.score is Score.FAIL


def test_uses_only_last_5_releases():
    # 7 releases: oldest two should not influence the median.
    # Last 5: ages 0,5,10,15,20 → gaps 5,5,5,5 → median 5 → PASS.
    r = cadence.DIMENSION.evaluate(
        _pypi_with_release_ages(0, 5, 10, 15, 20, 500, 1000), None
    )
    assert r.score is Score.PASS


def test_yanked_releases_excluded():
    pypi = {
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": _ts(0), "yanked": False}],
            "1.1.0": [{"upload_time_iso_8601": _ts(100), "yanked": True}],
            "1.2.0": [{"upload_time_iso_8601": _ts(200), "yanked": False}],
        }
    }
    # Only 2 non-yanked → cadence over 1 gap = 200 days → FAIL
    r = cadence.DIMENSION.evaluate(pypi, None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_is_none():
    r = cadence.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_no_releases():
    r = cadence.DIMENSION.evaluate({"releases": {}}, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert cadence.DIMENSION.name == "cadence"
    assert cadence.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_cadence.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `cadence.py`**

```python
"""Cadence dimension — median gap (days) between the last 5 releases."""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _nonyanked_uploads(pypi: dict) -> list[datetime]:
    out: list[datetime] = []
    for files in (pypi.get("releases") or {}).values():
        for f in files or []:
            if f.get("yanked"):
                continue
            ts = f.get("upload_time_iso_8601") or f.get("upload_time")
            if not ts:
                continue
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            out.append(t)
    return sorted(out)


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    uploads = _nonyanked_uploads(pypi)
    if not uploads:
        return DimensionResult(Score.UNKNOWN, "—", "no non-yanked releases")
    if len(uploads) == 1:
        return DimensionResult(Score.FAIL, "1 release", "only one non-yanked release")
    last5 = uploads[-5:]
    gaps_days = [(b - a).days for a, b in zip(last5, last5[1:])]
    med = median(gaps_days)
    value = f"{med:.0f}d median ({len(uploads)} releases)"
    reason = f"gaps over last {len(last5)}: {gaps_days}"
    if med < 15:
        return DimensionResult(Score.PASS, value, reason)
    if med <= 60:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="cadence",
    description="Median gap (days) between the last 5 non-yanked releases",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_cadence.py -q
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/cadence.py tests/test_rubric_cadence.py
git commit -m "feat(rubric): cadence dimension"
```

---

## Task 10: Dimension — `downloads`

**Files:**

- Create: `auntiepypi/_rubric/downloads.py`
- Test: `tests/test_rubric_downloads.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_downloads.py`:

```python
"""Tests for the downloads dimension — pypistats last_week."""
from __future__ import annotations

from auntiepypi._rubric import downloads
from auntiepypi._rubric._dimension import Score


def _stats(last_week: int) -> dict:
    return {"data": {"last_day": 0, "last_week": last_week, "last_month": 0}}


def test_pass_at_threshold():
    r = downloads.DIMENSION.evaluate(None, _stats(10))
    assert r.score is Score.PASS


def test_pass_well_above():
    r = downloads.DIMENSION.evaluate(None, _stats(1000))
    assert r.score is Score.PASS


def test_warn_3_to_9():
    r = downloads.DIMENSION.evaluate(None, _stats(5))
    assert r.score is Score.WARN


def test_warn_at_lower_boundary():
    r = downloads.DIMENSION.evaluate(None, _stats(3))
    assert r.score is Score.WARN


def test_fail_under_3():
    r = downloads.DIMENSION.evaluate(None, _stats(2))
    assert r.score is Score.FAIL


def test_unknown_when_stats_none():
    r = downloads.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_data_key_missing():
    r = downloads.DIMENSION.evaluate(None, {"unexpected": "shape"})
    assert r.score is Score.UNKNOWN


def test_unknown_when_last_week_missing():
    r = downloads.DIMENSION.evaluate(None, {"data": {"last_day": 5}})
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert downloads.DIMENSION.name == "downloads"
    assert downloads.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_downloads.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `downloads.py`**

```python
"""Downloads dimension — pypistats `last_week` count."""
from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _evaluate(_pypi: dict | None, stats: dict | None) -> DimensionResult:
    if stats is None:
        return DimensionResult(Score.UNKNOWN, "—", "no pypistats data")
    data = stats.get("data")
    if not isinstance(data, dict):
        return DimensionResult(Score.UNKNOWN, "—", "pypistats response missing 'data'")
    if "last_week" not in data or not isinstance(data["last_week"], int):
        return DimensionResult(Score.UNKNOWN, "—", "pypistats 'last_week' missing")
    n = data["last_week"]
    value = f"{n}/wk"
    reason = "pypistats last_week"
    if n >= 10:
        return DimensionResult(Score.PASS, value, reason)
    if n >= 3:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="downloads",
    description="Last-week download count from pypistats.org",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_downloads.py -q
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/downloads.py tests/test_rubric_downloads.py
git commit -m "feat(rubric): downloads dimension"
```

---

## Task 11: Dimension — `lifecycle`

**Files:**

- Create: `auntiepypi/_rubric/lifecycle.py`
- Test: `tests/test_rubric_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_lifecycle.py`:

```python
"""Tests for the lifecycle dimension — Trove Development Status."""
from __future__ import annotations

import pytest

from auntiepypi._rubric import lifecycle
from auntiepypi._rubric._dimension import Score


def _pypi(classifier: str | None) -> dict:
    return {"info": {"classifiers": [classifier] if classifier else []}}


@pytest.mark.parametrize("c", [
    "Development Status :: 4 - Beta",
    "Development Status :: 5 - Production/Stable",
    "Development Status :: 6 - Mature",
])
def test_pass_for_mature_states(c):
    assert lifecycle.DIMENSION.evaluate(_pypi(c), None).score is Score.PASS


def test_warn_for_alpha():
    r = lifecycle.DIMENSION.evaluate(_pypi("Development Status :: 3 - Alpha"), None)
    assert r.score is Score.WARN


@pytest.mark.parametrize("c", [
    "Development Status :: 1 - Planning",
    "Development Status :: 2 - Pre-Alpha",
])
def test_fail_for_early_states(c):
    assert lifecycle.DIMENSION.evaluate(_pypi(c), None).score is Score.FAIL


def test_fail_when_no_dev_status_classifier():
    """No Development Status classifier counts as fail per spec."""
    r = lifecycle.DIMENSION.evaluate(_pypi(None), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_none():
    r = lifecycle.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert lifecycle.DIMENSION.name == "lifecycle"
    assert lifecycle.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_lifecycle.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `lifecycle.py`**

```python
"""Lifecycle dimension — Trove ``Development Status`` classifier."""
from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score

_PASS = {"4 - Beta", "5 - Production/Stable", "6 - Mature"}
_WARN = {"3 - Alpha"}
_FAIL = {"1 - Planning", "2 - Pre-Alpha"}

_PREFIX = "Development Status :: "


def _extract_status(pypi: dict) -> str | None:
    classifiers = (pypi.get("info") or {}).get("classifiers") or []
    for c in classifiers:
        if c.startswith(_PREFIX):
            return c[len(_PREFIX):].strip()
    return None


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    status = _extract_status(pypi)
    if status is None:
        return DimensionResult(Score.FAIL, "absent", "no Development Status classifier")
    value = status
    reason = f"classifier: Development Status :: {status}"
    if status in _PASS:
        return DimensionResult(Score.PASS, value, reason)
    if status in _WARN:
        return DimensionResult(Score.WARN, value, reason)
    if status in _FAIL:
        return DimensionResult(Score.FAIL, value, reason)
    # Unknown classifier label — treat as fail (rubric specifies a closed set).
    return DimensionResult(Score.FAIL, value, "unrecognised Development Status")


DIMENSION = Dimension(
    name="lifecycle",
    description="Trove Development Status classifier",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_lifecycle.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/lifecycle.py tests/test_rubric_lifecycle.py
git commit -m "feat(rubric): lifecycle dimension (Trove Development Status)"
```

---

## Task 12: Dimension — `distribution`

**Files:**

- Create: `auntiepypi/_rubric/distribution.py`
- Test: `tests/test_rubric_distribution.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_distribution.py`:

```python
"""Tests for the distribution dimension — wheel/sdist artifacts."""
from __future__ import annotations

from auntiepypi._rubric import distribution
from auntiepypi._rubric._dimension import Score


def _pypi(*packagetypes: str) -> dict:
    return {"urls": [{"packagetype": pt} for pt in packagetypes]}


def test_pass_with_wheel_and_sdist():
    r = distribution.DIMENSION.evaluate(
        _pypi("bdist_wheel", "sdist"), None
    )
    assert r.score is Score.PASS


def test_pass_with_wheel_only_is_actually_warn():
    """Per spec: pass = wheel + sdist; sdist-only = warn; no artifacts = fail."""
    r = distribution.DIMENSION.evaluate(_pypi("bdist_wheel"), None)
    assert r.score is Score.WARN


def test_warn_with_sdist_only():
    r = distribution.DIMENSION.evaluate(_pypi("sdist"), None)
    assert r.score is Score.WARN


def test_fail_with_no_artifacts():
    r = distribution.DIMENSION.evaluate({"urls": []}, None)
    assert r.score is Score.FAIL


def test_fail_with_only_legacy_egg():
    r = distribution.DIMENSION.evaluate(_pypi("bdist_egg"), None)
    assert r.score is Score.FAIL


def test_unknown_when_pypi_none():
    r = distribution.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert distribution.DIMENSION.name == "distribution"
    assert distribution.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_distribution.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `distribution.py`**

```python
"""Distribution dimension — current release artifacts (wheel, sdist)."""
from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    urls = pypi.get("urls") or []
    types = {u.get("packagetype") for u in urls if isinstance(u, dict)}
    has_wheel = "bdist_wheel" in types
    has_sdist = "sdist" in types
    value = ",".join(sorted(t for t in types if t)) or "none"
    if has_wheel and has_sdist:
        return DimensionResult(Score.PASS, value, "both wheel and sdist present")
    if has_wheel or has_sdist:
        only = "wheel" if has_wheel else "sdist"
        return DimensionResult(Score.WARN, value, f"only {only} available")
    return DimensionResult(Score.FAIL, value, "no wheel or sdist artifacts")


DIMENSION = Dimension(
    name="distribution",
    description="Wheel and sdist artifact availability for the current release",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_distribution.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/distribution.py tests/test_rubric_distribution.py
git commit -m "feat(rubric): distribution dimension"
```

---

## Task 13: Dimension — `metadata`

**Files:**

- Create: `auntiepypi/_rubric/metadata.py`
- Test: `tests/test_rubric_metadata.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_metadata.py`:

```python
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
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_metadata.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `metadata.py`**

```python
"""Metadata dimension — license, requires_python, homepage, source, README."""
from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score


def _signals_present(info: dict) -> dict[str, bool]:
    project_urls = info.get("project_urls") or {}
    description = info.get("description") or ""
    return {
        "license": bool(info.get("license")),
        "requires_python": bool(info.get("requires_python")),
        "homepage": bool(project_urls.get("Homepage")),
        "source": bool(project_urls.get("Source")),
        "readme": len(description) > 200,
    }


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    info = pypi.get("info") or {}
    signals = _signals_present(info)
    present = sum(signals.values())
    value = f"{present}/5"
    missing = [k for k, v in signals.items() if not v]
    reason = f"present: {[k for k, v in signals.items() if v]}; missing: {missing}"
    if present == 5:
        return DimensionResult(Score.PASS, value, reason)
    if present >= 3:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="metadata",
    description="License, requires_python, Homepage, Source, README ≥ 200 chars",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_metadata.py -q
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/metadata.py tests/test_rubric_metadata.py
git commit -m "feat(rubric): metadata dimension"
```

---

## Task 14: Dimension — `versioning`

**Files:**

- Create: `auntiepypi/_rubric/versioning.py`
- Test: `tests/test_rubric_versioning.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rubric_versioning.py`:

```python
"""Tests for the versioning dimension — PEP 440 maturity by major version."""
from __future__ import annotations

from auntiepypi._rubric import versioning
from auntiepypi._rubric._dimension import Score


def _pypi(version: str, n_releases: int = 1) -> dict:
    return {
        "info": {"version": version},
        "releases": {f"x{i}": [{"upload_time_iso_8601": "2025-01-01T00:00:00Z"}]
                     for i in range(n_releases)},
    }


def test_pass_for_1_x():
    r = versioning.DIMENSION.evaluate(_pypi("1.2.3"), None)
    assert r.score is Score.PASS


def test_pass_for_2_x_with_one_release():
    r = versioning.DIMENSION.evaluate(_pypi("2.0.0", n_releases=1), None)
    assert r.score is Score.PASS


def test_warn_for_0_x_with_more_than_5_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.5.0", n_releases=10), None)
    assert r.score is Score.WARN


def test_warn_for_0_x_at_6_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.5.0", n_releases=6), None)
    assert r.score is Score.WARN


def test_fail_for_0_x_with_5_or_fewer_releases():
    r = versioning.DIMENSION.evaluate(_pypi("0.1.0", n_releases=5), None)
    assert r.score is Score.FAIL


def test_pre_release_of_1_x_stays_0_x():
    """A 1.0.0rc1 with no stable 1.0.0 stays effectively 0.x."""
    r = versioning.DIMENSION.evaluate(_pypi("1.0.0rc1", n_releases=2), None)
    assert r.score is Score.FAIL


def test_unknown_for_non_pep440_version():
    r = versioning.DIMENSION.evaluate(_pypi("not-a-version"), None)
    assert r.score is Score.UNKNOWN


def test_unknown_when_pypi_none():
    r = versioning.DIMENSION.evaluate(None, None)
    assert r.score is Score.UNKNOWN


def test_dimension_metadata():
    assert versioning.DIMENSION.name == "versioning"
    assert versioning.DIMENSION.description
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_versioning.py -q
```

Expected: collection error.

- [ ] **Step 3: Implement `versioning.py`**

```python
"""Versioning dimension — current PEP 440 version maturity."""
from __future__ import annotations

import re

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score

# Loose PEP 440 regex sufficient for our needs (major.minor.patch + pre/dev).
_PEP440 = re.compile(
    r"^(?P<epoch>\d+!)?(?P<major>\d+)\.(?P<minor>\d+)(?:\.\d+)?"
    r"(?P<pre>(a|b|rc)\d+)?(?:\.dev\d+)?(?:\.post\d+)?$"
)


def _evaluate(pypi: dict | None, _stats: dict | None) -> DimensionResult:
    if pypi is None:
        return DimensionResult(Score.UNKNOWN, "—", "no PyPI data")
    info = pypi.get("info") or {}
    version = info.get("version", "")
    match = _PEP440.match(version)
    if not match:
        return DimensionResult(Score.UNKNOWN, version or "—", "non-PEP-440 version string")
    major = int(match.group("major"))
    is_pre = match.group("pre") is not None
    n_releases = len(pypi.get("releases") or {})
    value = version
    if major >= 1 and not is_pre:
        return DimensionResult(Score.PASS, value, f"stable {major}.x line")
    # major == 0 OR pre-release of any major
    reason = f"0.x or pre-release; {n_releases} releases"
    if n_releases > 5:
        return DimensionResult(Score.WARN, value, reason)
    return DimensionResult(Score.FAIL, value, reason)


DIMENSION = Dimension(
    name="versioning",
    description="PEP 440 version maturity (≥ 1.0.0 stable, else release count)",
    evaluate=_evaluate,
)
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_versioning.py -q
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_rubric/versioning.py tests/test_rubric_versioning.py
git commit -m "feat(rubric): versioning dimension"
```

---

## Task 15: Wire dimensions into `_rubric/__init__.py` registry + `evaluate_package`

**Files:**

- Modify: `auntiepypi/_rubric/__init__.py`
- Modify: `auntiepypi/_rubric/_runtime.py` — add `evaluate_package`
- Test: extend `tests/test_rubric_runtime.py`

- [ ] **Step 1: Add the failing test for `evaluate_package`**

Append to `tests/test_rubric_runtime.py`:

```python
def test_evaluate_package_returns_one_result_per_dimension():
    from auntiepypi._rubric import DIMENSIONS, _runtime

    minimal_pypi = {
        "info": {
            "version": "1.0.0",
            "license": "MIT",
            "requires_python": ">=3.10",
            "project_urls": {"Homepage": "h", "Source": "s"},
            "description": "x" * 250,
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        },
        "releases": {"1.0.0": [{"upload_time_iso_8601": "2026-04-25T00:00:00Z",
                                "yanked": False}]},
        "urls": [{"packagetype": "bdist_wheel"}, {"packagetype": "sdist"}],
    }
    minimal_stats = {"data": {"last_week": 100}}

    results = _runtime.evaluate_package(minimal_pypi, minimal_stats)
    assert len(results) == len(DIMENSIONS)
    assert {r.score.value for r in results} <= {"pass", "warn", "fail", "unknown"}


def test_dimensions_registry_has_seven_entries():
    from auntiepypi._rubric import DIMENSIONS

    names = [d.name for d in DIMENSIONS]
    assert names == [
        "recency", "cadence", "downloads", "lifecycle",
        "distribution", "metadata", "versioning",
    ]
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_rubric_runtime.py::test_dimensions_registry_has_seven_entries -q
```

Expected: assertion failure (`DIMENSIONS` is empty tuple).

- [ ] **Step 3: Fill in the registry**

Replace `auntiepypi/_rubric/__init__.py`:

```python
"""Rubric for ``auntiepypi packages overview`` — per-dimension plugin point.

Each module under this package exposes one ``DIMENSION``. The tuple
:data:`DIMENSIONS` is the canonical iteration order; agents see results
in this order.
"""
from __future__ import annotations

from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score
from auntiepypi._rubric.cadence import DIMENSION as cadence
from auntiepypi._rubric.distribution import DIMENSION as distribution
from auntiepypi._rubric.downloads import DIMENSION as downloads
from auntiepypi._rubric.lifecycle import DIMENSION as lifecycle
from auntiepypi._rubric.metadata import DIMENSION as metadata
from auntiepypi._rubric.recency import DIMENSION as recency
from auntiepypi._rubric.versioning import DIMENSION as versioning

DIMENSIONS: tuple[Dimension, ...] = (
    recency,
    cadence,
    downloads,
    lifecycle,
    distribution,
    metadata,
    versioning,
)

__all__ = ["DIMENSIONS", "Dimension", "DimensionResult", "Score"]
```

- [ ] **Step 4: Add `evaluate_package` to `_runtime.py`**

Append to `auntiepypi/_rubric/_runtime.py`:

```python
def evaluate_package(
    pypi: dict | None,
    stats: dict | None,
) -> list[DimensionResult]:
    """Run every dimension over the two source dicts. Iteration order = registry order."""
    from auntiepypi._rubric import DIMENSIONS

    return [d.evaluate(pypi, stats) for d in DIMENSIONS]
```

- [ ] **Step 5: Run; confirm pass**

```bash
uv run pytest tests/test_rubric_runtime.py -q
```

Expected: all tests pass (12 prior + 2 new = 14).

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/_rubric/__init__.py auntiepypi/_rubric/_runtime.py tests/test_rubric_runtime.py
git commit -m "feat(rubric): wire DIMENSIONS registry + evaluate_package"
```

---

## Task 16: `auntiepypi packages overview` CLI verb

**Files:**

- Create: `auntiepypi/cli/_commands/_packages/__init__.py`
- Create: `auntiepypi/cli/_commands/_packages/overview.py`
- Modify: `auntiepypi/cli/__init__.py:18-23`, `:47-53`
- Test: `tests/test_cli_packages.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_packages.py`:

```python
"""Tests for `auntiepypi packages overview [PKG]`."""
from __future__ import annotations

import json

import pytest

from auntiepypi.cli import main


def _good_pypi(name: str = "x") -> dict:
    return {
        "info": {
            "name": name,
            "version": "1.0.0",
            "license": "MIT",
            "requires_python": ">=3.10",
            "project_urls": {"Homepage": "h", "Source": "s"},
            "description": "y" * 250,
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        },
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2026-04-25T00:00:00Z", "yanked": False}],
            "0.9.0": [{"upload_time_iso_8601": "2026-04-15T00:00:00Z", "yanked": False}],
        },
        "urls": [{"packagetype": "bdist_wheel"}, {"packagetype": "sdist"}],
    }


def _good_stats() -> dict:
    return {"data": {"last_week": 100}}


@pytest.fixture
def patched_sources(monkeypatch):
    from auntiepypi._rubric import _sources

    monkeypatch.setattr(_sources, "fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(_sources, "fetch_pypistats", lambda pkg: _good_stats())


def test_overview_no_arg_requires_config(tmp_path, monkeypatch, capsys):
    """Without [tool.auntiepypi].packages, no-arg form errors with code 1."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    rc = main(["packages", "overview"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "tool.auntiepypi" in err
    assert "hint:" in err


def test_overview_no_arg_emits_dashboard(tmp_path, monkeypatch, capsys, patched_sources):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.auntiepypi]\npackages = ["alpha", "beta"]\n'
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "packages"
    assert len(payload["sections"]) == 2
    for section in payload["sections"]:
        assert section["category"] == "packages"
        assert section["light"] in {"green", "yellow", "red", "unknown"}
        names = {f["name"] for f in section["fields"]}
        assert {"version", "index", "released", "downloads_w"} <= names
        index_field = next(f for f in section["fields"] if f["name"] == "index")
        assert index_field["value"] == "pypi.org"


def test_overview_with_pkg_emits_deep_dive(tmp_path, monkeypatch, capsys, patched_sources):
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "requests", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "requests"
    titles = [s["title"] for s in payload["sections"]]
    assert titles[-1] == "_summary"
    rubric_titles = set(titles[:-1])
    assert rubric_titles == {
        "recency", "cadence", "downloads", "lifecycle",
        "distribution", "metadata", "versioning",
    }
    summary = payload["sections"][-1]
    assert summary["light"] in {"green", "yellow", "red", "unknown"}


def test_overview_invalid_pkg_name_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "Bad Name With Spaces"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid package name" in err.lower() or "invalid" in err.lower()


def test_overview_unknown_to_pypi_yields_unknown_section(tmp_path, monkeypatch, capsys):
    """Package that pypi.org returns 404 for: deep-dive lights all unknown."""
    from auntiepypi._rubric import _sources
    from auntiepypi._rubric._fetch import FetchError

    def fail_pypi(pkg):
        raise FetchError("http 404", status=404)

    monkeypatch.setattr(_sources, "fetch_pypi", fail_pypi)
    monkeypatch.setattr(
        _sources, "fetch_pypistats",
        lambda pkg: (_ for _ in ()).throw(FetchError("http 404", status=404)),
    )
    monkeypatch.chdir(tmp_path)
    rc = main(["packages", "overview", "ghost-package", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["sections"][-1]
    assert summary["title"] == "_summary"
    assert summary["light"] == "unknown"
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_cli_packages.py -q
```

Expected: collection error (`packages` subcommand not registered).

- [ ] **Step 3: Create the `_packages` package**

Create `auntiepypi/cli/_commands/_packages/__init__.py`:

```python
"""`auntiepypi packages` noun group — see overview.py."""
```

- [ ] **Step 4: Create the verb implementation**

Create `auntiepypi/cli/_commands/_packages/overview.py`:

```python
"""``auntiepypi packages overview [PKG]`` — informational, not gating.

No arg → roll-up over the configured list (``[tool.auntiepypi].packages``).
With arg → deep-dive over the rubric for one package.

JSON envelope: ``{"subject", "sections": [...]}``. Each section carries
``category="packages"``, a ``title``, a rolled-up ``light``, and ``fields``.
Read-only. Exit code 0 regardless of how many packages roll up red.
"""
from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from auntiepypi._packages_config import ConfigError, load_package_names
from auntiepypi._rubric import DIMENSIONS
from auntiepypi._rubric._fetch import FetchError
from auntiepypi._rubric._runtime import evaluate_package, roll_up
from auntiepypi._rubric._sources import fetch_pypi, fetch_pypistats
from auntiepypi.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, AfiError
from auntiepypi.cli._output import emit_diagnostic, emit_result

# PEP 508 normalised name regex (per packaging.utils.canonicalize_name input).
_NAME_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")
_INDEX_VALUE = "pypi.org"


def _validate_name(pkg: str) -> None:
    if not _NAME_RE.match(pkg):
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"invalid package name: {pkg!r}",
            remediation="package names match PEP 508; letters, digits, '.', '-', '_'",
        )


def _fetch_pair(pkg: str) -> tuple[dict | None, dict | None, list[str]]:
    """Fetch both sources for one package; return (pypi, stats, warnings)."""
    warnings: list[str] = []
    pypi: dict | None = None
    stats: dict | None = None
    try:
        pypi = fetch_pypi(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypi.org {err.reason}")
        if err.status == 404:
            # Don't bother pypistats for a package PyPI doesn't know.
            return pypi, stats, warnings
    try:
        stats = fetch_pypistats(pkg)
    except FetchError as err:
        warnings.append(f"{pkg}: pypistats.org {err.reason}")
    return pypi, stats, warnings


def _section_for_package(pkg: str, pypi: dict | None, stats: dict | None) -> dict:
    results = evaluate_package(pypi, stats)
    light = roll_up(results)
    info = (pypi or {}).get("info") or {}
    version = info.get("version", "—")
    # Released-age field
    released = "—"
    for r in results:
        if r.score.value == "unknown":
            continue
        if r.value and r.value.endswith("d"):
            released = f"{r.value} ago"
            break
    # Downloads field
    downloads_w = "—"
    for r in results:
        if r.value.endswith("/wk"):
            downloads_w = r.value.removesuffix("/wk")
            break
    return {
        "category": "packages",
        "title": pkg,
        "light": light,
        "fields": [
            {"name": "version", "value": version},
            {"name": "index", "value": _INDEX_VALUE},
            {"name": "released", "value": released},
            {"name": "downloads_w", "value": downloads_w},
        ],
    }


def _section_for_dimension(pkg: str, pypi, stats, dimension) -> dict:
    result = dimension.evaluate(pypi, stats)
    return {
        "category": "packages",
        "title": dimension.name,
        "light": result.score.value,
        "fields": [
            {"name": "value", "value": result.value},
            {"name": "reason", "value": result.reason},
        ],
    }


def _deep_dive(pkg: str, pypi: dict | None, stats: dict | None) -> dict:
    sections = [_section_for_dimension(pkg, pypi, stats, d) for d in DIMENSIONS]
    rolled = roll_up([d.evaluate(pypi, stats) for d in DIMENSIONS])
    sections.append({
        "category": "packages",
        "title": "_summary",
        "light": rolled,
        "fields": [{"name": "package", "value": pkg}],
    })
    return {"subject": pkg, "sections": sections}


def _dashboard(names: list[str]) -> tuple[dict, list[str], int]:
    """Return (payload, warnings, fetch_failures)."""
    sections: list[dict] = []
    warnings: list[str] = []
    failures = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_pair, n): n for n in names}
        results: dict[str, tuple[dict | None, dict | None, list[str]]] = {}
        for fut in futures:
            n = futures[fut]
            results[n] = fut.result()
    for n in names:
        pypi, stats, warns = results[n]
        warnings.extend(warns)
        if pypi is None and stats is None:
            failures += 1
        sections.append(_section_for_package(n, pypi, stats))
    return {"subject": "packages", "sections": sections}, warnings, failures


def _render_text(payload: dict) -> str:
    lines = [f"# {payload['subject']}"]
    for s in payload["sections"]:
        lines.append("")
        lines.append(f"## {s['title']}  [{s['light']}]")
        for f in s["fields"]:
            lines.append(f"  {f['name']:<12}  {f['value']}")
    return "\n".join(lines)


def _emit(payload: dict, json_mode: bool) -> None:
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(_render_text(payload), json_mode=False)


def cmd_packages_overview(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    pkg = args.pkg
    if pkg is None:
        try:
            names = load_package_names()
        except ConfigError as err:
            raise AfiError(
                code=EXIT_USER_ERROR,
                message=str(err),
                remediation=(
                    "add a [tool.auntiepypi] table to pyproject.toml with a "
                    "non-empty `packages = [...]` list"
                ),
            ) from err
        payload, warnings, failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        if failures == len(names) and len(names) > 0:
            _emit(payload, json_mode)
            return EXIT_ENV_ERROR
        _emit(payload, json_mode)
        return 0

    _validate_name(pkg)
    pypi, stats, warnings = _fetch_pair(pkg)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    payload = _deep_dive(pkg, pypi, stats)
    _emit(payload, json_mode)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "packages",
        help="Manage and report on PyPI packages.",
    )
    sp = p.add_subparsers(dest="packages_verb")
    ov = sp.add_parser(
        "overview",
        help="Roll-up dashboard or per-package deep-dive (informational, not gating).",
    )
    ov.add_argument(
        "pkg",
        nargs="?",
        default=None,
        help="Package name; omit for the dashboard over [tool.auntiepypi].packages.",
    )
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_packages_overview)

    def _packages_no_verb(args: argparse.Namespace) -> int:
        p.print_help()
        return EXIT_USER_ERROR

    p.set_defaults(func=_packages_no_verb)
```

- [ ] **Step 5: Wire into `cli/__init__.py`**

Edit `auntiepypi/cli/__init__.py`. After line 23 (the existing `from auntiepypi.cli._commands import whoami as _whoami_cmd`), add:

```python
from auntiepypi.cli._commands._packages import overview as _packages_overview_cmd
```

After line 53 (the existing `_whoami_cmd.register(sub)`), add:

```python
    _packages_overview_cmd.register(sub)
```

- [ ] **Step 6: Run; confirm pass**

```bash
uv run pytest tests/test_cli_packages.py -q
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add auntiepypi/cli/_commands/_packages/ auntiepypi/cli/__init__.py tests/test_cli_packages.py
git commit -m "feat(cli): auntiepypi packages overview [PKG]"
```

---

## Task 17: Promote top-level `overview` to composite

**Files:**

- Modify: `auntiepypi/cli/_commands/overview.py`
- Modify: `tests/test_overview.py` — section-shape update
- Test: `tests/test_cli_overview_composite.py`

- [ ] **Step 1: Write the failing composite test**

Create `tests/test_cli_overview_composite.py`:

```python
"""Tests for the composite `auntiepypi overview` (packages + servers)."""
from __future__ import annotations

import json

import pytest

from auntiepypi.cli import main


def _good_pypi(name="x"):
    return {
        "info": {
            "name": name, "version": "1.0.0", "license": "MIT",
            "requires_python": ">=3.10",
            "project_urls": {"Homepage": "h", "Source": "s"},
            "description": "y" * 250,
            "classifiers": ["Development Status :: 5 - Production/Stable"],
        },
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2026-04-25T00:00:00Z", "yanked": False}],
            "0.9.0": [{"upload_time_iso_8601": "2026-04-15T00:00:00Z", "yanked": False}],
        },
        "urls": [{"packagetype": "bdist_wheel"}, {"packagetype": "sdist"}],
    }


@pytest.fixture
def composite_env(tmp_path, monkeypatch):
    from auntiepypi._rubric import _sources

    monkeypatch.setattr(_sources, "fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(_sources, "fetch_pypistats", lambda pkg: {"data": {"last_week": 100}})
    (tmp_path / "pyproject.toml").write_text('[tool.auntiepypi]\npackages = ["alpha"]\n')
    monkeypatch.chdir(tmp_path)


def test_no_arg_emits_both_categories(composite_env, capsys):
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"packages", "servers"}


def test_with_pkg_target_delegates_to_packages(composite_env, capsys):
    rc = main(["overview", "alpha", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "alpha"
    titles = {s["title"] for s in payload["sections"]}
    assert "_summary" in titles


def test_with_server_target_keeps_v0_0_1_semantics(composite_env, capsys):
    rc = main(["overview", "devpi", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Single-flavor probe — sections list contains only servers entries.
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"servers"}
    titles = {s["title"] for s in payload["sections"]}
    assert "devpi" in titles


def test_with_unknown_target_zero_target_report(composite_env, capsys):
    rc = main(["overview", "i-am-not-real", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert payload.get("note")
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_cli_overview_composite.py -q
```

Expected: 4 failures (current `overview` has neither categories nor delegation).

- [ ] **Step 3: Replace `cli/_commands/overview.py` with the composite implementation**

Replace the entire file with:

```python
"""``auntiepypi overview`` — composite of packages + servers sections.

v0.0.1 ran the server-flavor probes; v0.1.0 promotes this verb to a
*composite* report:

- No arg → emit a packages section group (rolled-up dashboard from
  ``[tool.auntiepypi].packages``) followed by a servers section group
  (the existing ``_probes/`` flavor probes).
- With arg → resolve in priority: server flavor → existing single-probe
  semantics; configured package → delegate to ``packages overview``;
  otherwise zero-target stderr warning + exit 0.

Each section carries an explicit ``category`` key (``"packages"`` or
``"servers"``) so agents can group by domain.
"""
from __future__ import annotations

import argparse
from typing import Optional

from auntiepypi._packages_config import ConfigError, load_package_names
from auntiepypi._probes import PROBES, probe_status
from auntiepypi.cli._commands._packages.overview import (
    _dashboard,
    _deep_dive,
    _emit,
    _fetch_pair,
)
from auntiepypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "auntiepypi overview"


def _server_section(probe_result: dict) -> dict:
    fields = [
        {"name": "port", "value": str(probe_result.get("port", ""))},
        {"name": "url", "value": probe_result.get("url", "")},
        {"name": "status", "value": probe_result.get("status", "")},
    ]
    if probe_result.get("detail"):
        fields.append({"name": "detail", "value": probe_result["detail"]})
    light_map = {"up": "green", "down": "red", "absent": "unknown"}
    return {
        "category": "servers",
        "title": probe_result.get("name", "?"),
        "light": light_map.get(probe_result.get("status", ""), "unknown"),
        "fields": fields,
    }


def _all_servers_sections() -> list[dict]:
    return [_server_section(probe_status(p)) for p in PROBES]


def _server_target(target: str) -> Optional[dict]:
    for p in PROBES:
        if p.name == target:
            return _server_section(probe_status(p))
    return None


def _try_package_target(target: str) -> Optional[dict]:
    """Return the deep-dive payload if `target` is a configured package."""
    try:
        names = load_package_names()
    except ConfigError:
        return None
    if target not in names:
        return None
    pypi, stats, warnings = _fetch_pair(target)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    return _deep_dive(target, pypi, stats)


def _composite_no_arg(json_mode: bool) -> int:
    sections: list[dict] = []
    # Packages: only when configured; otherwise omit silently and warn.
    try:
        names = load_package_names()
    except ConfigError:
        names = []
        emit_diagnostic(
            "warning: no [tool.auntiepypi].packages configured; "
            "showing servers only"
        )
    if names:
        payload, warnings, _failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        sections.extend(payload["sections"])
    sections.extend(_all_servers_sections())

    payload = {"subject": _SUBJECT, "sections": sections}
    _emit(payload, json_mode)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    target = args.target if args.target else None
    json_mode = bool(getattr(args, "json", False))

    if target is None:
        return _composite_no_arg(json_mode)

    # Priority 1: server flavor.
    server = _server_target(target)
    if server is not None:
        payload = {"subject": _SUBJECT, "sections": [server]}
        _emit(payload, json_mode)
        return 0

    # Priority 2: configured package.
    pkg_payload = _try_package_target(target)
    if pkg_payload is not None:
        # Use the package subject so consumers can route on it.
        _emit(pkg_payload, json_mode)
        return 0

    # Priority 3: zero-target report (preserved v0.0.1 semantics).
    payload = {
        "subject": _SUBJECT,
        "sections": [],
        "target": target,
        "note": (
            f"target {target!r} not recognised; emitting zero-target report "
            "(use `auntiepypi overview` with no arg for the default scan)"
        ),
    }
    emit_diagnostic(f"warning: {payload['note']}")
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(f"# {_SUBJECT}\n\n(no targets scanned)", json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "overview",
        help="Composite report: packages dashboard + local PyPI server probes.",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Optional target: a server flavor (devpi / pypiserver) or a "
            "configured package name. Omit for the full composite."
        ),
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_overview)
```

- [ ] **Step 4: Update existing v0.0.1 overview tests for the new section shape**

Open `tests/test_overview.py` and read its assertions. Update any assertions that touch `section["name"]`, `section["summary"]`, `section["items"]` to the new keys: `section["title"]`, `section["category"]`, `section["light"]`, `section["fields"]`.

The test must still pass without configured packages (since `tmp_path` won't have `[tool.auntiepypi]`). The `_composite_no_arg` path warns and emits servers-only — that's fine.

If existing tests assert on `subject == "auntiepypi overview"`, that still holds.

If they assert on the legacy section keys, update to:

```python
def test_overview_emits_server_sections_with_category():
    # ... existing setup ...
    rc = main(["overview", "--json"])
    payload = json.loads(captured_stdout)
    server_sections = [s for s in payload["sections"] if s["category"] == "servers"]
    assert len(server_sections) == 2  # devpi + pypiserver
    for s in server_sections:
        assert s["light"] in {"green", "red", "unknown"}
        names = {f["name"] for f in s["fields"]}
        assert {"port", "url", "status"} <= names
```

- [ ] **Step 5: Run all overview-related tests**

```bash
uv run pytest tests/test_overview.py tests/test_cli_overview_composite.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/cli/_commands/overview.py tests/test_overview.py tests/test_cli_overview_composite.py
git commit -m "feat(cli): promote auntiepypi overview to packages+servers composite"
```

---

## Task 18: Update explain catalog

**Files:**

- Modify: `auntiepypi/explain/catalog.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_cli.py` (or create `tests/test_explain_catalog.py` if cleaner):

```python
def test_catalog_has_packages_entry():
    from auntiepypi.explain.catalog import ENTRIES

    assert ("packages",) in ENTRIES
    assert ("packages", "overview") in ENTRIES
    assert ("online",) not in ENTRIES


def test_catalog_root_mentions_packages_overview():
    from auntiepypi.explain.catalog import ENTRIES

    root = ENTRIES[("auntiepypi",)]
    assert "auntiepypi packages overview" in root
    assert "online" not in root.lower() or "online release" in root  # roadmap mention OK
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_cli.py -q -k catalog
```

Expected: failures.

- [ ] **Step 3: Edit `auntiepypi/explain/catalog.py`**

Replace `_ROOT` body (lines 12-52) with:

```python
_ROOT = """\
# auntiepypi

auntiepypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## Verbs

- `auntiepypi learn` — structured self-teaching prompt.
- `auntiepypi explain <path>` — markdown docs for any noun/verb.
- `auntiepypi overview [TARGET]` — composite: packages dashboard + local
  server probes. With TARGET, drills into one server flavor or one
  configured package.
- `auntiepypi packages overview [PKG]` — read-only PyPI maturity dashboard
  (no arg) or per-package deep-dive (with arg).
- `auntiepypi doctor [--fix]` — probe + diagnose; `--fix` starts servers.
- `auntiepypi whoami` — auth/env probe; reports configured indexes.

## Planned

- `auntiepypi local serve | upload | mirror` — v0.2.0
- `auntiepypi servers …` — v0.2.0 (formal home for server lifecycle)

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `auntiepypi explain learn`
- `auntiepypi explain explain`
- `auntiepypi explain overview`
- `auntiepypi explain packages`
- `auntiepypi explain packages overview`
- `auntiepypi explain doctor`
- `auntiepypi explain whoami`
- `auntiepypi explain local`
"""
```

Replace `_ONLINE` (lines 165-185) with `_PACKAGES` and a deep entry. Find the block:

```python
_ONLINE = """\
# auntiepypi online (planned, v0.1.0)
...
"""
```

Replace it with:

```python
_PACKAGES = """\
# auntiepypi packages

Read-only verbs against PyPI for the configured set of packages.

The configured set lives in `pyproject.toml`:

    [tool.auntiepypi]
    packages = ["pkg-a", "pkg-b"]

## Verbs

- `auntiepypi packages overview` — dashboard over all configured packages.
- `auntiepypi packages overview <pkg>` — deep-dive over the rubric for one.

Read-only by design. Reports — never gates. Exit code is `0` regardless
of how many packages roll up `red`.
"""

_PACKAGES_OVERVIEW = """\
# auntiepypi packages overview

Roll-up dashboard over the configured package list, or per-package
deep-dive when called with an argument.

## Usage

    auntiepypi packages overview            # dashboard
    auntiepypi packages overview <pkg>      # deep-dive
    auntiepypi packages overview --json
    auntiepypi packages overview <pkg> --json

## Rubric (deep-dive)

Seven dimensions, each scored pass / warn / fail / unknown, rolled up
to a green / yellow / red / unknown traffic light:

- recency — days since last non-yanked release
- cadence — median gap between last 5 releases
- downloads — pypistats `last_week`
- lifecycle — Trove `Development Status` classifier
- distribution — wheel + sdist availability
- metadata — license / requires_python / Homepage / Source / README
- versioning — PEP 440 maturity

## Exit codes

- `0` always (read-only; reds do not change the exit).
- `1` on missing config (no `[tool.auntiepypi].packages`) or invalid name.
- `2` only if every fetch failed.
"""
```

Then update the `ENTRIES` dict (lines 209-219) — remove `("online",)`, replace with `("packages",)` and `("packages", "overview")`:

```python
ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("auntiepypi",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("whoami",): _WHOAMI,
    ("packages",): _PACKAGES,
    ("packages", "overview"): _PACKAGES_OVERVIEW,
    ("local",): _LOCAL,
}
```

Also update `_OVERVIEW` body (lines 88-118) to describe the composite shape:

```python
_OVERVIEW = """\
# auntiepypi overview

Composite report. With no arg: emits a packages dashboard (one section
per configured package) plus the local PyPI server probes (one section
per known flavor). With an arg, drills into one server flavor or one
configured package, in that priority.

Recognised server flavors:

- `devpi` on port `3141` (`/+api`)
- `pypiserver` on port `8080` (`/`)

Read-only — no mutation flags. Use `auntiepypi doctor --fix` to start
servers.

## Usage

    auntiepypi overview
    auntiepypi overview --json
    auntiepypi overview <server-flavor>      # e.g. `devpi`
    auntiepypi overview <configured-pkg>     # e.g. `requests`

## JSON envelope

    {
      "subject": "auntiepypi overview",
      "sections": [
        {"category": "packages", "title": "<pkg>", "light": "green|...", "fields": [...]},
        {"category": "servers",  "title": "<flavor>", "light": "...", "fields": [...]}
      ]
    }

## Exit codes

- `0` always.
"""
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_cli.py -q -k catalog
uv run pytest -n auto -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/explain/catalog.py tests/test_cli.py
git commit -m "feat(explain): packages catalog entries; drop online placeholder"
```

---

## Task 19: Update `learn --json` planned array + text

**Files:**

- Modify: `auntiepypi/cli/_commands/learn.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (next to existing `learn` tests):

```python
def test_learn_json_drops_online_adds_packages():
    import json
    from io import StringIO
    import contextlib

    from auntiepypi.cli import main

    buf = StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    paths = [tuple(c["path"]) for c in payload["commands"]]
    assert ("packages", "overview") in paths
    planned = [tuple(p["path"]) for p in payload["planned"]]
    assert ("online", "status") not in planned
    assert ("online", "release") not in planned
    assert ("local", "serve") in planned  # local stays
```

- [ ] **Step 2: Run; confirm fail**

```bash
uv run pytest tests/test_cli.py -q -k learn_json_drops
```

Expected: assertion failure.

- [ ] **Step 3: Edit `learn.py`**

Update `_TEXT` (lines 24-74) to replace the `Planned (not yet registered)` section. Replace:

```text
Planned (not yet registered)
----------------------------
  auntiepypi online status SIBLING       (v0.1.0)
  auntiepypi online release SIBLING      (v0.1.0)
  auntiepypi local serve | upload | mirror (v0.2.0)
```

with:

```text
Planned (not yet registered)
----------------------------
  auntiepypi local serve | upload | mirror (v0.2.0)
  auntiepypi servers overview              (v0.2.0)
```

Also add `auntiepypi packages overview` to the Commands block (insert after the `auntiepypi overview` block, before `auntiepypi doctor`):

```text
  auntiepypi packages overview [PKG]  Read-only PyPI maturity dashboard or
                                     per-package deep-dive. Informational,
                                     not gating. Supports --json.
```

Update the `_M_ONLINE` constant block. Remove `_M_ONLINE` (no longer referenced) and replace the planned commands list at the bottom of `_as_json_payload`:

```python
_M_LOCAL = "v0.2.0"
_M_SERVERS = "v0.2.0"
```

In `_as_json_payload`, update `commands` to add packages overview:

```python
        "commands": [
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {
                "path": ["overview"],
                "summary": "Composite: packages dashboard + local server probes.",
            },
            {
                "path": ["packages", "overview"],
                "summary": "PyPI maturity dashboard or per-package deep-dive.",
            },
            {
                "path": ["doctor"],
                "summary": ("Probe + diagnose local PyPI servers; with --fix, start them."),
            },
            {
                "path": ["whoami"],
                "summary": "Report configured PyPI / TestPyPI / local index.",
            },
        ],
```

And update `planned`:

```python
        "planned": [
            {"path": ["local", "serve"], "milestone": _M_LOCAL},
            {"path": ["local", "upload"], "milestone": _M_LOCAL},
            {"path": ["local", "mirror"], "milestone": _M_LOCAL},
            {"path": ["servers", "overview"], "milestone": _M_SERVERS},
        ],
```

- [ ] **Step 4: Run; confirm pass**

```bash
uv run pytest tests/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/cli/_commands/learn.py tests/test_cli.py
git commit -m "feat(learn): drop online from planned; add packages overview"
```

---

## Task 20: README, CLAUDE.md, docs/about.md

**Files:**

- Modify: `README.md`
- Modify: `CLAUDE.md`
- Create: `docs/about.md`

- [ ] **Step 1: Read existing README and CLAUDE.md to find the right edit points**

```bash
head -30 README.md
head -50 CLAUDE.md
```

- [ ] **Step 2: Update README.md opening**

Replace the opening paragraph(s) of `README.md` (everything from the first H1 through the existing status line) with:

````markdown
# auntiepypi

> auntiepypi is both a CLI and an agent that maintains, uses, and serves
> the CLI for managing PyPI packages. It supports remote (pypi.org)
> today and local (mesh-hosted) indexes in future milestones. It
> overviews packages — informational, not gating.

**Status:** v0.1.0 — read-only PyPI maturity dashboard + composite
overview shipped. `local` (in-mesh PyPI server) and `servers` (lifecycle
management) are planned for v0.2.0.

## Quick start

```bash
uv tool install auntiepypi
auntiepypi --version
auntiepypi packages overview --json | jq
```

For the dashboard to show anything, add a configured package list to
your repo's `pyproject.toml`:

```toml
[tool.auntiepypi]
packages = ["requests", "pip"]
```

See [`docs/about.md`](docs/about.md) for the longer non-technical explainer.
````

Preserve any "Development" / "Contributing" sections from the original README below this block.

- [ ] **Step 3: Update CLAUDE.md status line + active surface**

Edit `CLAUDE.md`. Replace the `## Status: v0.0.1 baseline landed` block with:

```markdown
## Status: v0.1.0 — packages overview landed

The `packages` noun shipped: `auntiepypi packages overview [PKG]` is the
read-only PyPI maturity dashboard / deep-dive. The top-level
`auntiepypi overview` is now a composite of packages + servers sections.
Read-only, stdlib-only HTTP, informational (not gating).

This file describes the repository **as it exists on disk today**. When
you edit, keep claims grounded in checked-in reality; the moment a
section drifts ahead of reality, mark it `(planned)` or move it under
`## Roadmap`.

Remote: `https://github.com/agentculture/auntiepypi`.

See `docs/about.md` for the non-technical explainer.
```

In the existing CLI shape section, replace the `online` and `local` block descriptions with the v0.1.0 reality:

- Update the existing `auntiepypi overview [TARGET]` description to say "composite of packages + local server probes; with TARGET drills into a server flavor or configured package".
- Add `auntiepypi packages overview [PKG] [--json]` to the active list.
- Remove `online` from active; keep `local` in Roadmap.

In the Roadmap section: mark v0.1.0 as **shipped (read-only: dashboard + maturity rubric)**; release-orchestration explicitly deferred.

- [ ] **Step 4: Create `docs/about.md`**

```markdown
# About auntiepypi

auntiepypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## What it is

A small command-line tool plus a stable plumbing layer that an agent
inside the AgentCulture mesh can call. The tool reads. It reports. It
does not block builds, fail CI on package-quality grounds, or insist on
its own opinions of "good enough".

## What it does today (v0.1.0)

Two things, both read-only:

1. **Dashboard.** Run `auntiepypi packages overview` and you get a
   one-row-per-package summary of every package listed in your repo's
   `[tool.auntiepypi].packages` block. Each row shows the current
   version, the index it lives on (currently always pypi.org), how long
   ago it was released, and last-week download count. A traffic light
   sums up seven maturity signals.

2. **Deep-dive.** Run `auntiepypi packages overview <pkg>` for any
   package on PyPI — yours or anyone else's — and you get the seven
   signals broken out: recency of releases, cadence between them,
   download volume, Trove lifecycle classifier, distribution
   (wheel/sdist), metadata completeness, and PEP 440 versioning
   maturity.

The same machinery feeds the top-level `auntiepypi overview`, which adds
a second category — local PyPI server probes — for a one-shot picture
of "what's going on with my packages and my local servers right now".

## What "informational, not gating" means

The tool tells you what it sees. It does not refuse to exit with code 0
just because a dependency is stale or a download count is low. There is
no `--strict`, no `--fail-on=red`, no quietly-blocking-merge mode. If
you want to gate something on the rubric output, that's a separate
verb — and a separate noun — and a separate design conversation.

This is a deliberate choice. Tools that gate on opinion-shaped metrics
get worked around. Tools that report on opinion-shaped metrics stay
useful.

## Where it's headed

- v0.2.0 — local in-mesh PyPI index. `auntiepypi local serve` /
  `upload` / `mirror`. The dashboard's `index` column starts showing
  local mesh URLs for packages you host in-house.
- v0.2.0 — `auntiepypi servers …` for lifecycle management of those
  local servers (start/stop/list/diagnose).
- Later — release orchestration (trigger sibling `publish.yml`
  workflows); periodic last-update sweeps; whatever the mesh needs
  next.

Nothing here gets shipped without a brainstorm pass and a written spec
under `docs/superpowers/specs/`. The roadmap is a sketch, not a plan.
```

- [ ] **Step 5: Run docs lint**

```bash
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.afi"
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md docs/about.md
git commit -m "docs: statement of purpose, v0.1.0 status, docs/about.md"
```

---

## Task 21: Configure example `[tool.auntiepypi].packages`

**Files:**

- Modify: `pyproject.toml`

- [ ] **Step 1: Add the configuration block**

Append to `pyproject.toml` (after `[tool.pytest.ini_options]`):

```toml
[tool.auntiepypi]
# Packages this repo cares about for `auntiepypi packages overview`.
# These are AgentCulture siblings published to pypi.org. Add or remove as
# the mesh evolves.
packages = [
    "auntiepypi",
    "afi-cli",
    "shushu",
    "ghafi",
    "steward",
    "cfafi",
]
```

- [ ] **Step 2: Smoke-test against the live API (do NOT commit if any sibling is unpublished and would error the dashboard non-trivially)**

```bash
uv run auntiepypi packages overview --json | head -50
```

Expected: a JSON payload with `subject: "packages"` and one section per configured name. Some siblings may not yet be on PyPI — those will show `light: unknown` with a stderr warning. That's fine.

- [ ] **Step 3: Run full test suite**

```bash
uv run pytest -n auto -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "config: [tool.auntiepypi].packages with sibling list"
```

---

## Task 22: Live-network test suite (`@pytest.mark.live`)

**Files:**

- Create: `tests/test_live_packages.py`

- [ ] **Step 1: Write the live tests with skip-on-network fixture**

Create `tests/test_live_packages.py`:

```python
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
def test_packages_overview_against_real_api(monkeypatch, tmp_path, capsys):
    """End-to-end: run the CLI verb against live APIs."""
    import json

    from auntiepypi.cli import main

    (tmp_path / "pyproject.toml").write_text(
        '[tool.auntiepypi]\npackages = ["requests"]\n'
    )
    monkeypatch.chdir(tmp_path)

    try:
        rc = main(["packages", "overview", "--json"])
    except FetchError as err:  # pragma: no cover
        pytest.skip(f"upstream {err.reason}")

    if rc == 2:
        pytest.skip("all upstreams unreachable")
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "packages"
    assert len(payload["sections"]) == 1
    section = payload["sections"][0]
    assert section["title"] == "requests"
    assert section["light"] in {"green", "yellow", "red", "unknown"}
```

- [ ] **Step 2: Confirm default runs still skip these**

```bash
uv run pytest -n auto -q
```

Expected: same pass count as Task 21 (live tests not collected).

- [ ] **Step 3: Run the live suite explicitly**

```bash
uv run pytest -m live -v
```

Expected: ≤ 7 tests, all pass or skip (skips are OK if pypi.org is having a moment). Confirm none turn the run red unexpectedly.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_packages.py
git commit -m "test: live-network suite (opt-in via -m live)"
```

---

## Task 23: CI — add live job to `tests.yml`

**Files:**

- Modify: `.github/workflows/tests.yml`

- [ ] **Step 1: Append the live job**

Edit `.github/workflows/tests.yml`. Append after the existing `version-check:` job (after line 96):

```yaml
  live:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    # Soft on PR (continue-on-error), blocking on push to main.
    continue-on-error: ${{ github.event_name == 'pull_request' }}
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - name: Live network tests
        run: uv run pytest -m live -v
```

- [ ] **Step 2: Lint the YAML locally**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/tests.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: add live test job (soft on PR, blocking on main)"
```

---

## Task 24: CI — pre/post-deploy smoke in `publish.yml`

**Files:**

- Modify: `.github/workflows/publish.yml`

- [ ] **Step 1: Add a `smoke-source` job that runs after `test` and before publishes**

Edit `.github/workflows/publish.yml`. After the existing `test:` job (around line 25) and before `test-publish:`, insert:

```yaml
  smoke-source:
    needs: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - run: uv sync
      - name: Build wheel
        run: uv build
      - name: Install built wheel into clean venv
        run: |
          python -m venv /tmp/smoke
          /tmp/smoke/bin/pip install --quiet dist/*.whl
      - name: Smoke — version + packages overview against pypi.org
        run: |
          /tmp/smoke/bin/auntiepypi --version
          /tmp/smoke/bin/auntiepypi packages overview requests --json | python -m json.tool
```

- [ ] **Step 2: Add `smoke-source` as a dep of `test-publish` and `publish`**

In the existing `test-publish:` block, change `needs: test` to `needs: [test, smoke-source]`.
In the existing `publish:` block, change `needs: test` to `needs: [test, smoke-source]`.

- [ ] **Step 3: Add a `smoke-installed` post-publish job**

Append after the existing `publish:` block:

```yaml
  smoke-installed:
    if: github.event_name == 'push'
    needs: publish
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: astral-sh/setup-uv@38f3f104447c67c051c4a08e39b64a148898af3a # v4
      - run: uv python install 3.12
      - name: Wait for new version on pypi.org
        run: |
          VERSION=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          echo "Waiting for auntiepypi==$VERSION on pypi.org…"
          for i in $(seq 1 18); do
            if curl -sf "https://pypi.org/pypi/auntiepypi/$VERSION/json" -o /dev/null; then
              echo "Available."
              exit 0
            fi
            sleep 5
          done
          echo "::error::Timed out waiting for auntiepypi==$VERSION on pypi.org"
          exit 1
      - name: Install from pypi.org and smoke
        run: |
          VERSION=$(uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          rm -rf /tmp/postsmoke
          python -m venv /tmp/postsmoke
          /tmp/postsmoke/bin/pip install --quiet "auntiepypi==$VERSION"
          /tmp/postsmoke/bin/auntiepypi --version
          /tmp/postsmoke/bin/auntiepypi packages overview requests --json | python -m json.tool
```

- [ ] **Step 4: Lint**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/publish.yml'))" && echo OK
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/publish.yml
git commit -m "ci: pre/post-deploy smoke jobs in publish.yml"
```

---

## Task 25: End-to-end verification + push

**Files:** none (validation only)

- [ ] **Step 1: Full local verification**

```bash
uv sync
uv run pytest -n auto --cov=auntiepypi --cov-report=term -q
uv run black --check auntiepypi tests
uv run isort --check-only auntiepypi tests
uv run flake8 auntiepypi tests
uv run pylint --errors-only auntiepypi
uv run bandit -c pyproject.toml -r auntiepypi
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.afi"
bash .claude/skills/pr-review/scripts/portability-lint.sh
```

Expected: all pass; coverage ≥ 95%.

- [ ] **Step 2: CLI smoke (mirrors the spec's Verification block)**

```bash
uv run auntiepypi --version
uv run auntiepypi packages overview --json | head -30
uv run auntiepypi packages overview requests --json | head -50
uv run auntiepypi overview --json | head -30
uv run auntiepypi explain packages
uv run auntiepypi explain packages overview
uv run auntiepypi learn --json | head -40
```

Expected: each command exits 0 with non-empty output. The `packages overview` calls hit the live network; if pypi.org or pypistats.org are unreachable, expect `light: unknown` and warnings to stderr — not a non-zero exit.

- [ ] **Step 3: steward doctor (if available)**

```bash
(cd ../steward && uv run steward doctor --scope self ../auntiepypi) || true
```

Expected: clean output (or warnings unrelated to this PR).

- [ ] **Step 4: Push the branch**

```bash
git push -u origin v0.1.0-packages-overview
```

- [ ] **Step 5: Open the PR via the `pr-review` skill**

Invoke the auntiepypi `pr-review` skill or run `gh pr create` directly:

```bash
gh pr create --title "v0.1.0: packages overview (informational, not gating)" --body "$(cat <<'EOF'
## Summary

- Ships the `packages` noun: `auntiepypi packages overview [PKG]` — read-only PyPI maturity dashboard / per-package deep-dive.
- Promotes top-level `auntiepypi overview` to a composite of `packages` + `servers` sections; section JSON shape standardises on `{category, title, light, fields}`.
- Adds `_rubric/` plugin point with seven dimensions (recency, cadence, downloads, lifecycle, distribution, metadata, versioning) — parallel to the existing `_probes/` pattern.
- Tightens the test posture: 95% coverage gate (was 60%); opt-in `@pytest.mark.live` suite for real pypi.org / pypistats.org calls; pre/post-deploy smoke jobs in `publish.yml`.
- Drops the `online` placeholder from the catalog and `learn --json`.
- Adds `docs/about.md` — non-technical explainer.

Spec: `docs/superpowers/specs/2026-04-29-auntiepypi-packages-overview-design.md`.

"Not gating" is a design constraint: exit code stays 0 regardless of how many packages roll up red, no `--strict`, no `--fail-on=red`.

## Test plan

- [x] `uv run pytest -n auto -q` — full hermetic suite green
- [x] `uv run pytest -m live -v` — live suite green or skipped on upstream hiccups
- [x] coverage ≥ 95%
- [x] lint suite clean (black / isort / flake8 / pylint / bandit / markdownlint / portability)
- [x] `uv run auntiepypi packages overview --json` round-trips through `jq`
- [x] `uv run auntiepypi overview --json` shows mixed `category` sections
- [x] `uv run auntiepypi explain packages overview` returns non-empty markdown
- [x] `uv run auntiepypi learn --json | jq .planned` no longer mentions `online`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist

**Spec coverage:**

- [x] `packages overview` no-arg dashboard — Tasks 4, 16
- [x] `packages overview <pkg>` deep-dive — Task 16
- [x] Composite top-level `overview` — Task 17
- [x] All seven rubric dimensions — Tasks 8-14
- [x] `_rubric/` plugin point — Tasks 5, 15
- [x] Stdlib HTTP + concurrency — Tasks 6, 16
- [x] PyPI 404 → unknown, env error → exit 2 — Task 16
- [x] Section shape with `category` key — Tasks 16, 17
- [x] `index` field always `"pypi.org"` in v0.1.0 — Task 16
- [x] Static config in `[tool.auntiepypi].packages` — Tasks 4, 21
- [x] 95% coverage gate — Task 2
- [x] `@pytest.mark.live` suite + skip-on-error — Tasks 3, 22
- [x] CI live job (soft PR / blocking main) — Task 23
- [x] Pre/post-deploy smoke in `publish.yml` — Task 24
- [x] Catalog updates (`packages` in, `online` out) — Task 18
- [x] `learn --json` planned array updated — Task 19
- [x] Statement of purpose in README + catalog root — Tasks 18, 20
- [x] `docs/about.md` non-technical explainer — Task 20
- [x] Version bump + CHANGELOG entry — Task 1
- [x] CLAUDE.md status + roadmap update — Task 20

**Type consistency check:**

- `Score` enum values (pass/warn/fail/unknown) — used identically across all dimension tests and the runtime.
- `DimensionResult(score, value, reason)` — three positional fields, used identically across all dimensions.
- `Dimension(name, description, evaluate)` — three fields; `evaluate(pypi: dict | None, stats: dict | None) -> DimensionResult` is the canonical signature.
- `FetchError(reason, status=None)` — used in `_fetch.py`, `_sources.py`, `_packages/overview.py`, live tests.
- `roll_up(results) -> str` returns one of `"green"`/`"yellow"`/`"red"`/`"unknown"` — same vocabulary used in section `light` keys throughout.
- Section JSON shape `{category, title, light, fields: [{name, value}]}` — identical in both packages and servers categories.
- `ConfigError` for config issues; `AfiError` for CLI exit codes — never mixed.

**Placeholder scan:** no "TBD" / "TODO" / "implement later" appears in this plan.
