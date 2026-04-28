# Onboarding runbook

Welcome, agentpypi.

This folder is your **order-of-operations** for becoming a well-formed
AgentCulture sibling. The *spec* lives in `../CLAUDE.md` (the twelve required
artifacts, the CLI shape, the python floor, the do-not-implement-yet line);
this runbook tells you *how to acquire each piece in the right order*.

Read `../CLAUDE.md` first, then come back here. Nothing in this folder
overrides `CLAUDE.md` — when they disagree, `CLAUDE.md` wins and the doc
here is wrong (open a fix-up PR).

The canonical artifact list is intentionally **not** repeated here. See
`./sibling-pattern-pointer.md` for the pointer to the source of truth in
`../steward/docs/sibling-pattern.md`.

## Sequence

### Step 0 — Read the spec

- Read `../CLAUDE.md` end-to-end. Twelve required artifacts. CLI noun/verb
  shape. Python floor (≥3.12). The "do not implement yet" line.
- Read `../README.md` for the agent-facing pitch and intended verb sketches.
- Read `./sibling-pattern-pointer.md` to learn how `steward doctor`
  audits siblings against the canonical pattern.

### Step 1 — Skills setup

Vendor the canonical skills from steward (`version-bump`, `pr-review`).
Create `.claude/skills.local.yaml.example`. Stand up
`docs/skill-sources.md` so future re-syncs are deterministic.

→ See `./skills-setup.md`.

### Step 2 — AFI scaffold

`afi-cli` is the agent-first CLI scaffolder this repo is built from. Run
`afi cli cite .`, read the emitted `AGENT.md`, and apply the
stable-contract / shape-adapt split. This produces the package layout
(`agentpypi/`, `agentpypi/cli/`, `tests/`) that `CLAUDE.md` requires.

→ See `./afi-setup.md`.

### Step 3 — Quality pipeline

Lay down `pyproject.toml`, `.flake8`, `.markdownlint-cli2.yaml`,
`CHANGELOG.md`, and the two GitHub workflows
(`tests.yml`, `publish.yml`). Wire **before** the first real PR — the
`version-check` job blocks merge if the version doesn't move, and the
TestPyPI publish step needs Trusted Publishing in place.

→ See `./quality-pipeline.md`.

### Step 4 — Diagnose against the corpus

From the steward checkout (sibling-relative path):

```bash
cd ../steward
uv run steward doctor --scope self ../agentpypi
```

Exit 0 with no findings means portability + skills-convention are clean.
Fix any finding before opening the first PR.

Once `culture.yaml` lands (v0.0.1 in the roadmap), also run:

```bash
uv run steward doctor --scope siblings
```

This regenerates `../steward/docs/perfect-patient.md` and writes
per-target feedback to `docs/steward/steward-suggestions.md` *inside this
repo*. Treat that file as advisory — corpus mode never blocks.

### Step 5 — Hold

`CLAUDE.md` says: do **not** invent verbs, exit-code tables, or threat
models that aren't reflected there yet. The first implementation PR
brainstorms the noun set with `superpowers:brainstorming` before any
code lands. This runbook scaffolds the *frame*; Ori signals the
implementation kick-off.

What you may do without permission: tighten `CLAUDE.md`, `README.md`, or
any file in this `docs/` folder when you spot drift from the linked
sibling patterns.

## What "done" looks like for onboarding

- `.claude/skills/version-bump/` and `.claude/skills/pr-review/` exist
  with `SKILL.md` + `scripts/`.
- `.claude/skills.local.yaml.example` is committed; `.gitignore` lists
  `.claude/skills.local.yaml`.
- `pyproject.toml`, `CHANGELOG.md`, `.flake8`, `.markdownlint-cli2.yaml`
  exist.
- `.github/workflows/tests.yml` and `publish.yml` exist.
- `agentpypi/`, `agentpypi/cli/`, `tests/` exist with the afi scaffold
  applied.
- `steward doctor --scope self ../agentpypi` is clean.

After that, wait for kick-off.
