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

## What it does today (v0.1.x — packages overview)

Two things, both read-only:

1. **Dashboard.** Run `auntie packages overview` and you get a
   one-row-per-package summary of every package listed in your repo's
   `[tool.auntiepypi].packages` block. Each row shows the current
   version, the index it lives on (currently always pypi.org), how long
   ago it was released, and last-week download count. A traffic light
   sums up seven maturity signals.

2. **Deep-dive.** Run `auntie packages overview <pkg>` for any
   package on PyPI — yours or anyone else's — and you get the seven
   signals broken out: recency of releases, cadence between them,
   download volume, Trove lifecycle classifier, distribution
   (wheel/sdist), metadata completeness, and PEP 440 versioning
   maturity. See `maturity-rubric.md` for the green/yellow/red
   thresholds each signal applies.

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

## v0.3.0 (the v0.2.0 milestone) — detect, don't supervise

Semver bumped to 0.3.0 because 0.2.0 shipped the
`agentpypi → auntiepypi` rename. The spec calls this the **v0.2.0
detection milestone**.

`auntie overview` now sees more than just the canonical-port devpi /
pypiserver instances: it reads `[[tool.auntiepypi.servers]]` from
`pyproject.toml`, fingerprints anything running on port 3141 / 8080,
and (with `--proc`) walks `/proc` for matching processes. The CLI
binary becomes `auntie` (the longer `auntiepypi` stays as an alias
for muscle memory and any scripts that hard-coded the old name).

It deliberately stops at *seeing*. Lifecycle — start, stop, our own
PEP 503 server — lands in v0.3.0 under existing top-level verbs (no
new noun). For now: declare your servers, let systemd-user supervise
them (see `docs/deploy/`), and run `auntie overview` to see what's
home.

## Where it's headed

- v0.3.0 — serve / lifecycle. The ability to actually start and stop a
  PyPI server, or run our own. Verb shape is decided in v0.3.0's
  brainstorm: most likely either expanding `doctor` (`doctor --start`,
  `doctor --serve`) or adding a top-level verb. The earlier `local`
  noun has been permanently dropped — no new noun.
- Later — release orchestration (trigger sibling `publish.yml`
  workflows); additional detectors as needed (Docker socket,
  systemd-user unit listing, launchd on macOS); whatever the mesh
  needs next.

Nothing here gets shipped without a brainstorm pass and a written spec
under `docs/superpowers/specs/`. The roadmap is a sketch, not a plan.
