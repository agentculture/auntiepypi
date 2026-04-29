# Onboarding history

This file used to be a forward-looking runbook for becoming a
well-formed AgentCulture sibling ("Step 0–5 + Hold"). v0.0.1 (the
scaffold) and v0.1.0 (the `packages overview` PyPI maturity dashboard
and composite `overview`) have both shipped, so it's preserved here as
a historical record of how the repo got from empty to first release.

For *current* onboarding to the project, read `../CLAUDE.md` and
`./about.md`. For the next implementation milestone, see `../CLAUDE.md`
under "Roadmap".

## Sequence as it actually happened

### Step 0 — Read the spec ✓

- `../CLAUDE.md` end-to-end. Twelve required artifacts. CLI noun/verb
  shape. Python floor (≥3.12). The "do not implement yet" line.
- `../README.md` for the agent-facing pitch and intended verb sketches.
- `./sibling-pattern-pointer.md` for how `steward doctor` audits
  siblings against the canonical pattern.

### Step 1 — Skills setup ✓

Vendored the canonical skills from steward (`version-bump`,
`pr-review`). Added `.claude/skills.local.yaml.example`. Stood up
`docs/skill-sources.md` so future re-syncs are deterministic. The
re-sync procedure now lives in `./skill-sources.md` and the SKILL.md
files themselves; the standalone setup walk-through has been retired.

### Step 2 — AFI scaffold ✓

`afi-cli` is the agent-first CLI scaffolder this repo is built from.
Ran `afi cli cite .`, read the emitted `AGENT.md`, and applied the
stable-contract / shape-adapt split. Produced the package layout
(`auntiepypi/`, `auntiepypi/cli/`, `tests/`) that `CLAUDE.md` requires.

→ See `./afi-setup.md`.

### Step 3 — Quality pipeline ✓

Laid down `pyproject.toml`, `.flake8`, `.markdownlint-cli2.yaml`,
`CHANGELOG.md`, and the two GitHub workflows (`tests.yml`,
`publish.yml`). Wired before the first real PR — the `version-check`
job blocks merge if the version doesn't move, and the TestPyPI publish
step needs Trusted Publishing in place.

→ See `./quality-pipeline.md`.

### Step 4 — Diagnose against the corpus ✓

```bash
cd ../steward
uv run steward doctor --scope self ../auntiepypi
```

Exit 0 with no findings means portability + skills-convention are
clean. The corpus-scoped run (`--scope siblings`) regenerates
`../steward/docs/perfect-patient.md` and writes per-target feedback to
`docs/steward/steward-suggestions.md` *inside this repo*. Treat that
file as advisory — corpus mode never blocks.

### Step 5 — First implementation PR ✓

The "do not implement yet" hold ended with the v0.0.1 PR, which
brainstormed the noun set with `superpowers:brainstorming` before any
code landed. The brainstorm output is preserved under
`./superpowers/specs/2026-04-28-auntiepypi-v0.0.1-design.md`. v0.1.0
followed under
`./superpowers/specs/2026-04-29-auntiepypi-packages-overview-design.md`.

## Where v0.2.0 starts

Per `../CLAUDE.md` Roadmap: the `local` noun (in-mesh PyPI index —
`local serve`, `local upload`, `local mirror PACKAGE`) and the
`servers` lifecycle noun (start/stop/list/diagnose). Server *probes*
already ship in `overview`; v0.2.0 adds the write-side. Brainstorm
first, write a spec under `./superpowers/specs/`, bump the version,
then code.
