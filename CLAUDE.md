# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: v0.2.0 — `auntie overview` detection landed

The CLI binary renamed `auntiepypi` → `auntie` (with `auntiepypi` kept
as an alias console script). The composite `auntie overview` server
section now reads from a new `_detect/` module: declared inventory in
`[[tool.auntiepypi.servers]]`, default-port scanning of 3141 / 8080,
and an opt-in `--proc` (Linux) walker that ties processes to listening
ports. Read-only, stdlib-only HTTP, informational (not gating).
`_probes/` and `doctor --fix` are deliberately untouched; v0.3.0
unifies them with serve / lifecycle work.

This file describes the repository **as it exists on disk today**. When
you edit, keep claims grounded in checked-in reality; the moment a
section drifts ahead of reality, mark it `(planned)` or move it under
`## Roadmap`.

Remote: `https://github.com/agentculture/auntiepypi`.

See `docs/about.md` for the non-technical explainer.

## What this repo is

`auntiepypi` manages **both ends of the Python distribution pipe** for the
AgentCulture mesh:

- **Online PyPI** — release orchestration across AgentCulture siblings
  (`afi-cli`, `cfafi`, `ghafi`, `shushu`, `steward`, `zehut`, …). Read PyPI
  and TestPyPI state, diff against `CHANGELOG.md` / `main`, and trigger
  the per-sibling `publish.yml` workflow that `ghafi` provisioned.
- **Local PyPI** — a private PyPI-compatible index running on the Culture
  mesh so agents can publish and pull intra-mesh wheels without leaving the
  org's trust boundary.

Sibling to [`afi-cli`](https://github.com/agentculture/afi-cli) (CLI shape
this repo inherits), [`ghafi`](https://github.com/agentculture/ghafi)
(provisions the PyPI / TestPyPI GitHub Environments this repo drives), and
[`steward`](https://github.com/agentculture/steward) (alignment + skills
supplier; `steward doctor --scope siblings` will audit this repo against
the corpus baseline once code lands).

Workspace context: see `../CLAUDE.md` (the multi-project workspace) for
cross-project conventions; do not duplicate them here. Per-user globals
load automatically through the agent harness if present.

## Sibling pattern this repo MUST adopt

The AgentCulture sibling pattern (canonical source:
`../steward/docs/sibling-pattern.md`, baseline:
`../steward/docs/perfect-patient.md`). The first implementation PR is
expected to bring all twelve required artifacts in:

| # | Artifact | Path |
|---|----------|------|
| 1 | Toolchain | `pyproject.toml` (hatchling, Python ≥ 3.12, zero runtime deps where possible) |
| 2 | Top-level package | `auntiepypi/__init__.py`, `auntiepypi/__main__.py` (`__version__` via `importlib.metadata`) |
| 3 | CLI scaffolding | `auntiepypi/cli/__init__.py`, `cli/_errors.py`, `cli/_output.py`, `cli/_commands/` |
| 4 | Agent-first verbs | `cli/_commands/{learn,explain,whoami}.py` |
| 5 | Mutation safety | Every write verb defaults to **dry-run**; `--apply` to commit |
| 6 | Tests | `tests/test_cli_*.py`, pytest-xdist, coverage |
| 7 | CI | `.github/workflows/tests.yml`, `.github/workflows/publish.yml` (Trusted Publishing) |
| 8 | Changelog | `CHANGELOG.md` (Keep-a-Changelog), bumped on every PR by the `version-bump` skill |
| 9 | Skills | `.claude/skills/<name>/SKILL.md` + `scripts/` per skill |
| 10 | Per-machine config | `.claude/skills.local.yaml.example` (committed) + `.claude/skills.local.yaml` (git-ignored) |
| 11 | Lint configs | `.flake8`, `.markdownlint-cli2.yaml` (repo-local — no per-user home configs) |
| 12 | This file | Project shape, build/test/publish commands, non-obvious invariants |

`steward doctor --scope self` enforces a subset of these (portability,
skills convention, etc.). Run it before opening the first PR:

```bash
(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
```

## Quality pipeline

The dev-extras and pre-commit hook set every AgentCulture sibling ships
with — copy from `shushu` or `ghafi` rather than re-deriving:

- **Format:** `black`, `isort` (line length 100, target py312)
- **Lint:** `flake8` (+ `flake8-bandit`, `flake8-bugbear`), `pylint --errors-only`
- **Security:** `bandit -r auntiepypi -c pyproject.toml`
- **Markdown:** `markdownlint-cli2 "**/*.md"` (config: `.markdownlint-cli2.yaml` at repo root)
- **Portability:** `bash .claude/skills/pr-review/scripts/portability-lint.sh`
  (no `/home/<user>/...` paths, no `~/.<dotfile>` refs in committed configs)

`.flake8` carries any per-file ignores (e.g. `tests/*:S101`). Don't broaden
it to silence real findings — delete or fix the offending code.

## Version discipline

One source of truth: `pyproject.toml` `[project].version`.
`auntiepypi/__init__.py` resolves `__version__` dynamically via
`importlib.metadata.version("auntiepypi")`. No literal `__version__`
elsewhere. Every PR bumps (`major` / `minor` / `patch`) using the
vendored `version-bump` skill; CI's `version-check` job blocks merge
otherwise.

## Python floor

`requires-python = ">=3.12"`. PEP 604 unions, frozen dataclasses,
`tomllib`, `importlib.resources.files`. Do not lower the floor.

## CLI shape

Agent-first, mostly flat verbs with one noun (`packages`):

```text
auntie <verb> [args] [--json]
auntie packages overview [PKG] [--json]
```

Both `auntie` and `auntiepypi` are registered console scripts pointing
at the same `auntiepypi.cli:main`.

Active verbs registered at v0.2.0:

- `auntie learn` (and `learn --json`) — self-teaching prompt generated
  from the `auntiepypi/explain/catalog.py` catalog so it can never
  describe a verb that isn't registered.
- `auntie explain <path>` — markdown for any noun or verb. There are no
  `status: planned` entries any more (`learn`'s `planned[]` is `[]`).
- `auntie overview [TARGET] [--proc] [--json]` — composite of packages
  plus detected servers. The servers section comes from `_detect/`:
  declared inventory (`[[tool.auntiepypi.servers]]`), default-port scan
  of `3141` / `8080`, and `--proc` (Linux-only) `/proc` walker. With
  TARGET, drills into one detection name, bare flavor alias, or
  configured package, in that priority. JSON shape is
  `{"subject", "sections": [...]}`. Read-only. Unknown TARGET → exit 0
  with a stderr warning + zero-target report. Malformed
  `[[tool.auntiepypi.servers]]` → exit 1.
- `auntie packages overview [PKG] [--json]` — read-only PyPI maturity
  dashboard. Without PKG: one row per package in
  `[tool.auntiepypi].packages`. With PKG: deep-dive showing all seven
  maturity signals.
- `auntie doctor [--fix] [--json]` — same `_probes/` machinery as
  v0.0.1 plus diagnoses; with `--fix`, runs each probe's
  `start_command` and re-probes. Exits `2` only when `--fix` was
  attempted and any server is still not up after the re-probe.
  v0.3.0 will unify this with the new serve work.
- `auntie whoami [--json]` — auth/env probe; reads `$PIP_INDEX_URL` /
  `$UV_INDEX_URL` env vars and pip's global config file. Exact paths
  inspected live in `auntiepypi/cli/_commands/whoami.py`.

No nouns are catalog-known but unregistered; the earlier `local` noun
has been permanently dropped, and a `servers` noun was rejected during
v0.2.0's brainstorm in favour of surfacing detection through
`auntie overview`.

## Roadmap discipline

CLI changes follow the same discipline as the rest of the AgentCulture
mesh: brainstorm with the `superpowers:brainstorming` skill before code,
write a design doc under `docs/superpowers/specs/`, and bump the version
on every PR (`version-bump` skill — CI's `version-check` job blocks
merge otherwise).

The first implementation PR (v0.0.1) brainstormed the noun set and
shipped flat verbs instead of the `online` / `local` nouns CLAUDE.md
originally sketched. That decision is captured in
`docs/superpowers/specs/2026-04-28-auntiepypi-v0.0.1-design.md` under
"Drift acknowledged".

## Roadmap (high-level, agent-readable)

1. **v0.0.1 — package skeleton.** `pyproject.toml`, top-level package,
   argparse `main()` with `learn` / `explain` / `whoami`, tests for
   `--version` and `learn --json`, CI `tests.yml`. Joins the mesh
   (`culture.yaml`) and gets `pypi` / `testpypi` GH Environments via `ghafi`.
2. **v0.1.0 — packages overview (shipped; read-only: dashboard + maturity
   rubric).** `auntie packages overview [PKG]` — PyPI maturity
   dashboard across configured packages. Top-level `overview` promoted to
   composite (packages + server probes). Release orchestration
   (`online release SIBLING --apply`) explicitly deferred to a later
   milestone.
3. **v0.2.0 — `auntie overview` detection (shipped).** `_detect/` plugin
   module: declared inventory (`[[tool.auntiepypi.servers]]`), default
   port-scan, opt-in `/proc` walker. CLI binary rename `auntiepypi` →
   `auntie` (with `auntiepypi` kept as an alias). systemd-user unit
   templates in `docs/deploy/`. Detect-only; no lifecycle verbs.
   `_probes/` and `doctor --fix` deliberately untouched.
4. **v0.3.0 — serve / lifecycle.** Bring in the ability to actually
   start and stop a PyPI server (or run our own). Verb shape decided in
   v0.3.0's brainstorm: most likely either expanding `doctor`
   (`doctor --start`, `doctor --serve`) or adding a top-level verb. Will
   *not* introduce a `local` noun. Unifies `doctor --fix`'s raise
   capability with the new serve work and resolves the v0.2.0 redundancy
   where `_probes/` and `_detect/` both exist.
5. **v1.0.0 — mesh-aware.** Local index discoverable via Culture-mesh
   service registry; trust boundary documented in `docs/threat-model.md`.

This roadmap is descriptive of intent, not a commitment. Reorder or
replace as the design lands.
