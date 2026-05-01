# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/). This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-05-02

### Added

- HTTPS termination on the first-party server. `[tool.auntiepypi.local].cert` and `.key` point at operator-supplied PEM files, loaded via `ssl.SSLContext.load_cert_chain` with `minimum_version` pinned to TLS 1.2. No auto-generation; operator runs `mkcert` / `certbot` / their internal CA.
- HTTP Basic auth on the first-party server. `[tool.auntiepypi.local].htpasswd` points at an Apache htpasswd file (bcrypt-only — `$2y$` / `$2b$` / `$2a$` entries). The parser rejects non-bcrypt lines at load time with the offending line number; silent skip would be how auth bypasses ship.
- Public binding (non-loopback) is now allowed when both TLS and Basic auth are configured. The truth table is enforced at config-load time: loopback hosts always pass; non-loopback requires both `cert+key` AND `htpasswd`. Either alone raises `ServerConfigError` with a `missing: …` tail naming the gap.
- `_server/_tls.py` — `build_ssl_context(cert, key)` builder. Stdlib-only.
- `_server/_auth.py` — `parse_htpasswd`, `verify_basic`, `_AuthCache` (positive-only LRU; 60 s TTL; 128 max; threadsafe). Cache stores `(timestamp, user, expected_hash)` so credential rotation, user removal, or a fresh map all naturally invalidate.
- HTTPS-aware detection probe. `_detect/_http.format_http_url` and `probe_endpoint` accept a `scheme` keyword (default `"http"` — backward-compatible) and an optional `ssl_context`. `_detect/_local.detect()` switches scheme based on `cfg.tls_enabled`; with TLS on, it uses an unverified SSL context (self-probe of our own listener — not a trust decision).
- 401-as-up: when `cfg.auth_enabled`, a 401 from the local server counts as `status="up"` because a working auth gate is a stronger liveness signal than an open 200. The detector deliberately doesn't read htpasswd to extract creds.
- `bcrypt>=4.0,<5` becomes the **first runtime dependency**. Spec captures the rationale: stdlib has no htpasswd-compatible verifier (`crypt` removed in 3.13; `hashlib.scrypt` isn't htpasswd format), and rolling our own bcrypt is malpractice. `cryptography` is added to `[dependency-groups].dev` only — used by a session-scoped self-signed cert fixture for tls/auth tests.

### Changed

- `LocalConfig` (`auntiepypi/_server/_config.py`) gains three optional `Path | None` fields (`cert`, `key`, `htpasswd`) and two derived properties (`tls_enabled` requires both cert+key; `auth_enabled` is `htpasswd is not None`).
- `[tool.auntiepypi.local].host` validator's error message is rewritten — previously named v0.7.0 as the unlock; now describes the truth table directly.
- `_server.serve()` accepts `ssl_context` and `htpasswd_map` kwargs; both default to None so v0.6.0 callers preserve plain-HTTP, unauthed behavior.
- `_server/__main__` adds `--cert`, `--key`, `--htpasswd` flags; exits 2 with a clear stderr message if exactly one of `--cert`/`--key` is set.
- `_actions/auntie._argv()` conditionally appends the new flags. `auntie.start()` runs a pre-flight readability check on configured TLS/auth paths via `_verify_tls_auth_paths()`; a missing file surfaces as `ActionResult(ok=False)` instead of a raise, preserving `auntie up --all`'s independent-dispatch semantics.

### Fixed

- N/A (no carryover bugs from v0.6.0).

## [0.6.0] - 2026-05-01

### Added

- First-party PEP 503 simple-index server (read-only slice). `python -m auntiepypi._server --host H --port P --root R` serves `GET /simple/`, `GET /simple/<pkg>/`, and `GET /files/<filename>` from a wheelhouse. Stdlib-only (`http.server` + `ThreadingHTTPServer`).
- `auntie up` / `auntie down` / `auntie restart` (bare invocation) now start, stop, and restart the first-party server. The `auntie up --all` form aggregates the first-party server with every supervised declaration.
- `[tool.auntiepypi.local]` config block: `host` (loopback only in v0.6.0), `port` (default 3141), `root` (default `$XDG_DATA_HOME/auntiepypi/wheels`). Validated at config-load time; non-loopback host is rejected with a v0.7.0 forward-pointer.
- `_actions/auntie.py` — third managed_by strategy. Wraps `command.py` with a derived argv (`python -m auntiepypi._server …`) so PID-tracking, reprobe, and SIGTERM/SIGKILL escalation are reused from v0.5.0.
- `_detect/_local.py` — emits one Detection (`source="local"`, `flavor="auntiepypi"`, `managed_by="auntie"`) on every `auntie overview` call. Runs first in `detect_all` so the default-port scanner skips its endpoint.
- The name `"auntie"` is reserved. `auntie up auntie` (named target) errors with a clear remediation; the bare form is the only entry point to the first-party server.

### Changed

- `_lifecycle.run_lifecycle` no longer raises on bare invocation. The `_bare_invocation_message` / `_bare_invocation_error` helpers are deleted.
- `SUPERVISED_MODES` gains `"auntie"`.
- `_detect/_runtime.detect_all` order: `_local` → `_declared` → `_port` → `_proc`. The local detection's `(host, port)` enters `covered` so `_port.detect` doesn't double-report 127.0.0.1:3141 as `devpi`.
- Catalog (`_ROOT`, `_LIFECYCLE_PREAMBLE`, `_UP`, `_DOWN`, `_RESTART`) and `learn` synopsis describe the first-party-server lifecycle path; the v0.6.0 forward-pointer prose is removed.

### Fixed

## [0.5.0] - 2026-04-30

### Added

- `auntie up <name>` / `auntie up --all` — start a declared server, or every supervised declaration. Bare `auntie up` is reserved for v0.6.0's first-party server.
- `auntie down <name>` / `auntie down --all` — stop a declared server. For `managed_by=command`: SIGTERM with 5 s grace, then SIGKILL. PID-tracked via XDG state directory.
- `auntie restart <name>` / `auntie restart --all` — atomic for `systemd-user` (`systemctl --user restart`); stop+start for `command`. Re-spawns from current pyproject argv (sidecar argv is advisory; drift logged).
- `_actions/_pid.py` — PID file + sidecar (`<slug>.pid`, `<slug>.json`) with atomic write via `tempfile.mkstemp` + `os.replace`. Liveness check via `os.kill(pid, 0)`; stale records cleaned up on read.
- `_actions/_pid.find_by_port` — Linux-only port-walk fallback for `command.stop` when no PID file exists. Argv-match guard prevents accidentally killing an unrelated process bound to the same port.
- `_reprobe.probe(*, desired="up"|"down")` — extended polling loop supports stop-path verification; `desired="down"` matches both "down" and "absent".
- `auntie explain up` / `down` / `restart` catalog entries with shared lifecycle preamble.

### Changed

- `_actions/<strategy>.apply` → `_actions/<strategy>.start` (internal rename). The single-action contract is replaced by sibling `start` / `stop` / `restart` per strategy.
- `_actions.dispatch` widened to `dispatch(action, detection, declaration)`. `ACTIONS` is now `dict[str, dict[str, Strategy]]` keyed on `(managed_by, action)`. Doctor's `--apply` rewires to `dispatch("start", ...)`.
- `learn` and the explain catalog now describe the three new verbs; the v0.4.0 drift-detection test continues to pass.

## [0.4.0] - 2026-04-30

### Added

- _actions/ lifecycle module with systemd-user and command dispatch strategies
- _decide registry for extensible ambiguity resolution
- auntie doctor --apply (replaces --fix): dispatches actionable servers, deletes half-supervised declarations
- auntie doctor --decide=duplicate:NAME=N: resolves duplicate-name ambiguity before acting
- auntie doctor [TARGET] drill-down: diagnose a single server by name
- Cross-field config validation in strict + lenient modes (managed_by/unit/command consistency)
- Numbered `pyproject.toml.<N>.bak` snapshots written before any mutation
- auntiepypi/_errors.py extracted to break circular import

### Changed

- --fix flag renamed to --apply

## [0.3.0] - 2026-04-29

### Added

- `auntiepypi/_detect/` — declaration-driven inventory of running PyPI servers. Three detectors (`_declared`, `_port`, `_proc`) plus a runtime that merges them with augment + suppress-absent-when-declared semantics.
- `[[tool.auntiepypi.servers]]` config schema. Per-server `name` / `flavor` / `host` / `port` plus reserved-for-v0.3.0 lifecycle fields (`managed_by`, `unit`, `dockerfile`, `compose`, `service`, `command`).
- `[tool.auntiepypi].scan_processes` boolean (parent-table sibling of `packages`) to opt into the `/proc` scan from config; equivalent to passing `--proc`.
- `auntie overview --proc` flag. Linux-only `/proc` walker that finds `pypi-server` / `devpi-server` processes and ties them to listening ports via `/proc/<pid>/fd/*` + `/proc/net/tcp`.
- `auntie` console script registered alongside `auntiepypi` (both point at `auntiepypi.cli:main`). Argparse `prog` is now derived from `argv[0]` so `auntie --version` says `auntie` and `auntiepypi --version` says `auntiepypi`.
- `docs/deploy/` — systemd-user unit templates for `pypi-server` and `devpi-server` plus a one-page README with declaration snippets.

### Changed

- `auntie overview`'s server section group now consumes `_detect.detect_all()` instead of `_probes.probe_status` directly. Declared servers and any extras the augment scan finds appear in the composite report.
- `auntie overview <TARGET>` resolution priority is now: detection name → bare flavor alias → configured package → zero-target.
- Composite `auntie overview` subject string changes from `"auntiepypi"` to `"auntie"`.
- `learn`'s `planned` array is now `[]`. `learn --json`'s `tool` field flips to `"auntie"` with a new `package` field for the underlying distribution. The `local` noun (sketched in earlier roadmaps) is permanently dropped; v0.3.0 lifecycle work will land on `doctor` or top-level verbs, not under a noun.

### Notes

- `_probes/` and `doctor --fix` are deliberately untouched. They will be unified with the new serve work in a future milestone.

## [0.2.0] - 2026-04-29

### Changed

- Renamed package to `auntiepypi` (PyPI distribution name + import path). Old `agentpypi` project on pypi.org is left at 0.1.5; downstream consumers must re-pin.
- `.github/workflows/publish.yml` aligned with the `afi-cli` shape: TestPyPI on PR (`test-publish`, dev versions `<base>.dev<run>`), PyPI on push to main (`publish`). Removed the bespoke `smoke-source` and `smoke-installed` jobs that this repo had added on top of the canonical sibling pattern.

## [0.1.5] - 2026-04-29

### Added

- docs/maturity-rubric.md — single-page reference for the seven packages-overview signals with green/yellow/red thresholds derived from auntiepypi/_rubric/.

### Changed

- docs: refresh after v0.1.x landed — about.md tightens composite overview wording and links to new maturity-rubric.md; onboarding.md becomes historical record; sibling-pattern-pointer.md past-tenses culture.yaml claims; quality-pipeline.md trims CHANGELOG and pre-commit sections to point at vendored skills.

## [0.1.4] - 2026-04-29

### Added

### Changed

### Fixed

## [0.1.3] - 2026-04-29

### Added

### Changed

### Fixed

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
- AFI scaffold applied: `auntiepypi/cli/{_errors,_output}.py` (stable
  contract), `auntiepypi/cli/__init__.py` (`_ArgumentParser` override +
  `_dispatch`), `auntiepypi/explain/{__init__,catalog}.py` (catalog
  resolver + entries for every registered verb plus planned
  online/local nouns).
- Five verbs: `learn`, `explain`, `overview`, `doctor` (`--fix`-gated),
  `whoami`. All support `--json`. Mutating verbs default to dry-run.
- `auntiepypi/_probes/` — uniform interface for known PyPI server
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
- `culture.yaml` registering auntiepypi as a Culture-mesh agent.

### Notes

- `online`/`local` noun groups are catalog-known but NOT yet registered
  as argparse subcommands. Calling them fails with `error: invalid
  choice` + a `hint:` line. Implementations land in v0.1.0 (`online`)
  and v0.2.0 (`local`).
- AFI rubric `overview_cli_noun_exists` check fails for auntiepypi
  because the project has no `cli` noun (its nouns are `online` /
  `local`). Accepted structural deviation; documented in
  `docs/superpowers/specs/2026-04-28-auntiepypi-v0.0.1-design.md`.
