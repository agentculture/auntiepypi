---
name: pr-review
description: >
  auntiepypi PR workflow: branch, commit, push, PR, wait for Qodo/Copilot,
  triage, fix, reply, resolve. Adds a portability lint (no absolute /home paths,
  no per-user dotfile refs in committed docs), an alignment-delta check when
  CLAUDE.md or culture.yaml change, and greenfield-aware test/version-bump
  steps. Use when: creating PRs in auntiepypi, handling review feedback, or the
  user says "create PR", "review comments", "address feedback", "resolve threads".
---

# PR Review — auntiepypi edition

auntiepypi's PRs touch CLI verb surfaces, `culture.yaml` (when it lands),
quality-pipeline configs, and vendored skills. Path leaks and per-user
config dependencies are the recurring bug class across every AgentCulture
sibling — this skill catches both up front, plus an alignment-delta check
when CLAUDE.md or culture.yaml change. The workflow is encapsulated in
`scripts/workflow.sh` — follow that, not a manual checklist.

Vendored from `../steward/.claude/skills/pr-review/` per
`docs/skill-sources.md` (provenance ledger + re-sync procedure).
Re-sync when steward bumps the script. Adapted identifiers only — the
workflow shape is identical.

## Prerequisites

Hard requirements: `gh` (GitHub CLI), `jq`, `bash`, `python3` (stdlib only),
`curl` (used by `pr-status.sh`).

Soft requirement: `PyYAML` is needed only for parsing Culture's server
manifest if a sibling skill needs it. The vendored `pr-review` scripts
work without it.

Per-machine paths (sibling-project layout) live in
`.claude/skills.local.yaml`; see the committed `.example` for the schema.

## How to run

`scripts/workflow.sh` is the entry point. Subcommands:

| Command | Purpose |
|---------|---------|
| `workflow.sh lint` | Portability lint on the current diff (staged + unstaged). |
| `workflow.sh poll <PR>` | Fetch and display all review comments. |
| `workflow.sh delta` | Dump each sibling project's `CLAUDE.md` head + `culture.yaml`. |
| `workflow.sh reply <PR>` | Batch reply (JSONL on stdin) and resolve threads. |
| `workflow.sh help` | Print this list. |

The vendored single-comment helpers — `pr-reply.sh`, `pr-status.sh` — live
next to `workflow.sh` and are usable directly when batching isn't appropriate.

## End-to-end flow

```text
git checkout -b <type>/<desc>
# ... edit ...
.claude/skills/pr-review/scripts/workflow.sh lint
git commit -am "..." && git push -u origin <branch>
gh pr create --title "..." --body "..."   # title <70 chars, body signed "- Claude"
sleep 300                                  # wait for Qodo + Copilot
.claude/skills/pr-review/scripts/workflow.sh poll <PR>
# triage; if CLAUDE.md/culture.yaml/.claude/skills changed:
.claude/skills/pr-review/scripts/workflow.sh delta
# fix, re-lint, push
.claude/skills/pr-review/scripts/workflow.sh reply <PR> < replies.jsonl
gh pr checks <PR>
# Wait for human merge — never merge yourself.
```

Branch naming: `fix/<desc>`, `feat/<desc>`, `docs/<desc>`, `skill/<name>`.
Commit/PR signature: `- Claude` (workspace convention). The reply script
auto-appends `- Claude` only if the body isn't already signed, so JSONL
entries can include or omit it.

## Triage rules

For every comment, decide **FIX** or **PUSHBACK** with reasoning.

Default to **FIX** for: portability complaints (always valid — recurring
AgentCulture bug class), test or doc requests, style nits aligned with
workspace conventions.

Default to **PUSHBACK** for: architecture opinions that conflict with
workspace `CLAUDE.md` or workspace conventions; greenfield false-positives
(e.g. "add tests" before there's any source — defer to a later PR, don't
refuse).

### Alignment-delta rule

If the PR touches `CLAUDE.md`, `culture.yaml`, or anything under
`.claude/skills/`, run `workflow.sh delta` **before** declaring FIX or
PUSHBACK on each comment. The script dumps the head of every sibling
project's `CLAUDE.md` plus the full `culture.yaml`, using `sibling_projects`
from `skills.local.yaml`. Note any sibling that needs a follow-up PR and
mention it in your reply.

## Greenfield-aware steps

The lint and the workflow script are always-on. Stack-specific steps are
conditional and currently active for auntiepypi as the v0.0.1 quality
pipeline lands:

```bash
[ -d tests ] && [ -f pyproject.toml ] && uv run pytest tests/ -x -q
[ -f pyproject.toml ] && python3 .claude/skills/version-bump/scripts/bump.py patch
[ -f .markdownlint-cli2.yaml ] && markdownlint-cli2 "$(git diff --name-only --cached '*.md')"
```

Re-evaluate as later milestones (`online`, `local` nouns) bring new
review surfaces.

## Reply etiquette

Every comment must get a reply — no silent fixes. Always pass `--resolve`
when batch-replying so threads close automatically. Reference the
review-comment IDs in the fix-up commit message. auntiepypi has no
SonarCloud integration at v0.0.1 and isn't a registered mesh agent yet
(culture.yaml lands but no daemon runs), so skip the sonarclaude check
and the post-merge IRC ping that Culture's full `pr-review` includes —
those will return when the corresponding systems wire up.
