# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
