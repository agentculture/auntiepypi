# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status: warm-up

This repository is a **freshly-initialised AgentCulture sibling**. The only
checked-in files are `README.md`, `LICENSE`, `.gitignore`, and this file.
There is no `pyproject.toml`, no package, no tests, and no CI yet.

The contract this file captures is the **intended shape** for the first
implementation PR — not a description of what is on disk today. When you
edit, keep claims grounded in what is actually checked in: the moment a
section drifts ahead of reality, mark it `(planned)` or move it under
`## Roadmap`.

Remote (planned): `https://github.com/agentculture/agentpypi`.

## What this repo is

`agentpypi` manages **both ends of the Python distribution pipe** for the
AgentCulture mesh:

- **Online PyPI** — release orchestration across AgentCulture siblings
  (`afi-cli`, `cfafi`, `ghafi`, `shushu`, `steward`, `zehut`, …). Read PyPI
  + TestPyPI state, diff against `CHANGELOG.md` / `main`, and trigger the
  per-sibling `publish.yml` workflow that `ghafi` provisioned.
- **Local PyPI** — a private PyPI-compatible index running on the Culture
  mesh so agents can publish and pull intra-mesh wheels without leaving the
  org's trust boundary.

Sibling to [`afi-cli`](https://github.com/agentculture/afi-cli) (CLI shape
this repo inherits), [`ghafi`](https://github.com/agentculture/ghafi)
(provisions the PyPI / TestPyPI GitHub Environments this repo drives), and
[`steward`](https://github.com/agentculture/steward) (alignment + skills
supplier; `steward doctor --scope siblings` will audit this repo against
the corpus baseline once code lands).

Workspace context: see `../CLAUDE.md` (the multi-project workspace) and
`/home/spark/.claude/CLAUDE.md` (user globals) when in doubt about
conventions; do not duplicate them here.

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

## Quality pipeline (planned)

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

## Version discipline (planned)

One source of truth: `pyproject.toml` `[project].version`.
`agentpypi/__init__.py` resolves `__version__` dynamically via
`importlib.metadata.version("agentpypi")`. No literal `__version__`
elsewhere. Every PR bumps (`major` / `minor` / `patch`) using the
vendored `version-bump` skill; CI's `version-check` job blocks merge
otherwise.

## Python floor

`requires-python = ">=3.12"`. PEP 604 unions, frozen dataclasses,
`tomllib`, `importlib.resources.files`. Do not lower the floor.

## CLI shape (planned)

Noun/verb, agent-first, identical in spirit to `afi-cli` / `cfafi` /
`ghafi` / `shushu`:

```text
agentpypi <noun> <verb> [args] [--json] [--apply]
```

Required verbs (the agent-affordance trio):

- `agentpypi learn` (and `learn --json`) — self-teaching prompt covering
  every noun and verb, generated from the `explain/` catalog so it can
  never lie.
- `agentpypi explain <path>` — markdown for any noun, verb, or concept.
- `agentpypi whoami` — smallest auth probe; reports which PyPI / TestPyPI
  / local index the current env is pointed at.

Two top-level nouns, mirroring the README:

- `agentpypi online …` — read PyPI / TestPyPI state, diff siblings, trigger
  the sibling-side `publish.yml`. Mutations require `--apply`.
- `agentpypi local …` — run / mirror / publish to the in-mesh index.
  `serve` is foreground-default; everything write-shaped is `--apply`-gated.

The exact verb set is **not yet frozen** — brainstorm before coding.
Use the `superpowers:brainstorming` skill on the first design PR.

## Do not implement yet

This repo is a warm-up. Until Ori asks for an implementation PR:

- Do **not** create `pyproject.toml`, package directories, tests, workflows,
  or skills.
- Do **not** add a `culture.yaml` or join the mesh.
- Do **not** invent verbs, exit-code tables, or threat models that aren't
  reflected here.

What you *can* do without permission: tighten this file or `README.md` if
something is wrong, ambiguous, or has drifted from the linked sibling
patterns.

## Roadmap (high-level, agent-readable)

1. **v0.0.1 — package skeleton.** `pyproject.toml`, top-level package,
   argparse `main()` with `learn` / `explain` / `whoami`, tests for
   `--version` and `learn --json`, CI `tests.yml`. Joins the mesh
   (`culture.yaml`) and gets `pypi` / `testpypi` GH Environments via `ghafi`.
2. **v0.1.0 — `online` noun.** Read-only verbs first
   (`online status SIBLING`, `online list`), then mutations
   (`online release SIBLING --apply` triggering the sibling's
   `publish.yml`). PyPI + TestPyPI both addressable.
3. **v0.2.0 — `local` noun.** Foreground `local serve` (PEP 503 simple
   index), `local upload`, `local mirror PACKAGE`. Wire systemd unit
   under `docs/deploy/`.
4. **v1.0.0 — mesh-aware.** Local index discoverable via Culture-mesh
   service registry; trust boundary documented in `docs/threat-model.md`.

This roadmap is descriptive of intent, not a commitment. Reorder or
replace as the design lands.
