# auntiepypi v0.1.0 — `packages overview` design

**Status:** approved 2026-04-29 via brainstorming session. This document
is the project-side spec; if a planning artifact written elsewhere drifts,
this file wins.

## Statement of purpose

> auntiepypi is both a CLI and an agent that maintains, uses, and serves
> the CLI for managing PyPI packages. It supports remote (pypi.org) today
> and local (mesh-hosted) indexes in future milestones. It **overviews**
> packages — informational, not gating.

"Not gating" is a design constraint, not marketing copy:

- Exit code is `0` regardless of how many packages roll up red.
- The verb is `overview`, not `audit` / `check` / `verify`.
- No `--strict`, no `--fail-on=red`, no CI-killer flags. Ever.

If a future use case needs gating, that is a separate verb under a
separate noun; do not shoehorn it under `packages overview`.

## Context

v0.0.1 shipped the AgentCulture sibling skeleton: five flat verbs
(`learn`, `explain`, `overview`, `doctor`, `whoami`), the `_probes/`
plugin point for local PyPI server flavors, the full quality pipeline,
and the agent-affordance plumbing (catalog, JSON envelopes, exit-code
policy).

v0.1.0 introduces the first **noun**: `packages`. Two surfaces land:

- `auntiepypi packages overview [PKG]` — read-only multi-package roll-up
  (no arg) or per-package deep-dive (with arg) against pypi.org's public
  JSON API plus pypistats.org for download counts.
- `auntiepypi overview` is **promoted** to a composite: it now emits both
  a `packages` section group and the existing `servers` section group
  (the v0.0.1 server-flavor probes), with each section tagged by
  `category`.

`local` (v0.2.0) and release-orchestration verbs (deferred) are out of
scope for this PR.

## Brainstorm decisions (machine-readable)

| Question | Decision |
|---|---|
| Single milestone vs both nouns | `online` only (renamed `packages`); `local` deferred to v0.2.0 |
| Source of truth for "my packages" | Static list of strings in `pyproject.toml` `[tool.auntiepypi].packages` |
| Read-only vs release-trigger in v0.1.0 | Read-only only; releases stay in sibling repos |
| Maturity rubric | 7 dimensions, traffic-light roll-up (see §Rubric) |
| Verb shape | One verb `packages overview [PKG]`, double-meaning by arg presence |
| Architecture pattern | Per-dimension plugin under `_rubric/`, parallels `_probes/` |
| Live tests | `@pytest.mark.live` against stable third-party packages; CI = soft on PR + blocking on `main` |
| Coverage gate | 95% on the `auntiepypi/` package, with documented `pragma: no cover` allowlist |
| Pre/post-deploy checks | Smoke jobs in `publish.yml`: build-and-run before upload; install-and-run after upload |
| `auntiepypi overview` shape | Composite of `packages` + `servers` sections, tagged by `category` key |

## Surface

```text
auntiepypi packages overview [PKG] [--json]
auntiepypi overview [TARGET] [--json]            # composite, promoted
```

### `auntiepypi packages overview` (no arg)

Roll-up over `pyproject.toml [tool.auntiepypi].packages`. One section per
package. Each row carries: name, current version, traffic light, days
since last release, last-week download count, and the `index` value
(always `"pypi.org"` in v0.1.0; reserved for local index URLs in v0.2.0).

Empty list or missing key → exit `1` with `error: no
[tool.auntiepypi].packages` on stderr and a `hint:` pointing to the config
block.

### `auntiepypi packages overview <pkg>`

Deep-dive on a single package. One section per rubric dimension plus a
final `_summary` section carrying the rolled-up traffic light. Invalid
package name (per PEP 508) → exit `1`. Unknown-to-PyPI package → exit
`0` with the section's `light: unknown` and reason on stderr.

### `auntiepypi overview` (composite, promoted)

No arg → emits sections of mixed `category`:

- `packages` sections — same content as `packages overview` no-arg, one
  per configured package.
- `servers` sections — same content as v0.0.1 today, one per known
  flavor in `_probes/`.

With arg `<TARGET>` resolves in this priority order:

1. `TARGET` matches a known server flavor (`devpi`, `pypiserver`, …) →
   delegate to existing v0.0.1 single-flavor probe.
2. `TARGET` matches a configured package name → delegate to
   `packages overview <pkg>`.
3. Otherwise → zero-target stderr warning + exit `0` (existing v0.0.1
   semantics for unknown TARGET).

Server-flavor wins on the unlikely name collision.

### Exit codes (consistent with v0.0.1)

- `0` — fetch completed; rolled-up reds do not change the exit.
- `1` — user-input error (missing/empty `[tool.auntiepypi.packages]`
  table; invalid PEP 508 name; unknown flag).
- `2` — env error: every fetch raised. JSON envelope still emitted on
  stdout; warnings on stderr.

## JSON envelope

Same shape v0.0.1 established, with one new optional key per section:

```json
{
  "subject": "packages" | "<pkg-name>" | "auntiepypi",
  "sections": [
    {
      "category": "packages",            // NEW; "packages" | "servers"
      "title": "<pkg-name>",
      "light": "green|yellow|red|unknown",
      "fields": [{"name": "...", "value": "..."}]
    }
  ]
}
```

`category` is **optional** — a v0.0.1 consumer ignoring the key keeps
working. The noun-scoped verbs emit single-category section lists; the
composite `auntiepypi overview` emits mixed.

### Dashboard row schema (`category: "packages"`)

```json
{
  "category": "packages",
  "title": "afi-cli",
  "light": "green",
  "fields": [
    {"name": "version",     "value": "1.4.2"},
    {"name": "index",       "value": "pypi.org"},
    {"name": "released",    "value": "12d ago"},
    {"name": "downloads_w", "value": "247"}
  ]
}
```

`index` is always `"pypi.org"` in v0.1.0. The schema does not change in
v0.2.0; only the value flips for packages on the local mesh index.

### Deep-dive section schema (one per dimension + `_summary`)

```json
{
  "category": "packages",
  "title": "recency",
  "light": "pass|warn|fail|unknown",
  "fields": [
    {"name": "value",  "value": "12 days"},
    {"name": "reason", "value": "last release 2026-04-17"}
  ]
}
```

The `_summary` section carries `title: "_summary"`, `light` = the
rolled-up traffic light, and a single `fields` entry naming the package.

## Rubric (7 dimensions)

All scores are `pass` / `warn` / `fail` / `unknown`. Roll-up:

- Any `fail` → **red**.
- Else any 2+ `warn` (counting `unknown` as `warn`) → **yellow**.
- Else → **green**.

| Dimension | Source field | Pass | Warn | Fail | Unknown |
|---|---|---|---|---|---|
| **recency** | `releases[latest].upload_time_iso_8601` | < 30 d | 30–90 d | > 90 d | no releases |
| **cadence** | median gap, last 5 non-yanked `upload_time_iso_8601` | < 15 d | 15–60 d | > 60 d / only 1 release | no releases |
| **downloads** | pypistats `/recent.last_week` | ≥ 10 | 3–9 | < 3 | pypistats 404 / unreachable |
| **lifecycle** | `info.classifiers` `Development Status :: …` | 4-Beta / 5-Stable / 6-Mature | 3-Alpha | 1-Planning / 2-Pre-Alpha / absent | — |
| **distribution** | `urls[].packagetype` for current release | wheel + sdist | sdist only | no artifacts / only legacy `.egg` | — |
| **metadata** | `info.license` ∧ `info.requires_python` ∧ `info.project_urls.{Homepage,Source}` ∧ `len(info.description) > 200` | all 5 | 3–4 | < 3 | — |
| **versioning** | `info.version` parsed as PEP 440 | ≥ 1.0.0 | 0.x with > 5 releases | 0.x with ≤ 5 releases | non-PEP-440 string |

### Edge cases

- Yanked-only releases are filtered out for `recency` and `cadence`.
- Pre-releases (`a` / `b` / `rc`) count for `cadence` but a `1.0.0rc1`
  with no stable `1.0.0` stays `0.x` in `versioning`.
- `cadence` with < 5 releases uses what is available; with 1 release →
  `fail`.
- All time math is UTC; parse `upload_time_iso_8601` (always present per
  the Warehouse JSON spec, RFC 3339).

## Architecture

```text
auntiepypi/
├── cli/
│   └── _commands/
│       ├── overview.py        # composite: packages + servers sections
│       └── _packages/
│           ├── __init__.py
│           └── overview.py    # noun-scoped: dashboard or deep-dive
├── _rubric/
│   ├── __init__.py            # DIMENSIONS = (recency, cadence, ...)
│   ├── _dimension.py          # frozen @dataclass Dimension; Score enum
│   ├── _runtime.py            # roll_up(scores) -> Light; render
│   ├── _fetch.py              # urllib wrapper: get_json(url, timeout=5)
│   ├── _sources.py            # fetch_pypi(pkg), fetch_pypistats(pkg)
│   ├── recency.py
│   ├── cadence.py
│   ├── downloads.py
│   ├── lifecycle.py
│   ├── distribution.py
│   ├── metadata.py
│   └── versioning.py
└── _probes/                   # UNCHANGED from v0.0.1
```

`_rubric/` is the new plugin point. Each dimension file exposes a single
`Dimension` instance and a pure `evaluate(pypi_data, stats_data) -> Score`
function. Adding a future dimension (vuln scan, GH stars, license
compatibility) is one new file plus one entry in `_rubric/__init__.py`,
exactly the pattern `_probes/` already uses.

`_sources.py` stays a single small file with two functions until a third
data source enters the picture (osv.dev, GH API, …); at that point it
splits into `_sources/<name>.py`. Not before — YAGNI.

The composite `cli/_commands/overview.py` calls into both `_packages/`
and `_probes/` and concatenates their sections.

### Configuration

```toml
[tool.auntiepypi]
packages = ["afi-cli", "shushu", "ghafi", "steward", "auntiepypi"]
```

Read via stdlib `tomllib`. The dashboard requires this; the deep-dive
does not. Found by walking up from CWD until a `pyproject.toml`
containing `[tool.auntiepypi].packages` is found, or `$HOME` is reached
(no global fallback).

The schema is intentionally a flat list of strings. Per-package
overrides arrive in v0.2.0 as an array-of-tables form
(`[[tool.auntiepypi.packages]] name = "..."; index = "..."`); the loader
will accept either shape. The dashboard row schema does not change.

## Network policy

- **Stdlib only.** `urllib.request`, `concurrent.futures`,
  `socket.timeout`. No `requests`, no `httpx`, no retry libraries.
- **Per-fetch:** 5 s timeout, no retries, custom UA
  `auntiepypi/<__version__> (+https://github.com/agentculture/auntiepypi)`,
  `Accept: application/json`.
- **Concurrency:** roll-up uses `ThreadPoolExecutor(max_workers=8)` to
  fan out 2N fetches (PyPI + pypistats per package). Deep-dive fetches
  the two sources sequentially.
- **No on-disk cache.** Roll-up against ~10 packages takes ≤ 200 ms when
  upstream is healthy; caching is not worth the staleness story.

### Failure mapping

| Failure | Maps to |
|---|---|
| `HTTPError` 404 from pypi.org | section `light=unknown`, reason "package not on PyPI"; pypistats not fetched |
| `HTTPError` 404 from pypistats.org | `downloads` dimension only → `unknown`; rest scores |
| `HTTPError` 5xx, `URLError`, `socket.timeout` | affected dimensions → `unknown` with reason "fetch failed: \<repr\>" |
| `JSONDecodeError`, missing schema key | dimensions touched by missing key → `unknown` with reason "unexpected response shape" |
| Every fetch raised | exit `2`, "env error: no PyPI fetches succeeded"; JSON envelope still emitted |

### stderr / stdout

Same split as v0.0.1: structured payload (text or JSON) on stdout;
human-readable warnings ("fetch failed: …", "package not on PyPI: …")
on stderr. An agent piping to `jq` never sees the warnings.

## Testing

Two layers, two markers, two CI jobs.

### Layer 1 — Hermetic (PR-blocking, default)

- **Per-dimension unit tests** (`tests/test_rubric_<dim>.py`). Pure
  functions over fixture dicts. ~28 small tests across the seven
  dimensions × four cases (pass / warn / fail / unknown).
- **Roll-up tests** (`tests/test_rubric_runtime.py`). Pure logic.
- **Source-layer tests** (`tests/test_rubric_sources.py`).
  `_fetch.get_json` exercised via stdlib `http.server.ThreadingHTTPServer`
  on a localhost ephemeral port — same pattern `_probes/` already uses.
  Covers 200, 404, 5xx, slow → timeout, malformed JSON.
- **CLI tests** (`tests/test_cli_packages.py`,
  `tests/test_cli_overview_composite.py`). Argparse routing, exit
  codes, JSON envelope shape with monkeypatched sources.

### Layer 2 — Live network (`@pytest.mark.live`, opt-in)

Real HTTPS to pypi.org and pypistats.org. Targets: `requests`, `pip`,
`setuptools`. Schema-only assertions (e.g. "`info.version` is a
non-empty string", "rolled-up light is one of {green, yellow, red,
unknown}"). Values drift; schemas are what we depend on.

A `live_session` pytest fixture wraps each test: on `URLError`,
`socket.timeout`, or 5xx, it `pytest.skip()` with the reason — upstream
hiccups do not turn the build red. Stdlib only; no
`pytest-rerunfailures`.

Politeness: live tests run sequentially (no `-n auto`), one fetch per
second pacing. Total live traffic per run: ~10 requests.

### CI scheduling

| Trigger | Job |
|---|---|
| Pull requests | hermetic suite (blocking) + live suite (`continue-on-error: true`) |
| Push to `main` | hermetic suite (blocking) + live suite (blocking) |
| `publish.yml` pre-upload | install built wheel into clean venv → run `auntiepypi --version` and `auntiepypi packages overview requests --json`; aborts upload on failure |
| `publish.yml` post-upload | poll pypi.org for the new version; install fresh in tempdir; run the same smoke; failure → loud workflow failure (manual yank decision) |

The pre/post-deploy jobs are version-coupled by construction — they run
against the same checkout that produced the wheel.

### Coverage

Gate moves from 60% to **95%** on the `auntiepypi/` package, configured
in `pyproject.toml`:

```toml
[tool.coverage.report]
fail_under = 95
exclude_lines = [
  "pragma: no cover",
  'if __name__ == "__main__"',
  "raise NotImplementedError",
]
```

Step 0 of the implementation plan is an audit of current v0.0.1
coverage; if any module sits below 95%, that PR backfills tests on
existing code before any new code lands. Per-dimension purity makes
~95% on `_rubric/` straightforward; the work, if any, is on the
existing CLI plumbing.

## Catalog, learn, docs

- **`auntiepypi/explain/catalog.py`** — drop the `("online",)`
  placeholder; add `("packages",)` and `("packages", "overview")`. Root
  entry moves `auntiepypi packages overview` from "Planned" into "Verbs"
  and updates the noun list. `local` stays in "Planned".
- **`auntiepypi/cli/_commands/learn.py`** — JSON `planned` array drops
  the `online …` rows; keeps `local …`.
- **`CLAUDE.md`** — promote the v0.1.0 surface block above the Roadmap
  section; mark v0.1.0 line as shipped (read-only: dashboard + maturity
  rubric); release-orchestration explicitly deferred. Add a one-line
  pointer to `docs/about.md`.
- **`README.md`** — opening paragraph adopts the Statement of purpose
  verbatim. Status line moves to v0.1.0. Short example block showing
  `auntiepypi packages overview` output.
- **`CHANGELOG.md`** — `## [0.1.0]` block written at PR time by the
  `version-bump` skill, mirroring v0.0.1's bullet style.
- **NEW `docs/about.md`** — long-form, non-technical explainer. Audience:
  new humans and onboarding agents who haven't read CLAUDE.md. Opens
  with the Statement of purpose; describes "informational, not gating"
  in plain language; sketches the v0.2.0 + future direction without
  over-promising.
- **`culture.yaml`** — unchanged. The mesh metadata does not depend on
  CLI surface.

## Roadmap follow-ons (out of scope here)

- v0.2.0 introduces the `servers` noun. `auntiepypi servers overview` is
  the natural home for today's `_probes/` flavor probes; v0.2.0 expands
  it with lifecycle data (running PIDs, ports, mirror status).
- v0.2.0 is also where the `index` field in dashboard rows starts
  resolving to local mesh URLs for packages hosted on the local index.
- Release-orchestration (`packages release SIBLING --apply` triggering
  the sibling-side `publish.yml`) is its own design + PR. Not v0.1.0.
- Periodic last-update checks (cron-driven dashboards, alerting) are
  explicitly out of scope per the brainstorm.

## Verification

```bash
uv sync
uv run pytest -n auto --cov=auntiepypi --cov-report=term -v
uv run pytest -m live -v                         # opt-in live suite
uv run black --check auntiepypi tests
uv run isort --check-only auntiepypi tests
uv run flake8 auntiepypi tests
uv run pylint --errors-only auntiepypi
uv run bandit -c pyproject.toml -r auntiepypi
markdownlint-cli2 "**/*.md" "#node_modules"
bash .claude/skills/pr-review/scripts/portability-lint.sh

uv run auntiepypi --version
uv run auntiepypi packages overview --json | jq .
uv run auntiepypi packages overview requests --json | jq .
uv run auntiepypi overview --json | jq '.sections | group_by(.category) | map({category: .[0].category, count: length})'
uv run auntiepypi explain packages
uv run auntiepypi explain packages overview
uv run auntiepypi learn --json | jq '.planned'

(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
```
