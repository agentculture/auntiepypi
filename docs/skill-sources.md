# Skill upstream sources

auntiepypi vendors its `.claude/skills/` from steward (the canonical
sibling-pattern owner). This file tracks provenance so re-syncs are
deterministic.

| Skill | Upstream | Downstream copies (known) | Notes |
|-------|----------|---------------------------|-------|
| `version-bump` | `../steward/.claude/skills/version-bump/` | `auntiepypi` (this repo) | Pure-Python; CWD-aware. Re-sync when steward bumps the script. Identifier comments adapted (steward-cli → AgentCulture sibling convention). |
| `pr-review` | `../steward/.claude/skills/pr-review/` | `auntiepypi` (this repo) — adapted | Workflow shape kept verbatim; identifiers (`Steward` → `auntiepypi`) and recurring-bug framing generalized. Reviewer wiring (Qodo / Copilot) is the workspace default. |

## Re-sync procedure

```bash
# Diff against upstream before pulling:
diff -ru ../steward/.claude/skills/version-bump .claude/skills/version-bump
diff -ru ../steward/.claude/skills/pr-review    .claude/skills/pr-review

# Pull (overwrite identifier-only adapted scripts and re-apply the rename):
cp -R ../steward/.claude/skills/version-bump .claude/skills/
cp -R ../steward/.claude/skills/pr-review    .claude/skills/
# Re-apply identifier substitutions (search-replace `steward` → `auntiepypi`,
# `Steward` → `auntiepypi`).
```

If a re-sync would lose the auntiepypi adaptation, lift the change upstream
into steward first (per `../steward/docs/skill-sources.md` "When a skill
should be promoted upstream") and re-vendor.
