# Skills setup

This repo will host its own `.claude/skills/` tree. Skills are **vendored**
(copy-paste owned), not symlinked or pip-installed. Steward owns the
canonical copies; this file walks you through pulling them in and standing
up the local-config plumbing.

## Why vendor (not symlink)

From `../steward/CLAUDE.md` "Skills convention":

> Every skill in `.claude/skills/<name>/` ships:
>
> 1. `SKILL.md` — explains *why* and *when* to use it. Frontmatter + short
>    prose; no inline 10-step walk-throughs.
> 2. `scripts/<entry-point>.sh` (or `.py`) — the script that automates the
>    workflow. Following the skill should be "run this script," not "do
>    these ten manual steps." If a skill doesn't have a script, write one
>    before relying on it.
> 3. **No external path dependencies.** Scripts must not reach into
>    another skill's home-directory copy or any other location outside
>    this repo. If a skill needs functionality from elsewhere, vendor it
>    into the skill's own `scripts/` directory. This makes skills
>    portable across Culture projects (Steward's mission is alignment;
>    that requires copy-paste portability).

Symlinks across repos break copy-paste portability. Vendor.

## Which skills to vendor

Sourced from `../steward/docs/skill-sources.md`:

| Skill | Vendor? | Why |
|-------|---------|-----|
| `version-bump` | **Yes** | Pure Python, no per-repo customization. CI's `version-check` job depends on it. |
| `pr-review` | **Yes** (with light adaptation) | Steward owns the canonical PR workflow. Adapt the reviewer wiring (Qodo / Copilot / agentpypi-specific reviewers) and the `portability-lint.sh` paths if needed. |
| `agent-config` | No | Steward-specific (resolves Culture agent suffixes). Not portable as-is. |
| `doc-test-alignment` | No | Stub. Real implementation TBD. Re-evaluate when steward graduates it. |

If `agentpypi` later writes a novel skill that has no per-product
assumptions and a second sibling copies it, promote it upstream to
steward. See "When a skill should be promoted upstream" in
`../steward/docs/skill-sources.md`.

## Vendor procedure

From the agentpypi repo root:

```bash
mkdir -p .claude/skills

cp -R ../steward/.claude/skills/version-bump .claude/skills/
cp -R ../steward/.claude/skills/pr-review    .claude/skills/

# Verify each carries SKILL.md + scripts/ entry-point.
test -f .claude/skills/version-bump/SKILL.md
test -d .claude/skills/version-bump/scripts
test -f .claude/skills/pr-review/SKILL.md
test -d .claude/skills/pr-review/scripts
```

### Adapt `pr-review`

Open every script under `.claude/skills/pr-review/scripts/` and replace
any literal references to the `steward` repo or its package
(`steward.cli`, `steward/`, `agentculture/steward`, etc.) with the
agentpypi equivalents. Keep the **shape** of the workflow (branch,
commit, push, wait for reviewers, triage, fix, reply, resolve); only the
identifiers change.

If agentpypi's PR reviewers differ from steward's (Qodo / Copilot /
something else), update the wait-loop accordingly.

The `portability-lint.sh` carve-outs (`~/.claude/skills/.../scripts/`,
`~/.culture/`) stay as-is — they're general policy, not steward-specific.

### Adapt `version-bump` (rare)

`version-bump` is intentionally pure-Python and project-agnostic. The
script reads `pyproject.toml` + `CHANGELOG.md` from CWD; nothing to
adapt. If the script grows a path constant pointing at `steward/`, that's
a bug — fix it upstream in steward and re-vendor here.

## Per-machine config

Steward's per-machine config lives in
`.claude/skills.local.yaml` (git-ignored) and is documented by a
committed `.claude/skills.local.yaml.example`. Mirror that here.

### Create `.claude/skills.local.yaml.example`

Vendor steward's template verbatim, adjusting only the comment header:

```yaml
# Per-machine config for agentpypi's skills.
# Copy this to skills.local.yaml (git-ignored) and adjust for your environment.
# Skills read skills.local.yaml first, falling back to this example.

# Path to the Culture server's agent manifest (suffix → directory mapping).
# Used by: agent-config (if vendored later) and any skill that resolves
# a registered agent suffix to its repo dir.
culture_server_yaml: ~/.culture/server.yaml

# Sibling project paths checked during the pr-review alignment-delta step.
# Workspace-relative paths (../foo) are preferred. Skills skip entries
# that don't exist on disk, so commenting out missing ones isn't required.
sibling_projects:
  - ../afi-cli
  - ../ghafi
  - ../steward
```

### Update `.gitignore`

Append:

```text
.claude/skills.local.yaml
```

(Already covered by the existing `.gitignore` if it has a broad
`.claude/*.local.*` glob; check before adding.)

## Stand up `docs/skill-sources.md`

Even though agentpypi only vendors two skills today, record them in a
local upstream tracker so future re-syncs are deterministic. The schema
(from `../steward/docs/skill-sources.md`):

```markdown
# Skill upstream sources

| Skill | Upstream | Downstream copies (known) | Notes |
|-------|----------|---------------------------|-------|
| `version-bump` | `steward` (`.claude/skills/version-bump/`) | `agentpypi` (this repo) | Re-sync when steward bumps the script. |
| `pr-review`    | `steward` (`.claude/skills/pr-review/`)    | `agentpypi` (this repo) — adapted | Reviewer wiring may diverge. Note divergence in this repo's `SKILL.md` `description`. |
```

## Smoke test

Run the version-bump script end-to-end after `pyproject.toml` lands
(see `./quality-pipeline.md` for that):

```bash
python3 .claude/skills/version-bump/scripts/bump.py patch
git diff --stat   # expect changes in pyproject.toml + CHANGELOG.md
git checkout -- pyproject.toml CHANGELOG.md   # revert the smoke test
```

If the script can't find `pyproject.toml`, you ran it from the wrong
directory (run from repo root) or the toolchain artifact hasn't landed
yet — finish `./quality-pipeline.md` first and come back.
