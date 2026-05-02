# About auntiepypi

auntiepypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## What it is

A small command-line tool plus a stable plumbing layer that an agent
inside the AgentCulture mesh can call. The tool reads. It reports. It
does not block builds, fail CI on package-quality grounds, or insist on
its own opinions of "good enough".

## What it does today (v0.8.0)

Five things:

1. **Dashboard.** Run `auntie overview` and you get a
   one-row-per-package summary of every package listed in your repo's
   `[tool.auntiepypi].packages` block. Each row shows the current
   version, the index it lives on (currently always pypi.org), how long
   ago it was released, and last-week download count. A traffic light
   sums up seven maturity signals.

2. **Deep-dive.** Run `auntie overview <pkg>` for any package on PyPI
   — yours or anyone else's — and you get the seven signals broken out:
   recency of releases, cadence between them, download volume, Trove
   lifecycle classifier, distribution (wheel/sdist), metadata
   completeness, and PEP 440 versioning maturity. See
   `maturity-rubric.md` for the green/yellow/red thresholds.

3. **Doctor.** Run `auntie doctor` and you get a diagnosis of every
   declared server: what's down, what's misconfigured, what was found
   on a port scan but not declared. With `--apply`, doctor acts: it
   dispatches declared servers via their `managed_by` strategy, and
   deletes half-supervised declarations that are missing required
   config fields. We never invent config values; ambiguous cases (e.g.
   duplicate names) are deferred to a `--decide` re-run.

4. **Lifecycle.** `auntie up` / `auntie down` / `auntie restart`
   start, stop, and restart servers. Bare invocation targets auntie's
   own first-party PEP 503 simple-index server (loopback only by
   default; HTTPS + Basic auth required for public binding). A named
   target acts on one declared `[[tool.auntiepypi.servers]]` entry;
   `--all` aggregates the first-party server with every supervised
   declaration.

5. **Publish.** `auntie publish <path>` uploads a wheel or sdist to
   the configured first-party index using the legacy PyPI POST upload
   protocol (twine-compatible). Authorization is a strict superset of
   authentication: every publisher must be both authenticated AND in
   the `publish_users` allowlist. With no `htpasswd` configured, the
   server is read-only (POST → 405). With auth configured but
   `publish_users` empty, authenticated POSTs return 403
   "publish disabled" — read-only mode is preserved either way.

The same machinery feeds the top-level `auntie overview`, which
composes the packages dashboard with a `servers` section that surfaces
declared servers, default-port finds, and (with `--proc`) /proc-walked
processes — one read for "what's going on with my packages and my
local servers right now".

## What "informational, not gating" means

The tool tells you what it sees. It does not refuse to exit with code 0
just because a dependency is stale or a download count is low. There is
no `--strict`, no `--fail-on=red`, no quietly-blocking-merge mode. If
you want to gate something on the rubric output, that's a separate
verb — and a separate noun — and a separate design conversation.

This is a deliberate choice. Tools that gate on opinion-shaped metrics
get worked around. Tools that report on opinion-shaped metrics stay
useful.

## How we got here

- **v0.3.0 — detect, don't supervise.** `auntie overview` learned to
  read `[[tool.auntiepypi.servers]]`, fingerprint default-port devpi
  / pypiserver, and (with `--proc`) walk `/proc`. The CLI binary
  became `auntie`; `auntiepypi` stayed as an alias.
- **v0.4.0 — doctor acts.** Diagnosis + `--apply` to dispatch
  declared servers and delete half-supervised entries. Numbered
  `.bak` snapshots before any `pyproject.toml` edit.
- **v0.5.0 — lifecycle verbs.** `auntie up` / `auntie down` /
  `auntie restart` against declared servers. PID-file + sidecar
  tracking; argv-matched port-walk fallback when no PID file exists.
- **v0.6.0 — first-party server.** Read-only PEP 503 simple-index
  for mesh-private use; bare `auntie up` / `down` / `restart` start
  and stop it. Loopback-only binding.
- **v0.7.0 — HTTPS + Basic auth.** Operator-supplied PEM cert and
  htpasswd (bcrypt-only). Public binding allowed only when both are
  configured; either alone rejected at config-load time. `bcrypt`
  becomes the first runtime dependency.
- **v0.8.0 — `auntie publish` (write side).** Twine-compatible POST
  upload at `/`, gated by v0.7.0 auth plus a `publish_users`
  allowlist (cross-checked against htpasswd at config-load).
  Per-request body cap via `max_upload_bytes` (default 100 MiB).
  No new runtime dep — `email.parser.BytesParser` parses the
  multipart body.

## Where it's headed

- **v0.8.x — keyring / netrc.** Credential plumbing for
  `auntie publish`: read username/password from system keyring or a
  netrc-format file. Reduces the `$AUNTIE_PUBLISH_*` env-var
  ergonomics gap.
- **v0.9.0 — streaming multipart.** Replace the v0.8.0 in-memory
  parser with a streaming variant so multi-GiB ML wheels don't pay
  the memory cost. Same on-the-wire protocol.
- **v1.0.0 — mesh-aware.** Local index discoverable via Culture-mesh
  service registry; trust boundary documented. Per-package ownership
  maps likely land here too.

Nothing here gets shipped without a brainstorm pass and a written spec
under `docs/superpowers/specs/`. The roadmap is descriptive of intent,
not a commitment — reorder or replace as the design lands.
