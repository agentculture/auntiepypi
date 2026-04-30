# auntiepypi v0.6.0 — first-party PEP 503 simple-index server

**Status:** approved 2026-05-01
**Implements:** the bare form of `auntie up` / `down` / `restart` reserved by v0.5.0
**Related specs:**
[v0.5.0 lifecycle verbs](2026-04-30-auntiepypi-v0.5.0-lifecycle-verbs-design.md),
[v0.4.0 doctor lifecycle](2026-04-30-auntiepypi-v0.4.0-doctor-lifecycle-design.md)

## Context

v0.5.0 wired three lifecycle verbs against declared third-party servers
(`systemd-user`, `command`) but reserved the **bare** form
(`auntie up` with no target and no `--all`) for v0.6.0.
`_lifecycle.py:173` raises:

> "auntie {verb}: the first-party auntie server lands in v0.6.0; for now
> use `auntie {verb} <name>` or `auntie {verb} --all`"

This spec fills that reservation: a stdlib-only PEP 503 simple-index
server that auntie owns end-to-end, plugged into the existing
`_actions` × `_detect` machinery as a third managed_by strategy
("auntie"), with bare-form CLI semantics that synthesize a
Detection + ServerSpec from `[tool.auntiepypi.local]` and dispatch
through the same code path as `command` and `systemd-user`.

This is the **read-only slice**. `auntie publish`, HTTPS, basic-auth,
and the mesh-aware service registry are out of scope (see "Out of
scope" below). Loopback-only binding (127.0.0.1) is the v0.6.0 trust
model: the missing auth is not a foot-gun because the server is not
reachable off-host. Public binding requires the deferred auth work
and is rejected at config-load time in v0.6.0.

## Locked design decisions

### D1. Read-only slice

v0.6.0 ships **only** the read side of a PEP 503 index:

- `GET /simple/` — HTML anchor list of project names found in the
  wheelhouse.
- `GET /simple/<pkg>/` — HTML anchor list of distribution files
  (wheels + sdists) for `<pkg>` after PEP 503 name normalization;
  404 when the project has no dists.
- `GET /files/<filename>` — `application/octet-stream` body of the
  file; 404 when missing or path-traversal-rejected.

No `auntie publish`. No HTTPS. No basic-auth. No write side.
Loopback-only binding so missing auth is not exploitable from the
network.

**Why:** the v0.5.0 brainstorm validated the small-landable-PR pattern
(option A every time). A full-bundle v0.6.0 (read + publish +
HTTPS + auth) would multiply the testing surface and stretch the PR
beyond reviewable size. Read-only is the smallest slice that fills
the bare-form reservation. Publish, HTTPS, and auth get their own
patch versions.

### D2. `auntie` is a third managed_by strategy

`_actions/__init__.py:ACTIONS` gains an `"auntie"` entry alongside
`"systemd-user"` and `"command"`. The bare-form CLI synthesizes:

```python
spec = ServerSpec(
    name="auntie",
    flavor="auntiepypi",
    host=cfg.host,
    port=cfg.port,
    managed_by="auntie",
)
```

…and dispatches through the existing `_actions.dispatch("start" | "stop"
| "restart", detection, spec)` machinery. The strategy module
`_actions/auntie.py` mirrors `_actions/command.py` (Popen → `_pid` →
`_reprobe`) but with a derived argv:

```python
argv = [
    sys.executable,
    "-m", "auntiepypi._server",
    "--host", cfg.host,
    "--port", str(cfg.port),
    "--root", str(cfg.root),
]
```

PID + sidecar live at `state_root() / "auntie_<port>.pid"` (and
`.json`), reusing the v0.5.0 port-disambiguated convention.

**Why over alternatives:**

- **vs. special-cased bare-form short-circuit**: dispatching through the
  existing strategy table means `_actions.dispatch` stays the single
  source of truth for "how do I act on a managed server." Adding a
  bypass would split the model.
- **vs. synthesizing managed_by="command"** with an internal argv:
  blurs the boundary. The first-party server is a *first-class
  feature*, not "a command we happen to invoke." A dedicated
  `_actions/auntie.py` keeps the defaults, config, and argv logic
  together.

### D3. stdlib `http.server` + `ThreadingHTTPServer`

No external runtime deps (consistent with the AgentCulture sibling
pattern). PEP 503 minimum surface is two GET routes; filename parsing
is stdlib regex; PEP 503 name normalization is `re.sub` on the
canonicalized form.

`ThreadingHTTPServer` (stdlib `http.server`) gives concurrent reads
without an event loop. Connection volume is bounded (mesh-internal,
agents-only); thread-per-request is appropriate.

### D4. Filesystem-walk wheelhouse

Default root: `$XDG_DATA_HOME/auntiepypi/wheels/` (override via
`[tool.auntiepypi.local].root`).

Each `/simple/<pkg>/` request walks the directory directly:

```python
def list_projects(root: Path) -> dict[str, list[Path]]:
    """{normalized_name: [paths]} for all dist files in root."""
```

No index file. No cache. No write-side concerns. Adding wheels means
"drop them into the directory"; removing means "delete the file."
Because there is no write side in v0.6.0, the absence of an index
isn't a coordination problem.

Filename parsing follows PEP 427 (wheels) and PEP 625 (sdists,
`.tar.gz` and `.zip`). Names extracted from filenames are normalized
per PEP 503 (`re.sub(r"[-_.]+", "-", name).lower()`).

### D5. Bare form is privileged; `--all` includes the local server

CLI semantics:

| Invocation                     | Acts on                                   |
|--------------------------------|-------------------------------------------|
| `auntie up`                    | first-party server only                   |
| `auntie up --all`              | local server + every supervised declared  |
| `auntie up <name>`             | one declared server (unchanged from v0.5) |
| `auntie up auntie`             | error: name reserved                      |

The local server is **always** supervised (managed_by="auntie" is in
`SUPERVISED_MODES`), so `--all` always picks it up. The local pair is
inserted **first** in the dispatch list so a failed declared start
doesn't shadow the local result.

Reserved name: `"auntie"` cannot be used as the `name` of any
`[[tool.auntiepypi.servers]]` entry. Detected at config-load time;
raises `AfiError(EXIT_USER_ERROR)` with a remediation pointing at the
conflict.

## Architecture

### File layout

```text
auntiepypi/_server/                # NEW package
├── __init__.py                    # public surface; serve(host, port, root)
├── __main__.py                    # `python -m auntiepypi._server` entry
├── _app.py                        # BaseHTTPRequestHandler + routes
├── _wheelhouse.py                 # filesystem walk + filename parsing
└── _config.py                     # LocalConfig dataclass + defaults

auntiepypi/_actions/
├── __init__.py                    # ACTIONS["auntie"] registered
└── auntie.py                      # NEW: spawn → _pid → _reprobe

auntiepypi/_detect/
├── _config.py                     # MODIFY: load_local_config()
├── _local.py                      # NEW: probe the first-party server
└── _runtime.py                    # MODIFY: chain _local first

auntiepypi/cli/_commands/
├── _lifecycle.py                  # MODIFY: bare → local pair dispatch
└── overview.py                    # MODIFY: surface local section

auntiepypi/explain/catalog.py      # MODIFY: bare-form docs
```

### `[tool.auntiepypi.local]` config block

```toml
[tool.auntiepypi.local]
host = "127.0.0.1"   # default; non-loopback rejected in v0.6.0
port = 3141          # default; conflict → user override
root = "~/.local/share/auntiepypi/wheels"  # default; XDG_DATA_HOME aware
```

`LocalConfig` (frozen dataclass), all fields defaulted:

```python
@dataclass(frozen=True)
class LocalConfig:
    host: str = "127.0.0.1"
    port: int = 3141
    root: Path = field(default_factory=default_root)
```

`load_local_config(start: Path | None = None) -> LocalConfig`:

- Walks to `pyproject.toml` (same logic as
  `load_servers_lenient`).
- Reads `[tool.auntiepypi.local]`; absent table → defaults.
- Validates: `port` is `int` 1–65535; `host` is loopback (IPv4
  127.0.0.0/8 or IPv6 `::1`); `root` expands `~`.
- Non-loopback host → `AfiError(EXIT_USER_ERROR)` with v0.7.0
  forward-pointer.

### Dispatch flow (bare-form `auntie up`)

```text
auntie up                              (CLI parse)
  → _lifecycle.run_lifecycle(target=None, all_servers=False)
  → _local_pair()
      → load_local_config()
      → Detection(name="auntie", source="local", ...)
      → ServerSpec(name="auntie", managed_by="auntie", ...)
  → _actions.dispatch("start", detection, spec)
      → ACTIONS["auntie"]["start"](detection, spec)
      → auntie.start():
          - argv = [python, -m, auntiepypi._server, --host, --port, --root]
          - Popen(argv, start_new_session=True, stdout=log)
          - _pid.write("auntie", pid=..., argv=..., port=...)
          - probe(detection, desired="up", budget_seconds=5.0)
          - return ActionResult(ok=True, detail="started", pid=...)
  → emit_result({"verb": "up", "results": [{"name": "auntie", "ok": ...}]})
```

### Detection wiring

`_detect/_runtime.detect_all()` order, after v0.6.0:

1. `_local.detect(config)` → first-party server (always one record)
2. `_declared.detect(config, covered)` → user-declared servers,
   skipping the local endpoint
3. `_port.detect(covered)` → default-port scan, skipping `covered`
4. `_proc.detect(covered)` → `/proc` walker (opt-in)

The local detection's `(host, port)` enters `covered` so the port
scanner doesn't re-discover it as `devpi` on 3141.

`Detection.source` gains the value `"local"` (alongside `"declared"`,
`"port"`, `"proc"`). `Detection.to_section()` already renders any
source value.

### `auntie overview` integration

The local server appears as a regular detection block with
`source="local"` and `flavor="auntiepypi"`:

```text
servers:
  auntie@127.0.0.1:3141 up (auntiepypi/local)
    pid 12345 (sidecar 2026-05-01T10:23:45+00:00)
    log: ~/.local/state/auntiepypi/auntie_3141.log
  pypiserver-stage@10.0.0.5:8080 up (pypiserver/declared)
```

JSON section: a regular `Detection` JSON dict with `source: "local"`.

## CLI shape after v0.6.0

```text
auntie up                          start the first-party server
auntie down                        stop the first-party server
auntie restart                     restart the first-party server
auntie up <name>                   unchanged from v0.5.0
auntie up --all                    declared supervised + local server
auntie overview                    composite (packages + servers + local)
```

Exit codes unchanged from v0.5.0:
0 = all targets reached desired state, 2 = action attempted but
failed, 1 = user/config error before any action attempted.

## Out of scope (deferred to v0.6.x or v0.7.0)

- **`auntie publish` upload path.** Write side of the mesh-private
  index. Likely a separate verb that writes to `cfg.root`. v0.6.1 or
  v0.7.0.
- **HTTPS termination.** Requires a `[tool.auntiepypi.local].cert` /
  `.key` pair (or self-signed via Python `ssl.SSLContext.load_cert_chain`).
  Pairs naturally with public-binding, deferred together. v0.7.0.
- **Basic auth (and tokens).** Loopback-only is the v0.6.0 trust
  model; auth lifts the loopback restriction. v0.7.0.
- **Mesh-aware service registry.** The local server's
  `(host, port)` discoverable via Culture-mesh service registry;
  cross-machine pulls. v1.0.0 (sketched in CLAUDE.md roadmap).
- **Multiple wheelhouses.** Single root in v0.6.0. Multi-root
  layering (think devpi user/index) is post-v1.0.

## Threat model (v0.6.0 only)

The v0.6.0 server is **not internet-exposed**. The
`load_local_config` validator rejects non-loopback hosts, so the
attack surface is limited to processes on the same host. The
following remain possible and are accepted:

- A local user other than the auntie operator can read the wheelhouse
  by hitting `http://127.0.0.1:3141/`. **Mitigation:** wheelhouse
  contents are presumed-public; private content shouldn't live there.
- Path traversal in `/files/<filename>` could expose files outside
  the wheelhouse if the guard is wrong. **Mitigation:** explicit
  resolved-path-must-be-inside-root check; tests cover `..`,
  absolute paths, symlink escapes; bandit gates the PR.
- A local user can spam GET requests against the server. **Mitigation:**
  not addressed in v0.6.0; mesh-internal traffic only.

When v0.7.0 introduces auth + TLS, the threat model expands to
"public network" and these mitigations get formalized.

## Compat notes

- The reserved name `"auntie"` is rejected if used as a declared
  server name. Existing siblings should not have collided (the name
  is new), but if a user did pick it, they get a clear error pointing
  at the rename.
- Default port 3141 collides with running devpi instances. The
  detection-layer `covered` set prevents `auntie overview` from
  reporting both, but a hard bind conflict on `start` is a real
  failure. The error message points at
  `[tool.auntiepypi.local].port` for override.
- The bare-form forward-pointer message in
  `_lifecycle._bare_invocation_message` becomes dead code and is
  deleted. Tests that exercised the exit-1 path are updated to
  expect dispatch.

## Verification

The plan's "Verification" section (`$CLAUDE_HOME/plans/dazzling-snacking-kay.md`)
covers the smoke-test flow:

1. Bare-form lifecycle (`up` / `down` / `restart`) on a stock
   wheelhouse.
2. Wheelhouse round-trip (drop a wheel, `pip install --index-url`).
3. `--all` aggregates local + declared.
4. `auntie overview` surfaces the local section in both text and
   JSON.

Quality pipeline (same gauntlet v0.5.0 passed):

- `pytest -n auto --cov=auntiepypi`, coverage ≥ 94%
- `black`, `isort`, `flake8`, `pylint --errors-only`, `bandit`
- `markdownlint-cli2`
- `bash .claude/skills/pr-review/scripts/portability-lint.sh`

Expected SonarCloud findings (and resolutions):

- `python:S5332` (HTTP-without-TLS hotspot) on
  `_server/_app.py` and `_lifecycle.py:_local_pair`. Resolution:
  NOSONAR with comment linking to the v0.7.0 deferred-auth section
  (mirrors v0.5.0 treatment).
- No new code smells expected; cognitive-complexity budgets
  preserved by keeping `_app.py` route handlers thin.
