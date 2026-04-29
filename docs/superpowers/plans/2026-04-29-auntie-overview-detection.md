# auntie overview detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand `auntie overview`'s servers section to surface declared servers + default port scan + opt-in `/proc` scan, via a parallel `_detect/` module that leaves `_probes/` and `doctor` untouched.

**Architecture:** New `_detect/` plugin point with three detector modules (`_declared`, `_port`, `_proc`) + a small runtime that merges results (augment + suppress-absent-when-declared). The CLI composite `overview.py` swaps its server-section call site from `_probes/.probe_status` to `_detect/.detect_all`. The CLI binary registers an `auntie` alias alongside the existing `auntiepypi`.

**Tech Stack:** Python 3.12+, stdlib only (`socket`, `urllib.request`, `tomllib`, `concurrent.futures`, `http.server` for tests), pytest+xdist+cov, hatchling.

**Spec drift to note:** The design doc claims `[[tool.auntiepypi.servers]]` and `[tool.auntiepypi.servers]` (table form) coexist — they do not in TOML. This plan puts the singleton `scan_processes` flag on the parent `[tool.auntiepypi]` table instead. Same user surface; correct TOML.

---

## File Structure

**New files:**

- `auntiepypi/_detect/__init__.py` — re-exports `DETECTORS`, `Detection`, `detect_all`, `ServersConfig`, `load_servers`
- `auntiepypi/_detect/_detection.py` — frozen `Detection` dataclass + `to_section()`
- `auntiepypi/_detect/_config.py` — `ServerSpec`, `ServersConfig`, `load_servers()`, validation
- `auntiepypi/_detect/_http.py` — TCP-then-HTTP probe primitive shared by `_declared` + `_port`
- `auntiepypi/_detect/_declared.py` — detect by probing each declared `ServerSpec`
- `auntiepypi/_detect/_port.py` — detect by scanning `DEFAULT_PORTS` and fingerprinting flavor
- `auntiepypi/_detect/_proc.py` — Linux `/proc` scan (opt-in, no-op elsewhere)
- `auntiepypi/_detect/_runtime.py` — `detect_all()` merge logic
- `tests/test_detect_config.py`
- `tests/test_detect_declared.py`
- `tests/test_detect_port.py`
- `tests/test_detect_proc.py`
- `tests/test_detect_runtime.py`
- `docs/deploy/README.md`
- `docs/deploy/pypi-server.service`
- `docs/deploy/devpi.service`

**Modified files:**

- `auntiepypi/cli/_commands/overview.py` — composite uses `_detect/`; new `--proc` flag; bare-flavor alias preserved; `<flavor>:<port>` auto-name resolution
- `auntiepypi/explain/catalog.py` — delete `("local",)`; refresh `("overview",)`; refresh root entry
- `auntiepypi/cli/_commands/learn.py` — delete `_M_LOCAL`/`_M_SERVERS` + their `planned[]` entries; refresh `overview` summary; planned[] becomes `[]`
- `pyproject.toml` — add `auntie = "auntiepypi.cli:main"` script; bump version
- `CHANGELOG.md` — add new entry summarising the detection work
- `README.md` — update example to `auntie overview` form
- `CLAUDE.md` — drop `local` and `servers` from Roadmap; refresh v0.3.0 entry; switch CLI examples to `auntie`
- `docs/about.md` — drop `local` noun mentions; add detect-only paragraph
- `tests/test_cli_overview_composite.py` — update for `_detect/` integration; new tests for `--proc`, name-based drill-down, declared-server visibility

---

## Task 1: `Detection` dataclass

**Files:**

- Create: `auntiepypi/_detect/__init__.py`
- Create: `auntiepypi/_detect/_detection.py`
- Test: `tests/test_detect_runtime.py` (will start with one test for `Detection.to_section`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect_runtime.py`:

```python
"""Tests for _detect runtime: Detection dataclass and merge logic."""

from __future__ import annotations

from auntiepypi._detect._detection import Detection


def test_to_section_minimal_fields() -> None:
    d = Detection(
        name="main",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="up",
        source="declared",
    )
    section = d.to_section()
    assert section["category"] == "servers"
    assert section["title"] == "main"
    assert section["light"] == "green"
    field_names = {f["name"] for f in section["fields"]}
    assert {"flavor", "host", "port", "url", "status", "source"} <= field_names
    # No optional fields when none populated
    assert "pid" not in field_names
    assert "managed_by" not in field_names


def test_to_section_includes_optional_fields_when_populated() -> None:
    d = Detection(
        name="main",
        flavor="pypiserver",
        host="127.0.0.1",
        port=8080,
        url="http://127.0.0.1:8080/",
        status="down",
        source="declared",
        pid=1234,
        cmdline="pypi-server run -p 8080",
        detail="http 503",
        managed_by="systemd-user",
        unit="pypi.service",
        command=("pypi-server", "run", "-p", "8080"),
    )
    section = d.to_section()
    field_map = {f["name"]: f["value"] for f in section["fields"]}
    assert field_map["pid"] == "1234"
    assert field_map["detail"] == "http 503"
    assert field_map["managed_by"] == "systemd-user"
    assert field_map["unit"] == "pypi.service"
    assert field_map["command"] == "pypi-server run -p 8080"
    assert section["light"] == "red"


def test_light_mapping_for_absent() -> None:
    d = Detection(
        name="x", flavor="unknown", host="127.0.0.1", port=99,
        url="http://127.0.0.1:99/", status="absent", source="port",
    )
    assert d.to_section()["light"] == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_detect_runtime.py -v
```

Expected: ImportError / ModuleNotFoundError on `auntiepypi._detect`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/__init__.py`:

```python
"""auntiepypi detection layer.

Parallels ``_probes/`` but produces a richer, declaration-driven inventory
of running PyPI servers. ``_probes/`` is the *raise* path (used by
``doctor --fix``); ``_detect/`` is the *display* path (used by
``auntie overview``'s servers section).

Public surface:

* :class:`Detection` — frozen dataclass; one running/declared server.
* :func:`detect_all` — runs every detector, merges results.
* :class:`ServerSpec` / :class:`ServersConfig` / :func:`load_servers` —
  TOML loader for ``[[tool.auntiepypi.servers]]``.
* :data:`DETECTORS` — tuple of detector modules; runtime iterates this.
"""

from __future__ import annotations

from auntiepypi._detect._detection import Detection

__all__ = ["Detection"]
```

Create `auntiepypi/_detect/_detection.py`:

```python
"""Frozen :class:`Detection` dataclass + JSON-section renderer.

Each detector produces a list of these. The CLI renders them via
:meth:`Detection.to_section`.
"""

from __future__ import annotations

from dataclasses import dataclass

_LIGHT_MAP: dict[str, str] = {"up": "green", "down": "red", "absent": "unknown"}


@dataclass(frozen=True)
class Detection:
    """One PyPI server visible to the local box.

    ``status``: ``"up"`` (TCP+HTTP healthy), ``"down"`` (TCP open, HTTP
    unhealthy), ``"absent"`` (nothing listening).

    ``source``: ``"declared"`` (came from ``[[tool.auntiepypi.servers]]``),
    ``"port"`` (default port scan), ``"proc"`` (``--proc`` ``/proc`` scan).
    """

    name: str
    flavor: str  # "pypiserver" | "devpi" | "unknown"
    host: str
    port: int
    url: str
    status: str  # "up" | "down" | "absent"
    source: str  # "declared" | "port" | "proc"
    pid: int | None = None
    cmdline: str | None = None
    detail: str | None = None
    # Reserved declaration metadata (echoed verbatim; v0.2.0 does not act on it).
    managed_by: str | None = None
    unit: str | None = None
    dockerfile: str | None = None
    compose: str | None = None
    service: str | None = None
    command: tuple[str, ...] | None = None

    def to_section(self) -> dict:
        """Render as ``{category, title, light, fields}`` for the JSON envelope."""
        light = _LIGHT_MAP.get(self.status, "unknown")
        fields: list[dict] = [
            {"name": "flavor", "value": self.flavor},
            {"name": "host", "value": self.host},
            {"name": "port", "value": str(self.port)},
            {"name": "url", "value": self.url},
            {"name": "status", "value": self.status},
            {"name": "source", "value": self.source},
        ]
        optional: list[tuple[str, object]] = [
            ("pid", self.pid),
            ("cmdline", self.cmdline),
            ("detail", self.detail),
            ("managed_by", self.managed_by),
            ("unit", self.unit),
            ("dockerfile", self.dockerfile),
            ("compose", self.compose),
            ("service", self.service),
            ("command", self.command),
        ]
        for opt_name, opt_val in optional:
            if opt_val is None:
                continue
            value = " ".join(opt_val) if isinstance(opt_val, tuple) else str(opt_val)
            fields.append({"name": opt_name, "value": value})
        return {
            "category": "servers",
            "title": self.name,
            "light": light,
            "fields": fields,
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_detect_runtime.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_detect/__init__.py auntiepypi/_detect/_detection.py tests/test_detect_runtime.py
git commit -m "$(cat <<'EOF'
detect: Detection dataclass + section renderer

Frozen dataclass for one PyPI server visible to the local box. Renders
to the {category, title, light, fields} envelope shape v0.1.0
established. Optional fields are elided when null so consumers don't
drown in nulls.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: TOML config loader (`ServerSpec`, `ServersConfig`, `load_servers`)

**Files:**

- Create: `auntiepypi/_detect/_config.py`
- Test: `tests/test_detect_config.py`
- Modify: `auntiepypi/_detect/__init__.py` (re-export)

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect_config.py`:

```python
"""Tests for [[tool.auntiepypi.servers]] config loading."""

from __future__ import annotations

import pytest

from auntiepypi._detect._config import (
    ServerConfigError,
    ServerSpec,
    ServersConfig,
    load_servers,
)


def _write(tmp_path, body: str) -> None:
    (tmp_path / "pyproject.toml").write_text(body)


def test_no_pyproject_returns_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg == ServersConfig(specs=(), scan_processes=False)


def test_pyproject_without_servers_key_returns_empty(tmp_path, monkeypatch) -> None:
    _write(tmp_path, '[tool.auntiepypi]\npackages = ["x"]\n')
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.specs == ()
    assert cfg.scan_processes is False


def test_array_of_tables_parsed(tmp_path, monkeypatch) -> None:
    _write(tmp_path, """\
[tool.auntiepypi]
packages = ["x"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080

[[tool.auntiepypi.servers]]
name = "dev"
flavor = "devpi"
host = "127.0.0.1"
port = 3141
managed_by = "systemd-user"
unit = "devpi.service"
""")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert len(cfg.specs) == 2
    assert cfg.specs[0] == ServerSpec(
        name="main", flavor="pypiserver", host="127.0.0.1", port=8080,
    )
    assert cfg.specs[1].name == "dev"
    assert cfg.specs[1].managed_by == "systemd-user"
    assert cfg.specs[1].unit == "devpi.service"
    assert cfg.scan_processes is False


def test_scan_processes_scalar(tmp_path, monkeypatch) -> None:
    _write(tmp_path, """\
[tool.auntiepypi]
packages = ["x"]
scan_processes = true
""")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.scan_processes is True


def test_command_normalised_to_tuple(tmp_path, monkeypatch) -> None:
    _write(tmp_path, """\
[tool.auntiepypi]
packages = ["x"]

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
command = ["pypi-server", "run", "-p", "8080"]
""")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cfg = load_servers()
    assert cfg.specs[0].command == ("pypi-server", "run", "-p", "8080")


@pytest.mark.parametrize("body, msg", [
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
flavor = "pypiserver"
port = 8080
""", "missing 'name'"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
port = 8080
""", "missing 'flavor'"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "wat"
port = 8080
""", "invalid 'flavor'"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
""", "missing 'port'"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 0
""", "out of range"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 8080
[[tool.auntiepypi.servers]]
name = "a"
flavor = "devpi"
port = 3141
""", "duplicate name"),
    ("""\
[tool.auntiepypi]
packages = ["x"]
[[tool.auntiepypi.servers]]
name = "a"
flavor = "pypiserver"
port = 8080
managed_by = "kubernetes"
""", "invalid 'managed_by'"),
])
def test_validation_errors(tmp_path, monkeypatch, body, msg) -> None:
    _write(tmp_path, body)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ServerConfigError) as excinfo:
        load_servers()
    assert msg in str(excinfo.value)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_detect_config.py -v
```

Expected: ImportError on `auntiepypi._detect._config`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_config.py`:

```python
"""Read ``[[tool.auntiepypi.servers]]`` from the nearest ``pyproject.toml``.

Re-uses :func:`auntiepypi._packages_config.find_pyproject` to locate the
config file (same walk-up-to-$HOME semantics as ``packages overview``).

Soft cases:

* No ``pyproject.toml`` found → :class:`ServersConfig` with no specs and
  ``scan_processes=False``. *Not an error* — the default-port scan still
  runs.
* ``pyproject.toml`` exists but no ``[tool.auntiepypi.servers]`` array
  and no ``[tool.auntiepypi].scan_processes`` key → same.

Hard cases (raise :class:`ServerConfigError`):

* Missing ``name``/``flavor``/``port``.
* ``port`` outside ``1..65535``.
* ``flavor`` not in the closed set.
* ``managed_by`` not in the closed set (when present).
* Duplicate ``name`` within the array.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from auntiepypi._packages_config import find_pyproject

_VALID_FLAVORS = frozenset({"pypiserver", "devpi", "unknown"})
_VALID_MANAGED_BY = frozenset(
    {"systemd-user", "docker", "compose", "command", "manual"}
)


class ServerConfigError(Exception):
    """Malformed ``[[tool.auntiepypi.servers]]`` table."""


@dataclass(frozen=True)
class ServerSpec:
    """One declared server. Minimal fields required; rest reserved for v0.3.0."""

    name: str
    flavor: str
    host: str
    port: int
    managed_by: str | None = None
    unit: str | None = None
    dockerfile: str | None = None
    compose: str | None = None
    service: str | None = None
    command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ServersConfig:
    """Full detection-related configuration."""

    specs: tuple[ServerSpec, ...] = ()
    scan_processes: bool = False


def _parse_spec(entry: object, idx: int) -> ServerSpec:
    if not isinstance(entry, dict):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] is not a table"
        )
    name = entry.get("name")
    flavor = entry.get("flavor")
    if not isinstance(name, str) or not name:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}]: missing 'name' (must be a non-empty string)"
        )
    if not isinstance(flavor, str):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: missing 'flavor'"
        )
    if flavor not in _VALID_FLAVORS:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: invalid 'flavor': "
            f"{flavor!r} (valid: {sorted(_VALID_FLAVORS)})"
        )
    if "port" not in entry:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: missing 'port'"
        )
    port = entry["port"]
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'port' out of range "
            f"(got {port!r}; expected int 1..65535)"
        )
    host = entry.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'host' must be a non-empty string"
        )
    managed_by = entry.get("managed_by")
    if managed_by is not None:
        if managed_by not in _VALID_MANAGED_BY:
            raise ServerConfigError(
                f"[[tool.auntiepypi.servers]][{idx}] {name!r}: invalid 'managed_by': "
                f"{managed_by!r} (valid: {sorted(_VALID_MANAGED_BY)})"
            )
    command = entry.get("command")
    if command is not None:
        if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
            raise ServerConfigError(
                f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'command' must be a list of strings"
            )
        command = tuple(command)
    return ServerSpec(
        name=name,
        flavor=flavor,
        host=host,
        port=port,
        managed_by=managed_by,
        unit=_str_or_none(entry, "unit", name, idx),
        dockerfile=_str_or_none(entry, "dockerfile", name, idx),
        compose=_str_or_none(entry, "compose", name, idx),
        service=_str_or_none(entry, "service", name, idx),
        command=command,
    )


def _str_or_none(entry: dict, key: str, name: str, idx: int) -> str | None:
    val = entry.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: {key!r} must be a string"
        )
    return val


def _validate_unique_names(specs: tuple[ServerSpec, ...]) -> None:
    seen: set[str] = set()
    for s in specs:
        if s.name in seen:
            raise ServerConfigError(
                f"[[tool.auntiepypi.servers]]: duplicate name {s.name!r}"
            )
        seen.add(s.name)


def load_servers(start: Path | None = None) -> ServersConfig:
    """Read declaration array + scalar settings from the nearest pyproject.toml."""
    found = find_pyproject(start)
    if found is None:
        return ServersConfig()
    try:
        with found.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ServerConfigError(f"cannot parse {found}: {err}") from err
    auntie_table = data.get("tool", {}).get("auntiepypi", {})
    if not isinstance(auntie_table, dict):
        return ServersConfig()
    raw_specs = auntie_table.get("servers", [])
    scan_processes = bool(auntie_table.get("scan_processes", False))
    if not isinstance(raw_specs, list):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]] must be an array of tables, got "
            f"{type(raw_specs).__name__}"
        )
    specs = tuple(_parse_spec(entry, idx) for idx, entry in enumerate(raw_specs))
    _validate_unique_names(specs)
    return ServersConfig(specs=specs, scan_processes=scan_processes)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_detect_config.py -v
```

Expected: All parametrised + non-parametrised cases pass (~12 tests).

- [ ] **Step 5: Re-export from `__init__.py`**

Edit `auntiepypi/_detect/__init__.py`:

```python
"""auntiepypi detection layer.

(docstring as before)
"""

from __future__ import annotations

from auntiepypi._detect._config import (
    ServerConfigError,
    ServerSpec,
    ServersConfig,
    load_servers,
)
from auntiepypi._detect._detection import Detection

__all__ = [
    "Detection",
    "ServerConfigError",
    "ServerSpec",
    "ServersConfig",
    "load_servers",
]
```

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/_detect/_config.py auntiepypi/_detect/__init__.py tests/test_detect_config.py
git commit -m "$(cat <<'EOF'
detect: TOML loader for [[tool.auntiepypi.servers]]

ServerSpec / ServersConfig dataclasses + load_servers(). Re-uses
find_pyproject() walk-up-to-$HOME semantics. Soft fallthrough when no
config exists; hard errors on malformed declarations (missing required
fields, out-of-range port, unknown flavor/managed_by, duplicate name).
scan_processes lives on the parent [tool.auntiepypi] table because
[[tool.x.servers]] and [tool.x.servers] cannot coexist in TOML.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: HTTP probe primitive (`_http.probe_endpoint`)

**Files:**

- Create: `auntiepypi/_detect/_http.py`
- Test: extend `tests/test_detect_port.py` (created here)

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect_port.py`:

```python
"""Tests for the HTTP probe primitive shared by _declared and _port."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest

from auntiepypi._detect._http import ProbeOutcome, probe_endpoint


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_server(handler_factory) -> tuple[HTTPServer, str, int]:
    server = HTTPServer(("127.0.0.1", 0), handler_factory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "127.0.0.1", server.server_address[1]


@pytest.fixture
def http_server() -> Iterator:
    servers: list[HTTPServer] = []

    def start(handler_factory):
        server, host, port = _make_server(handler_factory)
        servers.append(server)
        return host, port

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()


def _silent(handler_cls):
    handler_cls.log_message = lambda *a, **kw: None
    return handler_cls


def test_probe_absent_when_nothing_listens() -> None:
    out = probe_endpoint("127.0.0.1", _free_port(), timeout=0.5)
    assert out.tcp_open is False
    assert out.http_status is None
    assert out.body is None


def test_probe_up_when_server_returns_200(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<a href='foo/'>foo</a>")
    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0, path="/")
    assert out.tcp_open is True
    assert out.http_status == 200
    assert b"<a href" in out.body


def test_probe_5xx_returns_status(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.end_headers()
    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0)
    assert out.tcp_open is True
    assert out.http_status == 503


def test_probe_outcome_url_field(http_server) -> None:
    """ProbeOutcome carries the URL it probed for caller convenience."""
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"")
    host, port = http_server(H)
    out = probe_endpoint(host, port, timeout=2.0, path="/foo")
    assert out.url == f"http://{host}:{port}/foo"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_detect_port.py -v
```

Expected: ImportError on `auntiepypi._detect._http`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_http.py`:

```python
"""TCP-then-HTTP probe primitive shared by ``_declared`` and ``_port``.

Two-stage by design (mirrors ``_probes/_runtime.probe_status``): TCP
first to distinguish "nothing listening" from "HTTP misbehaving"; then
HTTP GET with a small body read for flavor fingerprinting.

Stdlib only. No retries. Caller-supplied timeout enforced on both stages.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

_MAX_BODY_BYTES = 4096
_USER_AGENT = "auntie-detect/0"  # version stamped in via Detection later if needed


@dataclass(frozen=True)
class ProbeOutcome:
    """Result of one TCP+HTTP probe."""

    url: str
    tcp_open: bool
    http_status: int | None  # None when TCP closed
    body: bytes | None       # first ~4 KiB of response body; None on error/timeout
    error: str | None        # populated on connection error or HTTP timeout


def _tcp_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_endpoint(
    host: str,
    port: int,
    *,
    path: str = "/",
    timeout: float = 1.0,
) -> ProbeOutcome:
    """Probe ``http://host:port<path>``.

    Returns a :class:`ProbeOutcome` with the TCP/HTTP results. Never
    raises — every failure mode maps onto a field.
    """
    url = f"http://{host}:{port}{path}"
    if not _tcp_open(host, port, timeout):
        return ProbeOutcome(url=url, tcp_open=False, http_status=None, body=None, error=None)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    try:
        # URL is host+port-from-trusted-config + literal http:// scheme.
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 # nosec B310
            return ProbeOutcome(
                url=url,
                tcp_open=True,
                http_status=resp.status,
                body=resp.read(_MAX_BODY_BYTES),
                error=None,
            )
    except urllib.error.HTTPError as err:
        try:
            body = err.read(_MAX_BODY_BYTES)
        except OSError:
            body = None
        return ProbeOutcome(
            url=url, tcp_open=True, http_status=err.code, body=body, error=None,
        )
    except OSError as err:  # URLError, timeout, etc.
        return ProbeOutcome(
            url=url, tcp_open=True, http_status=None, body=None,
            error=f"{err.__class__.__name__}: {err}",
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_detect_port.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_detect/_http.py tests/test_detect_port.py
git commit -m "$(cat <<'EOF'
detect: TCP-then-HTTP probe primitive

ProbeOutcome dataclass carries url, tcp_open, http_status, body, error.
Mirrors _probes/_runtime two-stage approach but exposes the response
body so callers can fingerprint flavors. Never raises.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Default-port scanner (`_port.detect`)

**Files:**

- Create: `auntiepypi/_detect/_port.py`
- Test: extend `tests/test_detect_port.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_detect_port.py`:

```python
from http.server import BaseHTTPRequestHandler

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._port import (
    DEFAULT_PORTS,
    detect,
    fingerprint_flavor,
)


def test_default_ports_exposed() -> None:
    assert 3141 in DEFAULT_PORTS
    assert 8080 in DEFAULT_PORTS


def test_fingerprint_devpi_via_resources_key() -> None:
    body = b'{"type": "devpi-server", "resources": {"login": "/+login"}}'
    assert fingerprint_flavor(body, content_type="application/json") == "devpi"


def test_fingerprint_pypiserver_via_html_anchors() -> None:
    body = b'<html><body><a href="foo/">foo</a><a href="bar/">bar</a></body></html>'
    assert fingerprint_flavor(body, content_type="text/html") == "pypiserver"


def test_fingerprint_unknown_for_bare_simple_index() -> None:
    body = b'<html><body>nothing</body></html>'
    assert fingerprint_flavor(body, content_type="text/html") == "unknown"


def test_fingerprint_unknown_when_body_none() -> None:
    assert fingerprint_flavor(None, content_type=None) == "unknown"


def test_detect_emits_absent_for_closed_default_ports(monkeypatch) -> None:
    """When DEFAULT_PORTS aren't listening, scan emits absent detections."""
    monkeypatch.setattr(
        "auntiepypi._detect._port.DEFAULT_PORTS", (_free_port(), _free_port()),
    )
    detections = detect(declared=[], scan_processes=False)
    assert all(isinstance(d, Detection) for d in detections)
    assert all(d.status == "absent" for d in detections)
    assert all(d.source == "port" for d in detections)


def test_detect_skips_ports_in_covered_set(monkeypatch) -> None:
    """When a port is in `covered`, _port skips it."""
    p1, p2 = _free_port(), _free_port()
    monkeypatch.setattr("auntiepypi._detect._port.DEFAULT_PORTS", (p1, p2))
    detections = detect(declared=[], scan_processes=False, covered={("127.0.0.1", p1)})
    ports = {d.port for d in detections}
    assert p1 not in ports
    assert p2 in ports


def test_detect_finds_running_pypiserver(http_server, monkeypatch) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<a href="alpha/">alpha</a>')
    host, port = http_server(H)
    monkeypatch.setattr("auntiepypi._detect._port.DEFAULT_PORTS", (port,))
    detections = detect(declared=[], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.status == "up"
    assert d.flavor == "pypiserver"
    assert d.port == port
    assert d.name == f"pypiserver:{port}"
    assert d.source == "port"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_detect_port.py -v
```

Expected: ImportError on `auntiepypi._detect._port`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_port.py`:

```python
"""Default-port scanner.

Probes a small fixed set of well-known PyPI server ports on localhost.
Each probe emits a :class:`Detection` regardless of outcome (absent
detections matter for the overview report, except when declarations
exist — see :mod:`auntiepypi._detect._runtime`).
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import ProbeOutcome, probe_endpoint

DEFAULT_PORTS: tuple[int, ...] = (3141, 8080)
_DEFAULT_HOST = "127.0.0.1"
_TIMEOUT = 1.0
_HREF_DIR = re.compile(rb'<a\s+href=["\'][^"\']+/["\']', re.IGNORECASE)


def fingerprint_flavor(body: bytes | None, content_type: str | None) -> str:
    """Return ``"devpi"`` | ``"pypiserver"`` | ``"unknown"`` for one HTTP body."""
    if body is None:
        return "unknown"
    if content_type and "json" in content_type.lower():
        try:
            data = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict) and "resources" in data:
            return "devpi"
        return "unknown"
    # PEP 503 simple index: HTML with multiple <a href="X/"> anchors.
    matches = _HREF_DIR.findall(body)
    if len(matches) >= 1:
        return "pypiserver"
    return "unknown"


def _content_type(outcome: ProbeOutcome) -> str | None:
    # urllib stashes headers via the response object; we don't keep it.
    # We sniff the body instead: if it parses as JSON with a dict, treat as JSON.
    if outcome.body is None:
        return None
    head = outcome.body.lstrip()[:1]
    if head == b"{":
        return "application/json"
    if head == b"<":
        return "text/html"
    return None


def _detection_for(host: str, port: int, outcome: ProbeOutcome) -> Detection:
    if not outcome.tcp_open:
        return Detection(
            name=f"unknown:{port}",
            flavor="unknown",
            host=host,
            port=port,
            url=outcome.url,
            status="absent",
            source="port",
        )
    flavor = fingerprint_flavor(outcome.body, _content_type(outcome))
    if outcome.http_status is None:
        return Detection(
            name=f"{flavor}:{port}",
            flavor=flavor,
            host=host,
            port=port,
            url=outcome.url,
            status="down",
            source="port",
            detail=outcome.error or "http error",
        )
    if 200 <= outcome.http_status < 300:
        return Detection(
            name=f"{flavor}:{port}",
            flavor=flavor,
            host=host,
            port=port,
            url=outcome.url,
            status="up",
            source="port",
        )
    return Detection(
        name=f"{flavor}:{port}",
        flavor=flavor,
        host=host,
        port=port,
        url=outcome.url,
        status="down",
        source="port",
        detail=f"http {outcome.http_status}",
    )


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
    covered: set[tuple[str, int]] | None = None,
) -> list[Detection]:
    """Probe ``DEFAULT_PORTS`` on localhost; skip any ``(host, port)`` in ``covered``."""
    del declared, scan_processes  # signature parity with other detectors; not used here
    skip = covered or set()
    targets = [
        (_DEFAULT_HOST, p) for p in DEFAULT_PORTS if (_DEFAULT_HOST, p) not in skip
    ]
    if not targets:
        return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        outcomes = list(
            ex.map(lambda hp: probe_endpoint(hp[0], hp[1], timeout=_TIMEOUT), targets)
        )
    return [_detection_for(host, port, o) for (host, port), o in zip(targets, outcomes)]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_detect_port.py -v
```

Expected: All tests pass (~11 tests in this file by now).

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_detect/_port.py tests/test_detect_port.py
git commit -m "$(cat <<'EOF'
detect: default-port scanner with flavor fingerprinting

Probes DEFAULT_PORTS = (3141, 8080) on localhost and dispatches flavor
from the HTTP body: JSON `{"resources": ...}` => devpi; HTML with
PEP-503-style anchors => pypiserver; bare-success-2xx => unknown.
Skips any (host, port) already in `covered` (set by the runtime's
augment-from-declared logic).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Declared-inventory detector (`_declared.detect`)

**Files:**

- Create: `auntiepypi/_detect/_declared.py`
- Test: `tests/test_detect_declared.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect_declared.py`:

```python
"""Tests for the declared-inventory detector."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._declared import detect


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def http_server() -> Iterator:
    servers: list[HTTPServer] = []

    def start(handler_cls):
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return "127.0.0.1", server.server_address[1]

    yield start

    for s in servers:
        s.shutdown()
        s.server_close()


def _silent(handler_cls):
    handler_cls.log_message = lambda *a, **kw: None
    return handler_cls


def test_empty_declared_returns_empty() -> None:
    assert detect(declared=[], scan_processes=False) == []


def test_declared_absent_when_nothing_listens() -> None:
    spec = ServerSpec(name="main", flavor="pypiserver", host="127.0.0.1", port=_free_port())
    detections = detect(declared=[spec], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.name == "main"
    assert d.status == "absent"
    assert d.source == "declared"
    assert d.flavor == "pypiserver"


def test_declared_up_when_server_returns_200(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b'<a href="foo/">foo</a>')
    host, port = http_server(H)
    spec = ServerSpec(
        name="main", flavor="pypiserver", host=host, port=port,
        managed_by="systemd-user", unit="pypi.service",
    )
    detections = detect(declared=[spec], scan_processes=False)
    assert len(detections) == 1
    d = detections[0]
    assert d.status == "up"
    assert d.name == "main"
    assert d.managed_by == "systemd-user"
    assert d.unit == "pypi.service"


def test_declared_flavor_mismatch_marked_down(http_server) -> None:
    """Declared flavor must match the fingerprint; otherwise status=down."""
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"resources": {}}')  # devpi-shaped
    host, port = http_server(H)
    spec = ServerSpec(name="main", flavor="pypiserver", host=host, port=port)
    detections = detect(declared=[spec], scan_processes=False)
    d = detections[0]
    assert d.status == "down"
    assert "flavor mismatch" in (d.detail or "")


def test_declared_5xx_marked_down(http_server) -> None:
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(503)
            self.end_headers()
    host, port = http_server(H)
    spec = ServerSpec(name="main", flavor="pypiserver", host=host, port=port)
    detections = detect(declared=[spec], scan_processes=False)
    assert detections[0].status == "down"
    assert "503" in (detections[0].detail or "")


def test_declared_unknown_flavor_skips_fingerprint_check(http_server) -> None:
    """flavor='unknown' means 'I don't care what answers'; any 2xx is up."""
    @_silent
    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"hello")
    host, port = http_server(H)
    spec = ServerSpec(name="x", flavor="unknown", host=host, port=port)
    d = detect(declared=[spec], scan_processes=False)[0]
    assert d.status == "up"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_detect_declared.py -v
```

Expected: ImportError on `auntiepypi._detect._declared`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_declared.py`:

```python
"""Declared-inventory detector.

Probes each ``ServerSpec`` from ``[[tool.auntiepypi.servers]]`` and
emits one :class:`Detection`. Propagates declaration metadata
(``managed_by``, ``unit``, …) through unchanged. Validates the
declared flavor against the fingerprint and reports a flavor mismatch
as ``status="down"``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._http import ProbeOutcome, probe_endpoint
from auntiepypi._detect._port import fingerprint_flavor

_TIMEOUT = 1.0


def _content_type(outcome: ProbeOutcome) -> str | None:
    if outcome.body is None:
        return None
    head = outcome.body.lstrip()[:1]
    if head == b"{":
        return "application/json"
    if head == b"<":
        return "text/html"
    return None


def _detection_for(spec: ServerSpec, outcome: ProbeOutcome) -> Detection:
    common = {
        "name": spec.name,
        "flavor": spec.flavor,
        "host": spec.host,
        "port": spec.port,
        "url": outcome.url,
        "source": "declared",
        "managed_by": spec.managed_by,
        "unit": spec.unit,
        "dockerfile": spec.dockerfile,
        "compose": spec.compose,
        "service": spec.service,
        "command": spec.command,
    }
    if not outcome.tcp_open:
        return Detection(status="absent", **common)
    if outcome.http_status is None:
        return Detection(status="down", detail=outcome.error or "http error", **common)
    if not (200 <= outcome.http_status < 300):
        return Detection(status="down", detail=f"http {outcome.http_status}", **common)
    # 2xx — verify flavor (skip when declared flavor is "unknown")
    if spec.flavor != "unknown":
        observed = fingerprint_flavor(outcome.body, _content_type(outcome))
        if observed != spec.flavor and observed != "unknown":
            return Detection(
                status="down",
                detail=f"flavor mismatch: expected {spec.flavor!r}, saw {observed!r}",
                **common,
            )
    return Detection(status="up", **common)


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
) -> list[Detection]:
    """Probe each declared spec; emit one Detection per spec."""
    del scan_processes  # not relevant to this detector
    specs = list(declared)
    if not specs:
        return []
    with ThreadPoolExecutor(max_workers=8) as ex:
        outcomes = list(
            ex.map(
                lambda s: probe_endpoint(s.host, s.port, timeout=_TIMEOUT),
                specs,
            )
        )
    return [_detection_for(s, o) for s, o in zip(specs, outcomes)]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_detect_declared.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_detect/_declared.py tests/test_detect_declared.py
git commit -m "$(cat <<'EOF'
detect: declared-inventory detector

Probes each ServerSpec from [[tool.auntiepypi.servers]]. Reports up /
down / absent. Validates declared flavor against the fingerprint and
flags mismatches as down. Propagates managed_by/unit/dockerfile/etc.
verbatim onto the Detection (echoed in --json; not acted on in v0.2.0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `/proc` scanner (Linux-only, opt-in)

**Files:**

- Create: `auntiepypi/_detect/_proc.py`
- Test: `tests/test_detect_proc.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_detect_proc.py`:

```python
"""Tests for the /proc-based detector (Linux-only; opt-in)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from auntiepypi._detect._detection import Detection
from auntiepypi._detect._proc import (
    KNOWN_CMDLINE_PATTERNS,
    detect,
    parse_proc_net_tcp,
    scan_proc_root,
)

linux_only = pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc only")


def test_known_patterns_include_pypi_server() -> None:
    assert any("pypi-server" in p for p in KNOWN_CMDLINE_PATTERNS)
    assert any("devpi-server" in p for p in KNOWN_CMDLINE_PATTERNS)


@linux_only
def test_proc_root_missing_returns_empty(tmp_path) -> None:
    detections = detect(declared=[], scan_processes=True, proc_root=tmp_path / "no")
    assert detections == []


@linux_only
def test_disabled_returns_empty(tmp_path) -> None:
    """scan_processes=False short-circuits."""
    assert detect(declared=[], scan_processes=False, proc_root=Path("/proc")) == []


@linux_only
def test_scan_proc_root_finds_matching_cmdline(tmp_path) -> None:
    pid_dir = tmp_path / "1234"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("pypi-server\n")
    # cmdline uses NUL separators between argv entries
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00")
    matches = scan_proc_root(tmp_path)
    assert len(matches) == 1
    assert matches[0].pid == 1234
    assert "pypi-server" in matches[0].cmdline


@linux_only
def test_parse_proc_net_tcp_extracts_listening_pids(tmp_path) -> None:
    """0A in the state column means LISTEN; that's what we care about."""
    body = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 9999 1 ffff 100 0 0 10 0
"""
    tcp_path = tmp_path / "proc_net_tcp"
    tcp_path.write_text(body)
    listeners = parse_proc_net_tcp(tcp_path)
    assert listeners == {9999: 8080}


@linux_only
def test_full_pipeline_links_pid_to_port(tmp_path) -> None:
    """End-to-end: cmdline match + matching inode in net/tcp + fd link."""
    proc = tmp_path / "proc"
    proc.mkdir()
    pid_dir = proc / "1234"
    pid_dir.mkdir()
    (pid_dir / "comm").write_text("pypi-server\n")
    (pid_dir / "cmdline").write_bytes(b"pypi-server\x00run\x00-p\x008080\x00")
    fd_dir = pid_dir / "fd"
    fd_dir.mkdir()
    # /proc/<pid>/fd/3 -> socket:[9999]
    (fd_dir / "3").symlink_to("socket:[9999]")
    net_dir = proc / "net"
    net_dir.mkdir()
    (net_dir / "tcp").write_text(
        "  sl local rem st\n"
        "   0: 0100007F:1F90 00000000:0000 0A 0 0 0 0 0 9999\n"
    )
    detections = detect(declared=[], scan_processes=True, proc_root=proc)
    assert len(detections) == 1
    d = detections[0]
    assert isinstance(d, Detection)
    assert d.pid == 1234
    assert d.port == 8080
    assert d.flavor == "pypiserver"
    assert d.source == "proc"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_detect_proc.py -v
```

Expected: ImportError on `auntiepypi._detect._proc`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_proc.py`:

```python
"""Linux ``/proc`` scanner — opt-in via ``--proc`` or
``[tool.auntiepypi].scan_processes = true``.

On non-Linux platforms this module's ``detect()`` short-circuits to ``[]``.

What we look for:

1. Processes whose ``/proc/<pid>/comm`` or ``/proc/<pid>/cmdline``
   matches a known PyPI-server pattern.
2. The TCP port that process is listening on, by walking
   ``/proc/<pid>/fd/*`` for ``socket:[<inode>]`` links and matching the
   inode against ``/proc/net/tcp`` LISTEN entries.

Linux-only by construction. Other platforms get a documented no-op so
``--proc`` is still accepted (with a stderr note from the CLI layer).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from auntiepypi._detect._config import ServerSpec
from auntiepypi._detect._detection import Detection

KNOWN_CMDLINE_PATTERNS: tuple[str, ...] = (
    "pypi-server",
    "devpi-server",
)
_PROC_DEFAULT = Path("/proc")
_LISTEN_STATE = "0A"  # TCP_LISTEN per linux/include/net/tcp_states.h


@dataclass(frozen=True)
class _ProcMatch:
    pid: int
    comm: str
    cmdline: str


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return None


def _flavor_from_cmdline(cmdline: str) -> str:
    if "pypi-server" in cmdline:
        return "pypiserver"
    if "devpi-server" in cmdline:
        return "devpi"
    return "unknown"


def scan_proc_root(proc_root: Path) -> list[_ProcMatch]:
    """Walk ``proc_root`` for PID dirs whose cmdline matches a known pattern."""
    if not proc_root.is_dir():
        return []
    matches: list[_ProcMatch] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline_path = entry / "cmdline"
        cmdline_bytes: bytes | None = None
        try:
            cmdline_bytes = cmdline_path.read_bytes()
        except OSError:
            continue
        cmdline = cmdline_bytes.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        comm = (_read_text(entry / "comm") or "").strip()
        if not any(p in cmdline or p in comm for p in KNOWN_CMDLINE_PATTERNS):
            continue
        matches.append(_ProcMatch(pid=pid, comm=comm, cmdline=cmdline))
    return matches


_TCP_LINE_RE = re.compile(
    r"^\s*\d+:\s+([0-9A-Fa-f]+):([0-9A-Fa-f]+)\s+[0-9A-Fa-f]+:[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)"
    r"(?:\s+\S+){5,}\s+(\d+)"
)


def parse_proc_net_tcp(path: Path) -> dict[int, int]:
    """Return ``{inode: port}`` for every LISTEN socket in ``/proc/net/tcp``."""
    text = _read_text(path)
    if text is None:
        return {}
    inode_to_port: dict[int, int] = {}
    for line in text.splitlines():
        m = _TCP_LINE_RE.match(line)
        if not m:
            continue
        local_port_hex = m.group(2)
        state = m.group(3).upper()
        inode = int(m.group(4))
        if state != _LISTEN_STATE:
            continue
        port = int(local_port_hex, 16)
        if inode != 0:
            inode_to_port[inode] = port
    return inode_to_port


def _inodes_for_pid(pid_dir: Path) -> set[int]:
    """Walk ``pid_dir/fd/*`` for ``socket:[<inode>]`` links."""
    fd_dir = pid_dir / "fd"
    inodes: set[int] = set()
    try:
        fd_entries = list(fd_dir.iterdir())
    except OSError:
        return inodes
    for fd in fd_entries:
        try:
            target = os.readlink(fd)
        except OSError:
            continue
        m = re.match(r"socket:\[(\d+)\]", target)
        if not m:
            continue
        inodes.add(int(m.group(1)))
    return inodes


def detect(
    declared: Iterable[ServerSpec],
    *,
    scan_processes: bool,
    proc_root: Path | None = None,
) -> list[Detection]:
    """Find PyPI servers via ``/proc``. No-op when disabled or non-Linux."""
    del declared  # signature parity; this detector is independent
    if not scan_processes:
        return []
    if proc_root is None and sys.platform != "linux":
        return []
    root = proc_root if proc_root is not None else _PROC_DEFAULT
    matches = scan_proc_root(root)
    if not matches:
        return []
    listeners = parse_proc_net_tcp(root / "net" / "tcp")
    detections: list[Detection] = []
    for m in matches:
        port: int | None = None
        for inode in _inodes_for_pid(root / str(m.pid)):
            if inode in listeners:
                port = listeners[inode]
                break
        if port is None:
            # We saw the process but couldn't tie it to a listening port.
            # Skip — the port-scan / declared paths will catch it if it is
            # actually serving on a known endpoint.
            continue
        flavor = _flavor_from_cmdline(m.cmdline)
        detections.append(
            Detection(
                name=f"{flavor}:{port}",
                flavor=flavor,
                host="127.0.0.1",
                port=port,
                url=f"http://127.0.0.1:{port}/",
                status="up",  # process is alive + listening; trust it
                source="proc",
                pid=m.pid,
                cmdline=m.cmdline,
            )
        )
    return detections
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_detect_proc.py -v
```

Expected: All Linux tests pass; non-Linux platforms skip the marked tests.

- [ ] **Step 5: Commit**

```bash
git add auntiepypi/_detect/_proc.py tests/test_detect_proc.py
git commit -m "$(cat <<'EOF'
detect: opt-in /proc scanner (Linux)

Walks /proc for PIDs whose cmdline matches pypi-server / devpi-server.
For each match, parses /proc/<pid>/fd/* socket inodes and joins with
/proc/net/tcp LISTEN entries to find the listening port. Short-circuits
to [] on non-Linux or when scan_processes=False. proc_root is injectable
for tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Detection runtime (`detect_all`) — merge logic

**Files:**

- Create: `auntiepypi/_detect/_runtime.py`
- Modify: `auntiepypi/_detect/__init__.py` (re-export `detect_all`)
- Test: extend `tests/test_detect_runtime.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_detect_runtime.py`:

```python
from unittest.mock import patch

from auntiepypi._detect._config import ServerSpec, ServersConfig
from auntiepypi._detect._runtime import detect_all


def _det(name, port, source, status="up", flavor="pypiserver", pid=None) -> Detection:
    return Detection(
        name=name, flavor=flavor, host="127.0.0.1", port=port,
        url=f"http://127.0.0.1:{port}/", status=status, source=source, pid=pid,
    )


def test_detect_all_empty_config_runs_port_scan_only() -> None:
    cfg = ServersConfig(specs=(), scan_processes=False)
    declared_calls: list = []

    def fake_declared(declared, *, scan_processes):
        declared_calls.append(list(declared))
        return []

    def fake_port(declared, *, scan_processes, covered=None):
        return [_det("pypiserver:8080", 8080, "port", status="absent")]

    def fake_proc(declared, *, scan_processes, **kw):
        return []

    with patch("auntiepypi._detect._runtime._declared_detect", fake_declared), \
         patch("auntiepypi._detect._runtime._port_detect", fake_port), \
         patch("auntiepypi._detect._runtime._proc_detect", fake_proc):
        result = detect_all(cfg)
    assert len(result) == 1
    assert result[0].source == "port"
    assert declared_calls == [[]]


def test_detect_all_augment_suppresses_absent_from_scan_when_declared_exists() -> None:
    spec = ServerSpec(name="main", flavor="pypiserver", host="127.0.0.1", port=8080)
    cfg = ServersConfig(specs=(spec,), scan_processes=False)
    declared_results = [_det("main", 8080, "declared")]
    port_results = [
        _det("devpi:3141", 3141, "port", status="absent", flavor="unknown"),
    ]

    with patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: declared_results), \
         patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: port_results), \
         patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: []):
        result = detect_all(cfg)
    # Declared exists -> port-scan absents are suppressed.
    sources = [d.source for d in result]
    assert "declared" in sources
    # No port-scan absent in result
    port_absent = [d for d in result if d.source == "port" and d.status == "absent"]
    assert port_absent == []


def test_detect_all_keeps_port_scan_finds_when_declared_exists() -> None:
    """When declared exists AND port scan finds an *up* extra, keep it."""
    spec = ServerSpec(name="main", flavor="devpi", host="127.0.0.1", port=3141)
    cfg = ServersConfig(specs=(spec,), scan_processes=False)
    declared_results = [_det("main", 3141, "declared", flavor="devpi")]
    port_results = [_det("pypiserver:8080", 8080, "port", status="up")]

    with patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: declared_results), \
         patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: port_results), \
         patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: []):
        result = detect_all(cfg)
    sources = {d.source for d in result}
    assert sources == {"declared", "port"}


def test_detect_all_proc_enriches_existing_detection_with_pid() -> None:
    """Proc-found PID for a (host, port) already detected enriches it."""
    cfg = ServersConfig(specs=(), scan_processes=True)
    port_d = _det("pypiserver:8080", 8080, "port", status="up")
    proc_d = _det("pypiserver:8080", 8080, "proc", status="up", pid=1234)

    with patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: []), \
         patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: [port_d]), \
         patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: [proc_d]):
        result = detect_all(cfg)
    # One detection, port-source kept, pid enriched from proc.
    assert len(result) == 1
    assert result[0].pid == 1234
    assert result[0].source == "port"  # kept original source


def test_detect_all_proc_only_finds_appended() -> None:
    cfg = ServersConfig(specs=(), scan_processes=True)
    proc_d = _det("pypiserver:9001", 9001, "proc", pid=999)

    with patch("auntiepypi._detect._runtime._declared_detect", lambda *a, **kw: []), \
         patch("auntiepypi._detect._runtime._port_detect", lambda *a, **kw: []), \
         patch("auntiepypi._detect._runtime._proc_detect", lambda *a, **kw: [proc_d]):
        result = detect_all(cfg)
    assert len(result) == 1
    assert result[0].source == "proc"
    assert result[0].port == 9001
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_detect_runtime.py -v
```

Expected: ImportError on `auntiepypi._detect._runtime`.

- [ ] **Step 3: Write minimal implementation**

Create `auntiepypi/_detect/_runtime.py`:

```python
"""``detect_all`` — single entry point for callers.

Order of operations:

1. ``_declared.detect`` first. Build ``covered = {(host, port) ...}``.
2. ``_port.detect`` over default ports minus ``covered``. If declarations
   exist, drop ``status="absent"`` from the port detector's output
   (the augment + suppress-absent rule).
3. If ``scan_processes``: ``_proc.detect``. Merge by ``(host, port)`` —
   proc-found pids enrich existing detections; proc-only detections are
   appended.
"""

from __future__ import annotations

from dataclasses import replace

from auntiepypi._detect._config import ServersConfig
from auntiepypi._detect._declared import detect as _declared_detect
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._port import detect as _port_detect
from auntiepypi._detect._proc import detect as _proc_detect


def detect_all(config: ServersConfig) -> list[Detection]:
    """Run all detectors and merge results."""
    declared_results = _declared_detect(config.specs, scan_processes=config.scan_processes)
    covered: set[tuple[str, int]] = {(d.host, d.port) for d in declared_results}

    port_results = _port_detect(
        config.specs, scan_processes=config.scan_processes, covered=covered,
    )
    if declared_results:
        # Augment + suppress-absent rule.
        port_results = [d for d in port_results if d.status != "absent"]

    detections = list(declared_results) + list(port_results)

    if not config.scan_processes:
        return detections

    proc_results = _proc_detect(
        config.specs, scan_processes=config.scan_processes,
    )
    detections = _merge_proc(detections, proc_results)
    return detections


def _merge_proc(
    base: list[Detection], proc_results: list[Detection]
) -> list[Detection]:
    """Enrich ``base`` with PIDs from ``proc_results``; append proc-only finds."""
    by_endpoint: dict[tuple[str, int], int] = {}
    for i, d in enumerate(base):
        by_endpoint[(d.host, d.port)] = i

    appended: list[Detection] = []
    for p in proc_results:
        key = (p.host, p.port)
        if key in by_endpoint:
            i = by_endpoint[key]
            existing = base[i]
            base[i] = replace(
                existing,
                pid=existing.pid if existing.pid is not None else p.pid,
                cmdline=existing.cmdline if existing.cmdline is not None else p.cmdline,
            )
        else:
            appended.append(p)
    return base + appended
```

- [ ] **Step 4: Update `__init__.py` to re-export `detect_all`**

Edit `auntiepypi/_detect/__init__.py`:

```python
"""auntiepypi detection layer.

(docstring as before)
"""

from __future__ import annotations

from auntiepypi._detect._config import (
    ServerConfigError,
    ServerSpec,
    ServersConfig,
    load_servers,
)
from auntiepypi._detect._detection import Detection
from auntiepypi._detect._runtime import detect_all

__all__ = [
    "Detection",
    "ServerConfigError",
    "ServerSpec",
    "ServersConfig",
    "detect_all",
    "load_servers",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_detect_runtime.py -v
```

Expected: All tests pass (~8 tests in this file).

Run the full detect suite:

```bash
uv run pytest tests/test_detect_*.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/_detect/_runtime.py auntiepypi/_detect/__init__.py tests/test_detect_runtime.py
git commit -m "$(cat <<'EOF'
detect: detect_all runtime — merge declared + port + proc

Three-stage merge: declared first; port-scan over uncovered defaults
(absent suppressed when declared exists); /proc enrichment merges by
(host, port) with proc-only finds appended. Single entry point for
callers (cli/_commands/overview.py wires up next).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Wire `_detect/` into composite `auntie overview`

**Files:**

- Modify: `auntiepypi/cli/_commands/overview.py`
- Modify: `tests/test_cli_overview_composite.py`

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/test_cli_overview_composite.py`:

```python
"""Tests for the composite ``auntie overview`` (packages + detected servers)."""

from __future__ import annotations

import json

import pytest

from auntiepypi._detect._detection import Detection
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
    target = "auntiepypi.cli._commands._packages.overview"
    monkeypatch.setattr(f"{target}.fetch_pypi", lambda pkg: _good_pypi(pkg))
    monkeypatch.setattr(f"{target}.fetch_pypistats", lambda pkg: {"data": {"last_week": 100}})
    (tmp_path / "pyproject.toml").write_text(
        '[tool.auntiepypi]\npackages = ["alpha"]\n'
    )
    monkeypatch.chdir(tmp_path)


def _stub_detect(detections):
    """Return a stub that ignores its config arg and returns `detections`."""
    return lambda cfg: list(detections)


def test_no_arg_emits_both_categories(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main", flavor="pypiserver", host="127.0.0.1", port=8080,
            url="http://127.0.0.1:8080/", status="up", source="declared",
        ),
    ]
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections)
    )
    rc = main(["overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    cats = {s["category"] for s in payload["sections"]}
    assert cats == {"packages", "servers"}
    server_titles = {s["title"] for s in payload["sections"] if s["category"] == "servers"}
    assert "main" in server_titles


def test_declared_servers_show_up_in_composite(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main", flavor="pypiserver", host="127.0.0.1", port=8081,
            url="http://127.0.0.1:8081/", status="up", source="declared",
            managed_by="systemd-user", unit="pypi.service",
        ),
    ]
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections)
    )
    rc = main(["overview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    server = next(s for s in payload["sections"] if s["title"] == "main")
    field_map = {f["name"]: f["value"] for f in server["fields"]}
    assert field_map["source"] == "declared"
    assert field_map["managed_by"] == "systemd-user"
    assert field_map["unit"] == "pypi.service"


def test_target_resolves_to_declared_name(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="main", flavor="pypiserver", host="127.0.0.1", port=8080,
            url="http://127.0.0.1:8080/", status="up", source="declared",
        ),
    ]
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections)
    )
    rc = main(["overview", "main", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "main"
    titles = {s["title"] for s in payload["sections"]}
    assert titles == {"main"}


def test_target_resolves_to_bare_flavor_alias(composite_env, capsys, monkeypatch) -> None:
    """`auntie overview pypiserver` resolves to the first pypiserver detection."""
    detections = [
        Detection(
            name="alpha", flavor="devpi", host="127.0.0.1", port=3141,
            url="http://127.0.0.1:3141/+api", status="up", source="declared",
        ),
        Detection(
            name="beta", flavor="pypiserver", host="127.0.0.1", port=8080,
            url="http://127.0.0.1:8080/", status="up", source="declared",
        ),
    ]
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections)
    )
    rc = main(["overview", "pypiserver", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "beta"
    assert {s["title"] for s in payload["sections"]} == {"beta"}


def test_target_resolves_to_auto_name_with_port(composite_env, capsys, monkeypatch) -> None:
    detections = [
        Detection(
            name="pypiserver:8080", flavor="pypiserver", host="127.0.0.1", port=8080,
            url="http://127.0.0.1:8080/", status="up", source="port",
        ),
    ]
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect(detections)
    )
    rc = main(["overview", "pypiserver:8080", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert {s["title"] for s in payload["sections"]} == {"pypiserver:8080"}


def test_target_resolves_to_package(composite_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect([])
    )
    rc = main(["overview", "alpha", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "alpha"
    titles = {s["title"] for s in payload["sections"]}
    assert "_summary" in titles


def test_unknown_target_zero_target_report(composite_env, capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect([])
    )
    rc = main(["overview", "i-am-not-real", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["sections"] == []
    assert payload.get("note")


def test_no_arg_without_packages_config(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", _stub_detect([])
    )
    rc = main(["overview", "--json"])
    payload = json.loads(capsys.readouterr().out)
    cats = {s["category"] for s in payload["sections"]}
    # Without packages config and no detections, sections may be empty.
    # The diagnostic should still appear for missing packages config.
    captured = capsys.readouterr()
    assert payload["sections"] == [] or "servers" in cats
    # stderr was already drained by the previous capsys.readouterr() call,
    # but we did capture the JSON. Hit it again to check no double-drain issue:
    _ = captured  # avoid unused-warning
    # The packages-config diagnostic comes from _try_package_target; for the
    # composite no-arg branch we emit it via the existing emit_diagnostic call.


def test_proc_flag_propagates_to_detect_all(composite_env, capsys, monkeypatch) -> None:
    """`--proc` overrides the config's scan_processes to True."""
    seen: list = []

    def stub(cfg):
        seen.append(cfg.scan_processes)
        return []

    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", stub
    )
    rc = main(["overview", "--proc", "--json"])
    assert rc == 0
    assert seen == [True]


def test_default_scan_processes_false_when_no_config(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    seen: list = []

    def stub(cfg):
        seen.append(cfg.scan_processes)
        return []

    monkeypatch.setattr(
        "auntiepypi.cli._commands.overview.detect_all", stub
    )
    rc = main(["overview", "--json"])
    assert rc == 0
    assert seen == [False]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli_overview_composite.py -v
```

Expected: most tests fail because `overview.py` still uses `_probes/` and has no `--proc` flag.

- [ ] **Step 3: Rewrite `auntiepypi/cli/_commands/overview.py`**

Replace its content:

```python
"""``auntie overview`` — composite of packages + detected servers.

v0.2.0 swaps the server section group's data source from ``_probes/``
to ``_detect/``. Declared servers, default-port scan results, and
``--proc`` finds all surface here. ``_probes/`` and ``doctor --fix``
are deliberately untouched.
"""

from __future__ import annotations

import argparse
from dataclasses import replace

from auntiepypi._detect import (
    ServerConfigError,
    ServersConfig,
    detect_all,
    load_servers,
)
from auntiepypi._packages_config import ConfigError, load_package_names
from auntiepypi.cli._commands._packages.overview import (
    _dashboard,
    _deep_dive,
    _emit,
    _fetch_pair,
)
from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError
from auntiepypi.cli._output import emit_diagnostic, emit_result

_SUBJECT = "auntie"


def _load_config_or_raise(scan_processes_override: bool) -> ServersConfig:
    try:
        cfg = load_servers()
    except ServerConfigError as err:
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=str(err),
            remediation=(
                "fix [[tool.auntiepypi.servers]] in pyproject.toml; see "
                "docs/superpowers/specs/2026-04-29-auntie-overview-detection-design.md"
            ),
        ) from err
    if scan_processes_override:
        cfg = replace(cfg, scan_processes=True)
    return cfg


def _server_sections(detections: list) -> list[dict]:
    return [d.to_section() for d in detections]


def _try_package_target(target: str) -> dict | None:
    try:
        names = load_package_names()
    except ConfigError:
        return None
    if target not in names:
        return None
    pypi, stats, warnings, _env_failure = _fetch_pair(target)
    for w in warnings:
        emit_diagnostic(f"warning: {w}")
    return _deep_dive(target, pypi, stats)


def _detection_target(detections: list, target: str):
    """Return the matching Detection or None.

    Resolution priority:
      1. Exact name match.
      2. Bare flavor alias — first detection with `flavor == target`.
    """
    for d in detections:
        if d.name == target:
            return d
    for d in detections:
        if d.flavor == target:
            return d
    return None


def _composite_no_arg(json_mode: bool, detections: list) -> int:
    sections: list[dict] = []
    try:
        names = load_package_names()
    except ConfigError:
        names = []
        emit_diagnostic("warning: no [tool.auntiepypi].packages configured; showing servers only")
    if names:
        payload, warnings, _failures = _dashboard(names)
        for w in warnings:
            emit_diagnostic(f"warning: {w}")
        sections.extend(payload["sections"])
    sections.extend(_server_sections(detections))
    payload = {"subject": _SUBJECT, "sections": sections}
    _emit(payload, json_mode)
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    cfg = _load_config_or_raise(scan_processes_override=bool(getattr(args, "proc", False)))
    detections = detect_all(cfg)
    target = args.target if args.target else None

    if target is None:
        return _composite_no_arg(json_mode, detections)

    # 1 + 2: detection name match (exact then bare-flavor alias)
    match = _detection_target(detections, target)
    if match is not None:
        payload = {"subject": match.name, "sections": [match.to_section()]}
        _emit(payload, json_mode)
        return 0

    # 3: configured package
    pkg_payload = _try_package_target(target)
    if pkg_payload is not None:
        _emit(pkg_payload, json_mode)
        return 0

    # 4: zero-target report
    note = (
        f"target {target!r} not recognised; emitting zero-target report "
        "(use `auntie overview` with no arg for the default scan)"
    )
    emit_diagnostic(f"warning: {note}")
    payload = {"subject": _SUBJECT, "sections": [], "target": target, "note": note}
    if json_mode:
        emit_result(payload, json_mode=True)
    else:
        emit_result(f"# {_SUBJECT}\n\n(no targets scanned)", json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "overview",
        help="Composite report: packages dashboard + detected PyPI servers.",
    )
    p.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Optional target: a detection name (declared or `<flavor>:<port>`), "
            "a bare flavor (`devpi` / `pypiserver`), or a configured package name."
        ),
    )
    p.add_argument(
        "--proc",
        action="store_true",
        help="Opt-in /proc scan for running PyPI servers (Linux only; no-op elsewhere).",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_overview)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli_overview_composite.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run the existing top-level CLI tests to make sure nothing else broke**

```bash
uv run pytest tests/ -v -x
```

Expected: all green. (Some pre-existing tests reference `auntiepypi.cli._commands.overview.probe_status` — verify those don't exist any longer or are skipped.)

If `tests/test_overview.py` references the old shape, port the relevant assertions:

```bash
uv run pytest tests/test_overview.py -v
```

If failing, read it and update its monkeypatch targets to `auntiepypi.cli._commands.overview.detect_all`.

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/cli/_commands/overview.py tests/test_cli_overview_composite.py tests/test_overview.py
git commit -m "$(cat <<'EOF'
overview: composite uses _detect/ for the servers section

Server sections now come from detect_all(): declared inventory, default
port scan, optional /proc scan via --proc flag. Target resolution:
detection name -> bare flavor alias -> configured package -> zero-target.
Subject changes from "auntiepypi" to "auntie" to match the new CLI name.
_probes/ and doctor are unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Update `learn` and `explain catalog`

**Files:**

- Modify: `auntiepypi/cli/_commands/learn.py`
- Modify: `auntiepypi/explain/catalog.py`
- Modify: `tests/test_cli.py` (update assertions for new strings; verify by running first)

- [ ] **Step 1: Run existing tests to find what changes**

```bash
uv run pytest tests/test_cli.py -v
```

Note any assertions that depend on:

- `auntiepypi local …` strings in `learn` output
- `("local",)` catalog entries
- The `planned` array containing entries

- [ ] **Step 2: Edit `auntiepypi/cli/_commands/learn.py`**

Replace its content:

```python
"""``auntie learn`` — the learnability affordance (shape-adapt).

Self-teaching prompt for an agent that wants to use auntie. Generated
from the same explain catalog so it can never describe a command that
isn't registered.

Must satisfy the agent-first rubric: >=200 chars and mention purpose,
command map, exit codes, --json, explain.
"""

from __future__ import annotations

import argparse

from auntiepypi import __version__
from auntiepypi.cli._output import emit_result

_TEXT = """\
auntie — CLI and agent for managing PyPI packages across the AgentCulture mesh.

Purpose
-------
auntie is both a CLI and an agent that maintains, uses, and serves the
CLI for managing PyPI packages. It supports remote (pypi.org) and the
detect-only view of locally running PyPI servers. It overviews packages
and servers — informational, not gating.

Commands
--------
  auntie learn                 Print this self-teaching prompt. Supports --json.
  auntie explain <path>...     Print markdown docs for any noun/verb path.
                               Supports --json.
  auntie overview [TARGET]     Composite: packages dashboard + detected
                               local servers. With TARGET, drills into
                               one detection name, bare flavor alias, or
                               configured package. --proc opts into a
                               /proc-based scan (Linux). Read-only.
                               Supports --json.
  auntie packages overview [PKG]
                               Read-only PyPI maturity dashboard or
                               per-package deep-dive. Informational,
                               not gating. Supports --json.
  auntie doctor [--fix]        Same probes as v0.0.1 plus diagnoses; with
                               --fix, start configured servers. Default
                               is dry-run. Supports --json.
  auntie whoami                Auth/env probe — which PyPI / TestPyPI /
                               local index is the active environment
                               pointing at? Supports --json.

Configuration
-------------
  pyproject.toml [tool.auntiepypi]
    packages = [...]                      # for `auntie packages overview`
    scan_processes = false                # opt into /proc scan; same as --proc
  pyproject.toml [[tool.auntiepypi.servers]]   # one block per server
    name = "main"
    flavor = "pypiserver"                 # | "devpi" | "unknown"
    port = 8080

The CLI registers two console scripts: `auntie` (preferred) and
`auntiepypi` (alias).

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr are never
mixed.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  auntie explain auntiepypi
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "auntie",
        "package": "auntiepypi",
        "version": __version__,
        "purpose": (
            "CLI and agent for managing PyPI packages; surfaces remote (pypi.org) "
            "package data and a detect-only view of locally running PyPI servers."
        ),
        "commands": [
            {"path": ["learn"], "summary": "Self-teaching prompt."},
            {"path": ["explain"], "summary": "Markdown docs by path."},
            {
                "path": ["overview"],
                "summary": (
                    "Composite: packages dashboard + detected servers. "
                    "TARGET drills into one detection, flavor, or package. "
                    "--proc opts into /proc scan."
                ),
            },
            {
                "path": ["packages", "overview"],
                "summary": "PyPI maturity dashboard or per-package deep-dive.",
            },
            {
                "path": ["doctor"],
                "summary": "Probe + diagnose local PyPI servers; with --fix, start them.",
            },
            {
                "path": ["whoami"],
                "summary": "Report configured PyPI / TestPyPI / local index.",
            },
        ],
        "planned": [],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "auntie explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
```

- [ ] **Step 3: Edit `auntiepypi/explain/catalog.py`**

Make these in-place changes (use Edit, not Write):

Replace the `_ROOT` literal (`# auntiepypi` block) with:

```python
_ROOT = """\
# auntie

auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
that maintains, uses, and serves the CLI for managing PyPI packages. It
overviews packages on pypi.org and detects PyPI-flavored servers running
locally. Informational, not gating.

## Verbs

- `auntie learn` — structured self-teaching prompt.
- `auntie explain <path>` — markdown docs for any noun/verb.
- `auntie overview [TARGET]` — composite: packages dashboard + detected
  local servers. With TARGET, drills into a detection name, bare flavor
  alias (`devpi` / `pypiserver`), or configured package. `--proc` opts
  into a /proc scan (Linux only).
- `auntie packages overview [PKG]` — read-only PyPI maturity dashboard
  (no arg) or per-package deep-dive (with arg).
- `auntie doctor [--fix]` — probe + diagnose; `--fix` starts servers.
- `auntie whoami` — auth/env probe; reports configured indexes.

## Console scripts

The package installs two scripts that point at the same entry point:

- `auntie` — preferred.
- `auntiepypi` — alias kept for backward compatibility.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `auntie explain learn`
- `auntie explain explain`
- `auntie explain overview`
- `auntie explain packages`
- `auntie explain packages overview`
- `auntie explain doctor`
- `auntie explain whoami`
"""
```

Replace `_OVERVIEW`:

```python
_OVERVIEW = """\
# auntie overview

Composite report. With no arg: emits a packages dashboard (one section
per configured package) plus the detected-servers report (one section
per declared server, default-port find, and — when `--proc` is on —
each /proc-discovered process). With an arg, drills into one detection,
bare flavor alias, or configured package, in that priority.

## Detection sources

- **Declared inventory** — `[[tool.auntiepypi.servers]]` in pyproject.toml.
  Probes each declared host:port; carries `managed_by` / `unit` /
  `dockerfile` / etc. through to the JSON envelope (reserved for v0.3.0
  lifecycle work).
- **Default port scan** — probes `127.0.0.1:3141` (devpi) and
  `127.0.0.1:8080` (pypiserver), skipping any (host, port) already
  covered by declarations. When declarations exist, `absent` results
  from the scan are suppressed (so a declared-only user doesn't see
  noisy `pypiserver:8080 absent` rows when their server is on 8081).
- **`/proc` scan** — opt-in via `--proc` (CLI) or
  `[tool.auntiepypi].scan_processes = true` (config). Linux-only;
  no-op elsewhere. Enriches existing detections with PIDs; appends
  proc-only finds.

## Target resolution priority

1. Exact detection name (declared `name` or auto-name `<flavor>:<port>`).
2. Bare flavor alias (`pypiserver` / `devpi` → first detection of that
   flavor).
3. Configured package name.
4. Zero-target report (stderr warning + exit 0).

## Usage

    auntie overview
    auntie overview --json
    auntie overview --proc
    auntie overview <detection-name>          # e.g. `main` or `pypiserver:8080`
    auntie overview <flavor>                  # e.g. `pypiserver`
    auntie overview <configured-pkg>          # e.g. `requests`

## JSON envelope

    {
      "subject": "auntie",
      "sections": [
        {"category": "packages", "title": "<pkg>", "light": "...", "fields": [...]},
        {"category": "servers",  "title": "<name>", "light": "...", "fields": [...]}
      ]
    }

## Remediation for `status: absent`

See `docs/deploy/` for systemd-user unit templates that run pypiserver /
devpi as background services. `auntie` does not start servers itself
(see `auntie doctor --fix` for the existing raise capability).

## Exit codes

- `0` always (read-only; reds do not change the exit).
- `1` malformed `[[tool.auntiepypi.servers]]`.
- `2` only if every detector failed to run.
"""
```

Delete `_LOCAL` (whole block).

Update `ENTRIES`:

```python
ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("auntiepypi",): _ROOT,
    ("auntie",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("whoami",): _WHOAMI,
    ("packages",): _PACKAGES,
    ("packages", "overview"): _PACKAGES_OVERVIEW,
}
```

Note: keep `_LEARN`, `_EXPLAIN`, `_DOCTOR`, `_WHOAMI`, `_PACKAGES`, `_PACKAGES_OVERVIEW` literals as-is *except* swap the prose `auntiepypi <verb>` for `auntie <verb>` where the verb is named (e.g. "Usage: auntiepypi learn" → "Usage: auntie learn"). Use Edit's `replace_all=true` against each literal individually for safety.

- [ ] **Step 4: Update tests if any reference the old strings**

Inspect:

```bash
grep -n "local serve\|local upload\|local mirror\|servers overview\|_M_LOCAL\|_M_SERVERS\|local roadmap" tests/
```

Adjust any failing assertions in `tests/test_cli.py` (the file likely tests `learn --json`'s `planned` array and `explain` paths). Replace expectations:

- `planned` → `[]`
- `explain local` → expect `error: no explain entry for: local` (exit 1)
- references to `auntiepypi` in CLI output may now be `auntie` — update where applicable, but the binary still accepts the alias name on stdin.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -v -x
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add auntiepypi/cli/_commands/learn.py auntiepypi/explain/catalog.py tests/
git commit -m "$(cat <<'EOF'
learn/explain: drop `local` noun; refresh `overview` for detection

Catalog: delete ('local',) entry; refresh root + ('overview',) to
describe detection sources, target resolution priority, and the
auntie/auntiepypi alias pair. Add ('auntie',) -> _ROOT for the new
preferred CLI name.

learn: drop _M_LOCAL / _M_SERVERS milestone constants and their
planned[] entries. planned[] is now []. Verb text describes detection
behavior + --proc flag; mention pyproject.toml schema additions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Register `auntie` console script alias

**Files:**

- Modify: `pyproject.toml`
- Modify: `auntiepypi/cli/__init__.py` (parser `prog` stays `auntiepypi`; we don't change it because Python entry-points pass argv[0] from the script name — argparse picks it up automatically. But `--version` output should reflect both: `--version` already uses `%(prog)s` which uses argv[0], so it'll naturally say `auntie 0.x.y` when called as `auntie`.)

- [ ] **Step 1: Verify the test for the alias**

We need a hermetic test that confirms both entry points resolve to the same `main`. Append to `tests/test_cli.py`:

```python
def test_auntie_alias_console_script_registered() -> None:
    """Both `auntie` and `auntiepypi` are registered to auntiepypi.cli:main."""
    from importlib.metadata import entry_points
    eps = entry_points(group="console_scripts")
    names = {ep.name: ep.value for ep in eps}
    assert names.get("auntie") == "auntiepypi.cli:main"
    assert names.get("auntiepypi") == "auntiepypi.cli:main"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_cli.py::test_auntie_alias_console_script_registered -v
```

Expected: AssertionError — only `auntiepypi` is registered.

- [ ] **Step 3: Edit `pyproject.toml`**

Change:

```toml
[project.scripts]
auntiepypi = "auntiepypi.cli:main"
```

to:

```toml
[project.scripts]
auntie = "auntiepypi.cli:main"
auntiepypi = "auntiepypi.cli:main"
```

- [ ] **Step 4: Re-install the package so the new entry point is exposed**

```bash
uv sync
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_cli.py::test_auntie_alias_console_script_registered -v
uv run auntie --version
uv run auntiepypi --version
```

Both should print `<prog> <version>`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_cli.py uv.lock
git commit -m "$(cat <<'EOF'
pyproject: register `auntie` console script alongside `auntiepypi`

Both names point at auntiepypi.cli:main. Existing `auntiepypi` muscle
memory and any scripts that hard-coded the old name continue to work.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: systemd-user unit templates + `docs/deploy/`

**Files:**

- Create: `docs/deploy/README.md`
- Create: `docs/deploy/pypi-server.service`
- Create: `docs/deploy/devpi.service`

- [ ] **Step 1: Create `docs/deploy/pypi-server.service`**

```ini
# systemd-user unit template for pypi-server.
#
# Install:
#   mkdir -p ~/.config/systemd/user
#   cp pypi-server.service ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now pypi-server.service
#
# After install, declare it in pyproject.toml so `auntie overview` finds it:
#
#   [[tool.auntiepypi.servers]]
#   name = "main"
#   flavor = "pypiserver"
#   port = 8080
#   managed_by = "systemd-user"
#   unit = "pypi-server.service"
#
# Replace ${PACKAGES_DIR} below with your wheel/sdist storage directory.

[Unit]
Description=pypi-server (auntiepypi managed; v0.3.0 will integrate)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/pypi-server run -p 8080 %h/pypi-packages
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Create `docs/deploy/devpi.service`**

```ini
# systemd-user unit template for devpi-server.
#
# Install:
#   mkdir -p ~/.config/systemd/user
#   cp devpi.service ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now devpi.service
#
# After install, declare it in pyproject.toml so `auntie overview` finds it:
#
#   [[tool.auntiepypi.servers]]
#   name = "dev"
#   flavor = "devpi"
#   port = 3141
#   managed_by = "systemd-user"
#   unit = "devpi.service"

[Unit]
Description=devpi-server (auntiepypi managed; v0.3.0 will integrate)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=%h/.local/bin/devpi-server --host 127.0.0.1 --port 3141
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Create `docs/deploy/README.md`**

```markdown
# auntiepypi — deployment templates

`auntie overview` is **detect-only**: it reports what's running, it does
not raise servers. To run a local PyPI server in the background, use
the systemd-user unit templates in this directory.

## Why systemd-user?

A user-scoped unit needs no root, persists across logins (with
`loginctl enable-linger <user>`), and is what `auntie` v0.3.0 will
integrate with for lifecycle management. Until then, `systemctl --user`
is the recommended supervisor.

## Templates

- [`pypi-server.service`](pypi-server.service) — `pypi-server` on port 8080.
- [`devpi.service`](devpi.service) — `devpi-server` on port 3141.

Both contain inline install + declaration instructions.

## After install

Add a matching `[[tool.auntiepypi.servers]]` block to your project's
`pyproject.toml` so `auntie overview` reports it as `declared`:

    [[tool.auntiepypi.servers]]
    name = "main"
    flavor = "pypiserver"
    port = 8080
    managed_by = "systemd-user"
    unit = "pypi-server.service"

`auntie overview --json | jq` will then show the server with
`source: "declared"` and the `unit` field echoed through.
```

- [ ] **Step 4: Commit**

```bash
git add docs/deploy/
git commit -m "$(cat <<'EOF'
docs/deploy: systemd-user unit templates for pypi-server / devpi

Templates ship as documentation, not code: v0.2.0 is detect-only and
does not raise servers. Inline install instructions plus a matching
[[tool.auntiepypi.servers]] block snippet so `auntie overview` reports
the unit as `declared` with the `unit` field populated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: `docs/about.md`, `README.md`, `CLAUDE.md` refresh

**Files:**

- Modify: `docs/about.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read each file**

```bash
cat docs/about.md
cat README.md
cat CLAUDE.md
```

- [ ] **Step 2: Edit `docs/about.md`**

- Drop any "local noun" mentions (search for "local serve", "local upload", "local mirror").
- After the existing v0.1.0 paragraph, add:

  > ### v0.2.0 — detect, don't supervise
  >
  > `auntie overview` now sees more than just the canonical-port devpi /
  > pypiserver instances: it reads `[[tool.auntiepypi.servers]]` from
  > `pyproject.toml`, fingerprints anything running on port 3141 / 8080,
  > and (with `--proc`) walks `/proc` for matching processes. The CLI
  > binary becomes `auntie` (the longer `auntiepypi` stays as an alias).
  >
  > It deliberately stops at *seeing*. Lifecycle — start, stop, our own
  > PEP 503 server — lands in v0.3.0 under existing top-level verbs (no
  > new noun). For now: declare your servers, let systemd-user supervise
  > them (`docs/deploy/`), and run `auntie overview` to see what's home.

- [ ] **Step 3: Edit `README.md`**

- Replace any `auntiepypi <verb>` examples with `auntie <verb>` (use Edit's `replace_all=true` for `auntiepypi overview`, `auntiepypi packages overview`, `auntiepypi explain`, `auntiepypi learn`, `auntiepypi doctor`, `auntiepypi whoami`).
- Update the status line / opening paragraph to mention v0.2.0's detection upgrade.
- Add a short example block:

  ```text
  $ auntie overview --json | jq '.sections[] | select(.category == "servers")'
  {
    "category": "servers",
    "title": "main",
    "light": "green",
    "fields": [
      {"name": "flavor", "value": "pypiserver"},
      {"name": "port",   "value": "8080"},
      {"name": "status", "value": "up"},
      {"name": "source", "value": "declared"},
      …
    ]
  }
  ```

- [ ] **Step 4: Edit `CLAUDE.md`**

- Status block at the top: replace the v0.1.0 status with a v0.2.0 status describing the detection upgrade and CLI alias.
- "Active verbs and nouns" list: replace any `auntiepypi <verb>` with `auntie <verb>`. Mention the alias.
- Roadmap section:
  - Drop `local` from the list of nouns ("Active verbs and nouns").
  - The "One top-level noun is catalog-known but **not** yet registered" paragraph should be removed entirely (we deleted the `local` catalog entry).
  - In the numbered roadmap:
    - Update v0.2.0 entry to describe the detection work (declared inventory + default-port scan + opt-in /proc + CLI rename).
    - Remove the v0.2.0 reference to "`local` noun" and "`servers` noun" — replace with: v0.3.0 is "serve / lifecycle (verb shape decided in v0.3.0 brainstorm; will not introduce a `local` noun)".

- [ ] **Step 5: Run markdownlint and the portability lint**

```bash
markdownlint-cli2 "docs/about.md" "README.md" "CLAUDE.md" "docs/deploy/README.md"
bash .claude/skills/pr-review/scripts/portability-lint.sh
```

Expected: clean. Fix any issues.

- [ ] **Step 6: Commit**

```bash
git add docs/about.md README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: refresh for v0.2.0 detection + auntie CLI rename

about.md: add v0.2.0 detect-only paragraph. README.md: switch examples
to `auntie ...` and add a `auntie overview --json` server-section
sample. CLAUDE.md: drop `local` noun mentions, update Roadmap (v0.2.0
detection landed; v0.3.0 = serve/lifecycle, no new noun).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Version bump + CHANGELOG entry

**Files:**

- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`

The current version is already `0.2.0` (a published rename PR landed there). This work is a feature addition; bump **minor** to `0.3.0`.

- [ ] **Step 1: Use the vendored `version-bump` skill**

```bash
ls .claude/skills/version-bump
cat .claude/skills/version-bump/SKILL.md | head -30
```

Then run it (it's a slash command in the user's session — they'll invoke it):

In the session, type: `/version-bump minor`

This bumps `pyproject.toml` to `0.3.0` and prepends a `## [0.3.0] - <today>` entry to `CHANGELOG.md` with empty Added/Changed/Fixed sections.

- [ ] **Step 2: Fill in the changelog entry**

Replace the empty `## [0.3.0]` block with:

```markdown
## [0.3.0] - 2026-04-29

### Added

- `auntiepypi/_detect/` — declaration-driven inventory of running PyPI servers. Three detectors (`_declared`, `_port`, `_proc`) plus a runtime that merges them with augment + suppress-absent-when-declared semantics.
- `[[tool.auntiepypi.servers]]` config schema. Per-server `name` / `flavor` / `host` / `port` plus reserved-for-v0.3.0 lifecycle fields (`managed_by`, `unit`, `dockerfile`, `compose`, `service`, `command`).
- `[tool.auntiepypi].scan_processes` boolean (parent-table sibling of `packages`) to opt into the `/proc` scan from config; equivalent to passing `--proc`.
- `auntie overview --proc` flag. Linux-only `/proc` walker that finds `pypi-server` / `devpi-server` processes and ties them to listening ports via `/proc/<pid>/fd/*` + `/proc/net/tcp`.
- `auntie` console script registered alongside `auntiepypi` (both point at `auntiepypi.cli:main`).
- `docs/deploy/` — systemd-user unit templates for pypi-server and devpi-server.

### Changed

- `auntie overview`'s server section group now consumes `_detect.detect_all()` instead of `_probes.probe_status` directly. Declared servers and any extras the augment scan finds appear in the composite report.
- `auntie overview <TARGET>` resolution priority is now: detection name → bare flavor alias → configured package → zero-target.
- `learn`'s `planned` array is now `[]`. The `local` noun (sketched in earlier roadmaps) is permanently dropped; v0.3.0 lifecycle work will land on `doctor` or top-level verbs, not under a noun.

### Notes

- `_probes/` and `doctor --fix` are deliberately untouched. They will be unified with the new serve work in a future milestone.
```

- [ ] **Step 3: Verify the version-check CI gate would pass**

```bash
grep -n "version" pyproject.toml | head -5
grep -n "## \[" CHANGELOG.md | head -5
```

Expected: `pyproject.toml` shows `version = "0.3.0"`; `CHANGELOG.md`'s newest entry is `## [0.3.0]`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "$(cat <<'EOF'
v0.3.0: detection through `auntie overview`

(version-bump skill wrote the version + changelog scaffold; commit
fills in Added/Changed/Notes for the detection work and CLI alias.)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Final verification

- [ ] **Step 1: Run the full quality pipeline**

```bash
uv sync
uv run pytest -n auto --cov=auntiepypi --cov-report=term -v
uv run black --check auntiepypi tests
uv run isort --check-only auntiepypi tests
uv run flake8 auntiepypi tests
uv run pylint --errors-only auntiepypi
uv run bandit -c pyproject.toml -r auntiepypi
markdownlint-cli2 "**/*.md" "#node_modules"
bash .claude/skills/pr-review/scripts/portability-lint.sh
```

Expected: all green; coverage ≥ 95%.

If coverage on `_detect/` is below 95%, add hermetic tests for the missing branches (most likely: `_proc.py` non-Linux short-circuit, malformed `/proc/net/tcp` lines, empty fd dirs).

- [ ] **Step 2: End-to-end smoke**

```bash
uv run auntie --version
uv run auntiepypi --version
uv run auntie overview --json | jq '.sections | group_by(.category) | map({category: .[0].category, count: length})'
uv run auntie overview --proc --json | jq .
uv run auntie overview pypiserver --json | jq .       # bare-flavor alias
uv run auntie overview pypiserver:8080 --json | jq .  # auto-name (may show absent)
uv run auntie explain overview
uv run auntie learn --json | jq '.planned'            # expect []
```

Expected: every command exits 0; `learn --json | jq '.planned'` prints `[]`; `explain overview` mentions `--proc`.

- [ ] **Step 3: Steward sibling-pattern check**

```bash
(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
```

Expected: clean (or with the pre-existing accepted deviations only).

- [ ] **Step 4: Review the diff vs main one last time**

```bash
git log --oneline main..HEAD
git diff main..HEAD --stat
```

Confirm no surprises (no debug prints, no committed `.local.yaml`, no edits to `_probes/` or `doctor.py`).

- [ ] **Step 5: PR via the vendored `pr-review` skill**

In session: `/pr-review` (or use the skill manually per `.claude/skills/pr-review/SKILL.md`).

The skill will branch, push, open a PR, wait for Qodo + Copilot, triage and apply review comments, and resolve threads. The portability-lint and version-check CI jobs will run on push.

---

## Self-Review Notes

**Spec coverage:** every section of the design doc maps to a task —

- §1 statement & scope → reflected in changelog text (task 13) + CLAUDE.md (task 12)
- §2 surface (`auntie overview [TARGET] [--proc] [--json]`) → task 8
- §3 architecture (`_detect/` modules) → tasks 1–7
- §4 config schema → task 2 (with the noted TOML correction)
- §5 JSON envelope → task 1 (`Detection.to_section`)
- §6 catalog/learn/docs → tasks 9, 11, 12
- §7 testing → tasks 1–8 (each task is TDD)
- §8 verification → task 14

**Placeholder scan:** none. Every step has executable code or commands.

**Type consistency:** `Detection`, `ServerSpec`, `ServersConfig`, `ProbeOutcome` defined once and referenced consistently. `detect()` signatures match across `_declared`, `_port`, `_proc` (all take `declared`, `*, scan_processes`; `_port` adds `covered`, `_proc` adds `proc_root`). Runtime calls each via the renamed import (`_declared_detect`, `_port_detect`, `_proc_detect`) so test monkeypatching can target the runtime module's bindings.

**Spec drift documented:** the TOML coexistence claim in §4 of the spec is corrected in this plan (scalar `scan_processes` lives on `[tool.auntiepypi]`, not on `[tool.auntiepypi.servers]`). Surface and behavior are unchanged from the user's intent.
