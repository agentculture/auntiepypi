# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-04-29

### Added

### Changed

### Fixed

## [0.1.1] - 2026-04-29

### Added

### Changed

### Fixed

## [0.1.0] - 2026-04-29

### Added

- `agentpypi packages overview [PKG]` — read-only PyPI maturity dashboard / deep-dive (informational, not gating).
- Top-level `agentpypi overview` promoted to composite of `packages` + `servers` sections.
- `_rubric/` plugin point (parallels `_probes/`) with seven dimensions: recency, cadence, downloads, lifecycle, distribution, metadata, versioning.
- `[tool.agentpypi].packages` config block in `pyproject.toml`.
- `@pytest.mark.live` opt-in network suite + CI wiring (soft on PR, blocking on main).
- Pre/post-deploy smoke jobs in `publish.yml`.
- `docs/about.md` — non-technical explainer.

### Changed

- Section JSON shape standardises on `{category, title, light, fields}`. Existing v0.0.1 server-flavor sections gain `category: "servers"`.
- Coverage gate: 60% → 95%.

## [0.0.2] - 2026-04-28

### Changed

- doctor: ok now derived from final post-fix probe statuses (was: start_command return codes only)
- doctor: extracted `_apply_fix` and `_process_probe` helpers (S3776 cognitive complexity)
- whoami: switched configparser to interpolation=None (RawConfigParser semantics) so `%` in URL-encoded credentials no longer crashes whoami
- learn: extracted `_M_ONLINE` / `_M_LOCAL` constants for milestone strings (S1192)
- _runtime: dropped redundant URLError catch (subclass of OSError) (S5713)
- tests/test_whoami: switched fake HOME to pytest tmp_path (Copilot review)
- tests/test_overview: switched bogus target to a tmp_path subpath (S5443)
- tests/test_doctor: annotated yield fixture as Iterator[None] (S5886)

### Fixed

- doctor --fix exiting 0 even when a server was still down/absent after a successful start_command (Copilot + qodo bug report)
- README + CLAUDE.md still describing the repo as warm-up despite v0.0.1 landing

## [0.0.1] - 2026-04-28

### Added

- Toolchain bootstrap: `pyproject.toml` (hatchling, py3.12, zero runtime
  deps, dev-dep set), `.flake8`, `.markdownlint-cli2.yaml`, dynamic
  `__version__` via `importlib.metadata`. Coverage `fail_under = 60`.
- Vendored steward skills (`version-bump`, `pr-review`) under
  `.claude/skills/`. `.claude/skills.local.yaml.example` template +
  `docs/skill-sources.md` upstream tracker.
- AFI scaffold applied: `agentpypi/cli/{_errors,_output}.py` (stable
  contract), `agentpypi/cli/__init__.py` (`_ArgumentParser` override +
  `_dispatch`), `agentpypi/explain/{__init__,catalog}.py` (catalog
  resolver + entries for every registered verb plus planned
  online/local nouns).
- Five verbs: `learn`, `explain`, `overview`, `doctor` (`--fix`-gated),
  `whoami`. All support `--json`. Mutating verbs default to dry-run.
- `agentpypi/_probes/` — uniform interface for known PyPI server
  flavors (devpi:3141 `/+api`, pypiserver:8080 `/`); two-stage runtime
  probe (TCP then HTTP) distinguishes up/down/absent.
- Tests: 32 tests across `test_cli`, `test_probes`, `test_overview`,
  `test_doctor`, `test_whoami`; in-process `http.server` thread fixture
  in `conftest.py`. Coverage 92 %.
- GitHub workflows: `tests.yml` (test/lint/version-check) and
  `publish.yml` (TestPyPI on PR, PyPI on main, both via OIDC Trusted
  Publishing).
- Pre-commit hooks: black, isort, flake8 (+ bugbear, bandit), bandit -r,
  markdownlint-cli2 (check), portability-lint.
- `culture.yaml` registering agentpypi as a Culture-mesh agent.

### Notes

- `online`/`local` noun groups are catalog-known but NOT yet registered
  as argparse subcommands. Calling them fails with `error: invalid
  choice` + a `hint:` line. Implementations land in v0.1.0 (`online`)
  and v0.2.0 (`local`).
- AFI rubric `overview_cli_noun_exists` check fails for agentpypi
  because the project has no `cli` noun (its nouns are `online` /
  `local`). Accepted structural deviation; documented in
  `docs/superpowers/specs/2026-04-28-agentpypi-v0.0.1-design.md`.
