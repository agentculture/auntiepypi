# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: v0.1.0 — packages overview landed

The `packages` noun shipped: `agentpypi packages overview [PKG]` is the
read-only PyPI maturity dashboard / deep-dive. The top-level
`agentpypi overview` is now a composite of packages + servers sections.
Read-only, stdlib-only HTTP, informational (not gating).

This file describes the repository **as it exists on disk today**. When
you edit, keep claims grounded in checked-in reality; the moment a
section drifts ahead of reality, mark it `(planned)` or move it under
`## Roadmap`.

Remote: `https://github.com/agentculture/agentpypi`.

See `docs/about.md` for the non-technical explainer.

## What this repo is

`agentpypi` manages **both ends of the Python distribution pipe** for the
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
| 2 | Top-level package | `agentpypi/__init__.py`, `agentpypi/__main__.py` (`__version__` via `importlib.metadata`) |
| 3 | CLI scaffolding | `agentpypi/cli/__init__.py`, `cli/_errors.py`, `cli/_output.py`, `cli/_commands/` |
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
(cd ../steward && uv run steward doctor --scope self ../agentpypi)
```

## Quality pipeline

The dev-extras and pre-commit hook set every AgentCulture sibling ships
with — copy from `shushu` or `ghafi` rather than re-deriving:

- **Format:** `black`, `isort` (line length 100, target py312)
- **Lint:** `flake8` (+ `flake8-bandit`, `flake8-bugbear`), `pylint --errors-only`
- **Security:** `bandit -r agentpypi -c pyproject.toml`
- **Markdown:** `markdownlint-cli2 "**/*.md"` (config: `.markdownlint-cli2.yaml` at repo root)
- **Portability:** `bash .claude/skills/pr-review/scripts/portability-lint.sh`
  (no `/home/<user>/...` paths, no `~/.<dotfile>` refs in committed configs)

`.flake8` carries any per-file ignores (e.g. `tests/*:S101`). Don't broaden
it to silence real findings — delete or fix the offending code.

## Version discipline

One source of truth: `pyproject.toml` `[project].version`.
`agentpypi/__init__.py` resolves `__version__` dynamically via
`importlib.metadata.version("agentpypi")`. No literal `__version__`
elsewhere. Every PR bumps (`major` / `minor` / `patch`) using the
vendored `version-bump` skill; CI's `version-check` job blocks merge
otherwise.

## Python floor

`requires-python = ">=3.12"`. PEP 604 unions, frozen dataclasses,
`tomllib`, `importlib.resources.files`. Do not lower the floor.

## CLI shape

Noun/verb, agent-first, identical in spirit to `afi-cli` / `cfafi` /
`ghafi` / `shushu`:

```text
agentpypi <noun> <verb> [args] [--json] [--apply]
```

Active verbs and nouns registered at v0.1.0:

- `agentpypi learn` (and `learn --json`) — self-teaching prompt
  generated from the `agentpypi/explain/catalog.py` catalog so it can
  never describe a verb that isn't registered.
- `agentpypi explain <path>` — markdown for any noun, verb, or planned
  concept. `local` resolves to a `status: planned` entry.
- `agentpypi overview [TARGET] [--json]` — composite of packages +
  local server probes; with TARGET drills into a server flavor or
  configured package. JSON shape is `{"subject", "sections": [...]}`.
  Read-only. Unknown TARGET → exit 0 with a stderr warning + zero-target
  report (per AFI rubric bundle 6).
- `agentpypi packages overview [PKG] [--json]` — read-only PyPI
  maturity dashboard. Without PKG: one row per package in
  `[tool.agentpypi].packages`. With PKG: deep-dive showing all seven
  maturity signals.
- `agentpypi doctor [--fix] [--json]` — same probes plus diagnoses;
  with `--fix`, runs each probe's `start_command` and re-probes. Exits
  `2` only when `--fix` was attempted and any server is still not up
  after the re-probe.
- `agentpypi whoami [--json]` — auth/env probe; reads
  `$PIP_INDEX_URL` / `$UV_INDEX_URL` env vars and pip's global config
  file, cross-references local probes. Exact paths inspected live in
  `agentpypi/cli/_commands/whoami.py`.

One top-level noun is catalog-known but **not** yet registered as an
argparse subcommand; calling it errors with `invalid choice` until the
milestone lands:

- `agentpypi local …` (v0.2.0) — run / mirror / publish to the in-mesh
  index. `serve` is foreground-default; everything write-shaped is
  `--apply`-gated.

## Roadmap discipline

CLI changes follow the same discipline as the rest of the AgentCulture
mesh: brainstorm with the `superpowers:brainstorming` skill before code,
write a design doc under `docs/superpowers/specs/`, and bump the version
on every PR (`version-bump` skill — CI's `version-check` job blocks
merge otherwise).

The first implementation PR (v0.0.1) brainstormed the noun set and
shipped flat verbs instead of the `online` / `local` nouns CLAUDE.md
originally sketched. That decision is captured in
`docs/superpowers/specs/2026-04-28-agentpypi-v0.0.1-design.md` under
"Drift acknowledged".

## Roadmap (high-level, agent-readable)

1. **v0.0.1 — package skeleton.** `pyproject.toml`, top-level package,
   argparse `main()` with `learn` / `explain` / `whoami`, tests for
   `--version` and `learn --json`, CI `tests.yml`. Joins the mesh
   (`culture.yaml`) and gets `pypi` / `testpypi` GH Environments via `ghafi`.
2. **v0.1.0 — packages overview (shipped; read-only: dashboard + maturity
   rubric).** `agentpypi packages overview [PKG]` — PyPI maturity
   dashboard across configured packages. Top-level `overview` promoted to
   composite (packages + server probes). Release orchestration
   (`online release SIBLING --apply`) explicitly deferred to a later
   milestone.
3. **v0.2.0 — `local` noun + `servers` lifecycle.** Foreground
   `local serve` (PEP 503 simple index), `local upload`, `local mirror
   PACKAGE`. `servers` noun for start/stop/list/diagnose of local servers.
   Wire systemd unit under `docs/deploy/`.
4. **v1.0.0 — mesh-aware.** Local index discoverable via Culture-mesh
   service registry; trust boundary documented in `docs/threat-model.md`.

This roadmap is descriptive of intent, not a commitment. Reorder or
replace as the design lands.
