# About agentpypi

agentpypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## What it is

A small command-line tool plus a stable plumbing layer that an agent
inside the AgentCulture mesh can call. The tool reads. It reports. It
does not block builds, fail CI on package-quality grounds, or insist on
its own opinions of "good enough".

## What it does today (v0.1.0)

Two things, both read-only:

1. **Dashboard.** Run `agentpypi packages overview` and you get a
   one-row-per-package summary of every package listed in your repo's
   `[tool.agentpypi].packages` block. Each row shows the current
   version, the index it lives on (currently always pypi.org), how long
   ago it was released, and last-week download count. A traffic light
   sums up seven maturity signals.

2. **Deep-dive.** Run `agentpypi packages overview <pkg>` for any
   package on PyPI — yours or anyone else's — and you get the seven
   signals broken out: recency of releases, cadence between them,
   download volume, Trove lifecycle classifier, distribution
   (wheel/sdist), metadata completeness, and PEP 440 versioning
   maturity.

The same machinery feeds the top-level `agentpypi overview`, which adds
a second category — local PyPI server probes — for a one-shot picture
of "what's going on with my packages and my local servers right now".

## What "informational, not gating" means

The tool tells you what it sees. It does not refuse to exit with code 0
just because a dependency is stale or a download count is low. There is
no `--strict`, no `--fail-on=red`, no quietly-blocking-merge mode. If
you want to gate something on the rubric output, that's a separate
verb — and a separate noun — and a separate design conversation.

This is a deliberate choice. Tools that gate on opinion-shaped metrics
get worked around. Tools that report on opinion-shaped metrics stay
useful.

## Where it's headed

- v0.2.0 — local in-mesh PyPI index. `agentpypi local serve` /
  `upload` / `mirror`. The dashboard's `index` column starts showing
  local mesh URLs for packages you host in-house.
- v0.2.0 — `agentpypi servers …` for lifecycle management of those
  local servers (start/stop/list/diagnose).
- Later — release orchestration (trigger sibling `publish.yml`
  workflows); periodic last-update sweeps; whatever the mesh needs
  next.

Nothing here gets shipped without a brainstorm pass and a written spec
under `docs/superpowers/specs/`. The roadmap is a sketch, not a plan.
