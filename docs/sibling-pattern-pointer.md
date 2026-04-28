# Sibling pattern — pointer

agentpypi follows the AgentCulture sibling pattern enforced by
`steward doctor`. The canonical artifact list and the machine-checkable
invariants live in **`../steward/docs/sibling-pattern.md`** — read that
file rather than re-quoting it here.

The cross-corpus baseline (synthesized across every known sibling, with
field/skill/CLAUDE-section frequency) is
**`../steward/docs/perfect-patient.md`**. It is regenerated on every
`steward doctor --scope siblings` run, so what you see today reflects
the corpus as of the last run, not a frozen contract.

## Why a pointer instead of a copy

The artifact list and invariants change as the mesh evolves
(`changelog-format`, `lint-config-local`, etc. are listed `(planned)`
in steward today). Vendoring the list into agentpypi would make the
two drift the moment steward tightens. The agreement here is: **steward
owns the contract; agentpypi reads it from steward**.

If steward ever moves the canonical contract elsewhere (e.g. publishes
`sibling-pattern.json` for machine consumption), update this pointer —
not by copying the contents in.

## Running the diagnosis

Self-scope (single-repo invariants — portability + skills-convention):

```bash
cd ../steward
uv run steward doctor --scope self ../agentpypi
```

- Exit 0 + no findings: invariants pass.
- Exit non-zero: read each finding on stderr, fix, re-run. `--json`
  emits the structured findings list to stdout.

Corpus scope (advisory; never blocks):

```bash
cd ../steward
uv run steward doctor --scope siblings
```

This walks every `culture.yaml` in the workspace, regenerates
`../steward/docs/perfect-patient.md`, and writes per-target feedback
into `<target>/docs/steward/steward-suggestions.md` (gated by a marker
line so any hand-written content there is preserved).

agentpypi's `culture.yaml` lands at v0.0.1 per `../CLAUDE.md` Roadmap.
Until then, `--scope siblings` simply won't include this repo.

## On `culture.yaml`

`culture.yaml` declares an agent to the Culture mesh; it is **not**
required for every sibling. Steward itself doesn't have one — it's a
CLI/tools repo, not a Culture-managed resident agent. agentpypi's
roadmap (per `../CLAUDE.md`) puts `culture.yaml` at v0.0.1 because
agentpypi *will* run as a mesh-resident process (the local PyPI index
listens on the mesh). When you write it, model it after `../daria/culture.yaml`
or `../shushu/culture.yaml` rather than from scratch.

## On `steward doctor --apply`

`--apply` repair mode is **planned**, not implemented. The contract for
which findings will become auto-repairs lives in `../steward/docs/sibling-pattern.md`
under "Repairs". Until it ships, treat doctor's output as a punch list
to fix by hand.
