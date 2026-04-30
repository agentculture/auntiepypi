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

## What it does today (v0.4.0)

Three things:

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

## v0.3.0 — detect, don't supervise

`auntie overview` now sees more than just the canonical-port devpi /
pypiserver instances: it reads `[[tool.auntiepypi.servers]]` from
`pyproject.toml`, fingerprints anything running on port 3141 / 8080,
and (with `--proc`) walks `/proc` for matching processes. The CLI
binary is `auntie` (`auntiepypi` stays as an alias for muscle memory).

It deliberately stopped at *seeing*. Lifecycle — start, stop — landed
in v0.4.0.

## v0.4.0 — doctor acts

Doctor diagnoses what's wrong, explains how to fix it, and (with
`--apply`) acts. The acts are narrow: spawn declared servers via their
`managed_by` strategy (`systemd-user` or `command`), or delete
half-supervised declarations that are missing required fields. We never
invent config values; ambiguous cases are deferred to a `--decide`
re-run. Before any `pyproject.toml` edit, a numbered `.bak` snapshot
is written so you can roll back with a single `mv` command.

The `--fix` flag from earlier versions is replaced by `--apply`. The
`packages` noun (`auntie packages overview`) is removed — use
`auntie overview <PKG>` instead.

## Where it's headed

- v0.5.0 — own server + lifecycle commands. `auntie up` / `auntie down`
  / `auntie restart`; PID-file tracking; first-party PEP 503
  simple-index for mesh-private use.
- Later — release orchestration (trigger sibling `publish.yml`
  workflows); additional detectors as needed; whatever the mesh needs next.

Nothing here gets shipped without a brainstorm pass and a written spec
under `docs/superpowers/specs/`. The roadmap is a sketch, not a plan.
