# auntiepypi v0.2.0 — `auntie overview` detection design

**Status:** approved 2026-04-29 via brainstorming session. This document
is the project-side spec; if a planning artifact written elsewhere drifts,
this file wins.

## Statement of purpose

> v0.2.0 expands `auntie overview` so its **servers** section reflects
> everything visible to the local box — declared in config, found on a
> default port, or (opt-in) found by scanning `/proc`. No new nouns and
> no new verbs are added. v0.2.0 is read-only and detect-only: it does
> not start, stop, supervise, or own any server lifecycle.

The `local` noun (sketched in earlier roadmaps) and a `servers` noun
(sketched mid-brainstorm) are both **explicitly dropped**. Future work
for serve / lifecycle lands on `doctor` or as a top-level verb in v0.3.0
— not under a noun. `doctor --fix` keeps shipping unchanged through
v0.2.0; v0.3.0 unifies `doctor`'s raise capability with the new serve
work and is a separate brainstorm.

The CLI binary renames `auntiepypi` → `auntie`. The Python package and
import path remain `auntiepypi` (the PyPI rename landed in #4).
`auntiepypi` stays registered as a console-script alias so existing
muscle memory and scripts keep working.

## Context

v0.0.1 shipped `_probes/` (uniform interface for one PyPI server flavor:
`devpi` on 3141, `pypiserver` on 8080) and `doctor --fix`, which shells
out to each probe's `start_command` and re-probes.

v0.1.0 shipped the `packages` noun and promoted `auntie overview` to a
composite of packages + servers section groups, where the servers group
came from `_probes/`.

v0.2.0 introduces a parallel `_detect/` module that produces a wider,
declaration-driven inventory of running PyPI servers, and switches the
composite `auntie overview` server section group to consume it.
`_probes/` and `doctor --fix` are deliberately untouched.

## Brainstorm decisions (machine-readable)

| Question | Decision |
|---|---|
| Scope of v0.2.0 | Detect-only; no raise/start/stop verbs |
| Fate of `doctor --fix` | Untouched in v0.2.0; unified with serve work in v0.3.0 |
| Fate of `local` noun | Dropped permanently — no `local` noun ever |
| Fate of `servers` noun | Dropped — no new noun in v0.2.0; detection surfaces via `auntie overview` |
| Architecture | Parallel `_detect/` module; `_probes/` left untouched |
| Detection breadth | Declared-inventory + default port-scan; `/proc` scan opt-in |
| Detector layout | Plug-in modules under `_detect/` (mirrors `_probes/` and `_rubric/`) |
| Detection mode | Augment (declared + default scan), suppress `absent` from scan when declarations exist |
| CLI binary name | Rename `auntiepypi` → `auntie`; both registered as console scripts |
| Python import path | Unchanged — `auntiepypi.*` |
| systemd unit template | Documentation-only in `docs/deploy/`; runtime points users at it as remediation |

## Surface

```text
auntie overview [TARGET] [--proc] [--json]
auntie explain <path> [--json]                  # unchanged
auntie learn [--json]                           # unchanged (planned[] becomes [])
auntie doctor [--fix] [--json]                  # unchanged from v0.1.0
auntie packages overview [PKG] [--json]         # unchanged from v0.1.0
auntie whoami [--json]                          # unchanged from v0.1.0
```

### `auntie overview` (no arg)

Composite. Emits:

- A `category: "packages"` section group — same content as v0.1.0
  (rolled-up dashboard from `[tool.auntiepypi].packages`).
- A `category: "servers"` section group — one section per detection
  produced by `_detect/.detect_all()`. Order: declared first (in
  declaration order), then default-port detections, then `--proc` finds.

### `auntie overview <TARGET>`

Drill-down. `<TARGET>` resolves in this priority order:

1. **Exact detection name** — declared `name`, or auto-name
   `<flavor>:<port>` (e.g. `pypiserver:8080`).
2. **Bare flavor alias** — `pypiserver` / `devpi` matches the *first*
   detection of that flavor. Preserves v0.0.1's
   `auntie overview pypiserver` muscle memory.
3. **Configured package** — delegates to `packages overview <pkg>`.
4. **Zero-target** — stderr warning + exit `0` (preserves v0.0.1
   semantics for unknown TARGET).

### `--proc`

Opt-in `/proc` scan. Linux-only; on macOS or BSD the flag is accepted
but the proc detector is a no-op and emits a stderr note. Also exposed
as `[tool.auntiepypi.servers].scan_processes = true` for users who want
it always on.

### Filtering by category

There is **no** `--only=servers` / `--only=packages` flag. The composite
is composite. Consumers who want one slice use `jq`:

```bash
auntie overview --json | jq '.sections[] | select(.category=="servers")'
```

### Exit codes (consistent with v0.0.1 / v0.1.0)

- `0` — detection completed; `down` / `absent` results do **not** change
  the exit (informational, not gating).
- `1` — malformed `[[tool.auntiepypi.servers]]` (duplicate `name`,
  missing `port`, invalid `flavor`, etc.).
- `2` — every detector failed to run at all (e.g. `/proc` unreadable
  *and* every default-port scan timed out *and* every declared probe
  raised). JSON envelope still emitted on stdout; warnings on stderr.

Unknown `<TARGET>` stays at exit `0` with a stderr warning, matching
v0.0.1.

## JSON envelope

Same shape v0.1.0 established. Detections become `category: "servers"`
sections with a richer field set. Existing v0.1.0 consumers keep
working: changes are field *additions*; old fields keep their meaning.

```json
{
  "subject": "auntie",
  "sections": [
    {
      "category": "packages",
      "title": "...",
      "light": "...",
      "fields": [...]
    },
    {
      "category": "servers",
      "title": "main",
      "light": "green",
      "fields": [
        {"name": "flavor",      "value": "pypiserver"},
        {"name": "host",        "value": "127.0.0.1"},
        {"name": "port",        "value": "8080"},
        {"name": "url",         "value": "http://127.0.0.1:8080/"},
        {"name": "status",      "value": "up"},
        {"name": "source",      "value": "declared"},
        {"name": "managed_by",  "value": "systemd-user"}
      ]
    }
  ]
}
```

Light: `up → green`, `down → red`, `absent → unknown`.

Optional fields (`pid`, `cmdline`, `detail`, and reserved-for-v0.3.0
declaration metadata: `unit`, `dockerfile`, `compose`, `service`,
`command`) are appended only when populated. Null values are elided so
v0.2.0 consumers don't drown in nulls.

## Architecture

```text
auntiepypi/
├── _probes/                     # UNCHANGED — used only by `doctor --fix`
└── _detect/
    ├── __init__.py              # DETECTORS = (declared, port, proc); detect_all()
    ├── _detection.py            # frozen @dataclass Detection; Source enum
    ├── _runtime.py              # detect_all(): merge + augment + suppress-absent-when-declared
    ├── _config.py               # load_servers() reads [[tool.auntiepypi.servers]]
    ├── _declared.py             # detector: probe each declared entry
    ├── _port.py                 # detector: scan DEFAULT_PORTS = (3141, 8080)
    └── _proc.py                 # detector: /proc scan; opt-in; Linux-only; no-op elsewhere
```

`cli/_commands/overview.py` swaps its server-section call site from
`_probes/.probe_status` to `_detect/.detect_all`.
`cli/_commands/doctor.py` is **untouched**.

### Detector protocol

Each detector module exposes a single function:

```python
def detect(declared: list[ServerSpec], opts: DetectOpts) -> list[Detection]: ...
```

`_runtime.detect_all()` is the only entry point for callers. Order of
operations:

1. Run `_declared.detect()` first. Build
   `covered = {(d.host, d.port) for d in result}`.
2. Run `_port.detect()` over `DEFAULT_PORTS - covered`. If `declared`
   was non-empty, drop entries with `status == "absent"` from the port
   detector's output. (Augment + suppress-absent.)
3. If `opts.scan_processes`: run `_proc.detect()`. Merge by
   `(host, port)` — proc-found PIDs enrich existing detections;
   proc-only detections are appended.

Adding a future detector (Docker socket, container runtime queries, …)
is one new file plus one entry in `_detect/__init__.DETECTORS` —
exactly the pattern `_probes/` and `_rubric/` already use.

### `Detection` dataclass

```python
@dataclass(frozen=True)
class Detection:
    name: str                    # declared `name` or auto-name "<flavor>:<port>"
    flavor: str                  # "pypiserver" | "devpi" | "unknown"
    host: str
    port: int
    url: str
    status: str                  # "up" | "down" | "absent"
    source: str                  # "declared" | "port" | "proc"
    pid: int | None = None
    cmdline: str | None = None
    detail: str | None = None
    # Reserved declaration metadata (echoed verbatim; v0.2.0 does not act on it)
    managed_by: str | None = None
    unit: str | None = None
    dockerfile: str | None = None
    compose: str | None = None
    service: str | None = None
    command: tuple[str, ...] | None = None
```

## Configuration

```toml
[tool.auntiepypi]
packages = ["afi-cli", "shushu", "ghafi", "steward", "auntiepypi"]   # v0.1.0; unchanged

[[tool.auntiepypi.servers]]                                          # NEW — array of tables
name      = "main"             # required, unique within the array
flavor    = "pypiserver"       # required: "pypiserver" | "devpi" | "unknown"
host      = "127.0.0.1"        # default
port      = 8080               # required
# Reserved for v0.3.0 lifecycle. v0.2.0 echoes them in --json output but
# never acts on them. Loader validates "exactly one of {unit, dockerfile,
# compose, command} OR managed_by = 'manual'".
managed_by  = "systemd-user"   # "systemd-user" | "docker" | "compose" | "command" | "manual"
unit        = "pypi.service"
dockerfile  = "./infra/pypi/Dockerfile"
compose     = "./infra/pypi/docker-compose.yml"
service     = "pypi"
command     = ["pypi-server", "run", "-p", "8080", "/srv/wheels"]

[tool.auntiepypi.servers]                                            # singleton table
scan_processes = false         # default; --proc CLI flag overrides to true
```

The array-of-tables (`[[tool.auntiepypi.servers]]`) and the scalar
table (`[tool.auntiepypi.servers]`) coexist — `tomllib` parses the
scalar table's keys onto a dict adjacent to the array. The loader
handles both.

`_config.py` validates: `name` unique, `port` in `1..65535`, `flavor`
in the closed set `{"pypiserver", "devpi", "unknown"}`, `managed_by` in
`{"systemd-user", "docker", "compose", "command", "manual", null}`. On
violation: exit `1` with the failed key on stderr and a `hint:` line
pointing to this spec.

The dashboard / overview surface does **not** require
`[[tool.auntiepypi.servers]]` to be set: with no declarations, the
default port scan still runs and detection works for vanilla setups.

## Detection policy

- **Stdlib only.** `socket`, `urllib.request`, `urllib.error`,
  `concurrent.futures`. No `psutil`, no `requests`, no `httpx`.
- **Per-fetch:** 1 s timeout (TCP) + 1 s timeout (HTTP). No retries.
  Custom UA: `auntie/<__version__>`.
- **Concurrency:** declared probes and default-port probes fan out via
  `ThreadPoolExecutor(max_workers=8)`; `_proc.detect()` runs on the
  main thread (it's filesystem reads, not network).
- **No on-disk cache.** Detection against ~5 declared servers + 2
  default ports completes well under 200 ms when localhost is healthy.

### Flavor fingerprint

| HTTP signature on probe | Flavor |
|---|---|
| 200 + JSON body containing the key `"resources"` (devpi `/+api`) | `devpi` |
| 200 + HTML body matching `<a href=".+/">.+</a>` (PEP 503 simple) | `pypiserver` |
| 200 + valid PEP 503 simple-index but no pypiserver tell | `unknown` |
| anything else | the declaration's stated flavor (declarations are trusted), or `unknown` for scan-found |

### Failure mapping

| Failure | Maps to |
|---|---|
| TCP refused / `ECONNREFUSED` | `status = "absent"` |
| TCP timeout | `status = "absent"` with `detail = "tcp timeout"` |
| HTTP 5xx | `status = "down"` with `detail = "http <code>"` |
| HTTP timeout after TCP open | `status = "down"` with `detail = "http timeout"` |
| HTTP 200 but flavor fingerprint doesn't match declared flavor | `status = "down"` with `detail = "flavor mismatch: expected X, saw Y"` |
| `/proc` not readable (non-Linux, sandboxed, …) | `_proc.detect()` returns `[]`; stderr note |
| Every detector raised | exit `2`, "env error: no detector succeeded"; JSON envelope still emitted |

### stderr / stdout

Same split as v0.1.0: structured payload (text or JSON) on stdout;
human-readable warnings on stderr. An agent piping to `jq` never sees
the warnings.

## Testing

### Layer 1 — Hermetic (PR-blocking, default)

- **`tests/test_detect_declared.py`** — TOML loading + validation
  (duplicate name, bad port, missing flavor, unknown `managed_by`);
  per-declaration probing.
- **`tests/test_detect_port.py`** — `http.server.ThreadingHTTPServer`
  on localhost ephemeral ports (same pattern v0.0.1's
  `_probes/` tests use); flavor fingerprinting (devpi JSON; pypiserver
  HTML; bare simple-index → `unknown`); covers TCP refused / TCP
  timeout / HTTP 5xx / HTTP 200-but-wrong-flavor.
- **`tests/test_detect_proc.py`** —
  `@pytest.mark.skipif(sys.platform != "linux")`. Monkey-patch
  `_proc_root` to a temp dir with mock
  `/proc/<pid>/{comm,cmdline,net/tcp}`. Covers happy path, unreadable
  `/proc`, no matches, multiple matches.
- **`tests/test_detect_runtime.py`** — pure merge logic. Empty
  declarations + default scan; declarations + scan with port collision;
  declarations + scan with extras; augment + suppress-absent; `--proc`
  enrichment (proc PID merged onto port-found detection) vs proc-only
  finds.
- **`tests/test_cli_overview_composite.py`** — UPDATED from v0.1.0:
  composite uses `_detect/`; declared servers appear under
  `category: "servers"` with the richer field set; `--proc` plumbed
  through; bare-flavor alias still resolves; `<NAME>:<port>` auto-name
  resolves; unknown TARGET → exit `0` with stderr warning.

No new `tests/test_cli_servers.py` — there is no `servers` verb.

### Layer 2 — Live network

Not applicable. Detection is purely local; no third-party servers are
contacted. `@pytest.mark.live` continues to gate v0.1.0's PyPI /
pypistats tests; v0.2.0 adds nothing to that surface.

### Coverage

Stays at **95%** on the `auntiepypi/` package. The new `_detect/` code
is structured for hermetic coverage: detectors are pure functions over
fixtures or localhost servers; `_runtime.detect_all()` is pure merge
logic.

### CI scheduling

Unchanged from v0.1.0. The hermetic suite blocks PRs and `main`; the
live suite (PyPI / pypistats from v0.1.0) keeps its existing schedule.

## Catalog, learn, docs

- **`auntiepypi/explain/catalog.py`** — **delete** the `("local",)`
  entry; **do not** add a `("servers",)` entry. Update `("overview",)`:
  describe detection behavior, declaration-driven inventory, `--proc`,
  target resolution priority; add a one-liner pointing at
  `docs/deploy/`. Update root entry: drop `local` from Planned; drop
  the `auntiepypi explain local` See-also; refresh CLI examples to
  `auntie`.
- **`auntiepypi/cli/_commands/learn.py`** — delete `_M_LOCAL` and
  `_M_SERVERS`. The JSON `planned[]` becomes `[]` in v0.2.0. Verbs
  section: refresh `overview`'s description to mention
  detection-driven servers and `--proc`.
- **`pyproject.toml`** — `[project.scripts]` registers both `auntie`
  and `auntiepypi`, both → `auntiepypi.cli:main`.
- **`CLAUDE.md`** — Status line moves to v0.2.0; Roadmap drops the
  `local` noun line; v0.3.0 entry says "serve / lifecycle (under
  `doctor` or top-level — verb shape TBD; no new noun)". CLI examples
  through the file change `auntiepypi` → `auntie`.
- **`README.md`** — status line → v0.2.0; example block shows
  `auntie overview` output with declared servers visible. CLI examples
  use `auntie`.
- **`CHANGELOG.md`** — `## [0.2.0]` block written at PR time by the
  `version-bump` skill — note the CLI rename + the
  `[[tool.auntiepypi.servers]]` config addition.
- **`docs/about.md`** — drop any `local`-noun mentions; add a paragraph
  on the detect-only philosophy ("we report; you (or systemd)
  supervise").
- **NEW `docs/deploy/`** — two systemd-user unit templates
  (`pypi-server.service`, `devpi.service`) plus a one-page README. The
  `_detect/` runtime points users here as remediation when
  `status == "absent"`.
- **`culture.yaml`** — unchanged. Mesh metadata does not depend on CLI
  surface.

## Roadmap follow-ons (out of scope here)

- **v0.3.0** — serve / lifecycle. Brings in the ability to actually
  start and stop a PyPI server (or run our own). Verb shape is decided
  in v0.3.0's brainstorm: most likely either expanding `doctor` (`doctor
  --start`, `doctor --serve`) or a new top-level verb (`auntie serve`).
  Will *not* introduce a `local` noun. v0.3.0 unifies `doctor --fix`'s
  raise capability with the new serve work and resolves the v0.2.0
  redundancy where `_probes/` and `_detect/` both exist.
- **v0.3.x+** — additional detectors as needed: Docker socket /
  container introspection, systemd-user unit listing
  (`systemctl --user list-units 'pypi*'`), launchd on macOS. Each
  lands as one file under `_detect/` plus one entry in
  `_detect/__init__.DETECTORS`.
- **v1.0.0** — mesh-aware. Local index discoverable via Culture-mesh
  service registry; trust boundary documented in
  `docs/threat-model.md`.

## Verification

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

uv run auntie --version
uv run auntiepypi --version             # alias still works
uv run auntie overview --json | jq '.sections | group_by(.category) | map({category: .[0].category, count: length})'
uv run auntie overview --proc --json | jq .
uv run auntie overview main --json | jq .                # declared name (if configured)
uv run auntie overview pypiserver --json | jq .          # bare-flavor alias
uv run auntie overview pypiserver:8080 --json | jq .     # explicit auto-name
uv run auntie explain overview
uv run auntie learn --json | jq '.planned'               # expect []

(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
```
