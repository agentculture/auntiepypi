# Sibling pattern — pointer

auntiepypi follows the AgentCulture sibling pattern enforced by
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
in steward today). Vendoring the list into auntiepypi would make the
two drift the moment steward tightens. The agreement here is: **steward
owns the contract; auntiepypi reads it from steward**.

If steward ever moves the canonical contract elsewhere (e.g. publishes
`sibling-pattern.json` for machine consumption), update this pointer —
not by copying the contents in.

## Running the diagnosis

Self-scope (single-repo invariants — portability + skills-convention):

```bash
cd ../steward
uv run steward doctor --scope self ../auntiepypi
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

auntiepypi's `culture.yaml` landed at v0.0.1 (see repo root), so
`--scope siblings` includes this repo today.

## On `culture.yaml`

`culture.yaml` declares an agent to the Culture mesh; it is **not**
required for every sibling. Steward itself doesn't have one — it's a
CLI/tools repo, not a Culture-managed resident agent. auntiepypi shipped
`culture.yaml` at v0.0.1 because auntiepypi *will* run as a
mesh-resident process (the local PyPI index listens on the mesh, once
v0.2.0 lands `local serve`). It was modelled after
`../daria/culture.yaml` and `../shushu/culture.yaml` — keep changes
aligned with those when the agent shape evolves.

## On `steward doctor --apply`

`--apply` repair mode is **planned**, not implemented. The contract for
which findings will become auto-repairs lives in `../steward/docs/sibling-pattern.md`
under "Repairs". Until it ships, treat doctor's output as a punch list
to fix by hand.
