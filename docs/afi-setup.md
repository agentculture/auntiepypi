# AFI setup

`afi-cli` is the **Agent First Interface** scaffolder. It emits the
canonical agent-first CLI tree (errors module, output module, `learn`,
`explain`, `whoami`, tests) so siblings don't re-derive the rubric. This
repo is built *from* that scaffold — not by hand.

Sibling location: `../afi-cli`. Reference rubric:
[`docs/rubric.md`](https://github.com/agentculture/afi-cli/blob/main/docs/rubric.md).

## Install

```bash
uv tool install afi-cli
afi --version
```

Or use the workspace checkout directly (useful if you're tracking
unreleased afi-cli changes):

```bash
uv pip install -e ../afi-cli
afi --version
```

## Cite the reference tree

From the agentpypi repo root:

```bash
afi cli cite .
```

What this does (per `../afi-cli/README.md`):

> `afi cli cite` writes only under `.afi/` plus one line in `.gitignore`
> — it never modifies the rest of the target project. The emitted tree
> has literal `{{project_name}}`, `{{slug}}`, `{{module}}` tokens; an
> agent reads the accompanying `AGENT.md` and applies the pattern to
> the host project on its own terms.

Output lands in `.afi/reference/python-cli/`. The append to `.gitignore`
is idempotent — safe to re-run when afi-cli evolves.

## Read the emitted `AGENT.md`

`.afi/reference/python-cli/AGENT.md` is the canonical instruction set —
*it*, not this file, tells you what to do with the scaffold. Read it
end-to-end before applying anything.

This file describes the *intent* of the apply step; `AGENT.md` is the
authority on the mechanics.

## Apply: stable-contract vs shape-adapt

The reference tree splits files into two buckets.

### Stable-contract — copy verbatim into `agentpypi/cli/`

These encode the rubric and shouldn't be rewritten. Substitute only the
tokens (`{{project_name}}` → `agentpypi`, `{{slug}}` → `agentpypi`,
`{{module}}` → `agentpypi`):

- `_errors.py` — `AgentpypiError` + exit-code constants. Exit-code policy
  follows the afi rubric (`0` success / `1` user error / `2` env error).
  Per `../CLAUDE.md`'s "CLI shape", the trio is non-negotiable.
- `_output.py` — stdout/stderr split, `--json` plumbing.
- `explain.py` — markdown rendering for any noun/verb path. Generated
  from a catalog so it can never lie about what the CLI actually exposes.

### Shape-adapt — model and rewrite

These show the *structure*; you rewrite them to fit agentpypi's nouns
(`online`, `local`) and verb set:

- `__init__.py` — `__version__` via `importlib.metadata.version("agentpypi")`.
  No literal version string anywhere else (per `../CLAUDE.md` Version
  discipline).
- `__main__.py` — argparse entry that routes `python -m agentpypi`.
- `learn.py` — generates self-teaching prompt from the explain catalog.
- `whoami.py` — smallest auth probe. For agentpypi: report which
  PyPI / TestPyPI / local index the current env is pointed at.
- `_commands/` — one module per noun. Stub `online.py` and `local.py`
  with `NotImplementedError` raised through the `AgentpypiError`
  sentinel until the noun design lands (per `../CLAUDE.md` "Do not
  implement yet" — verb sets are not frozen).
- `tests/test_cli_*.py` — model the assertion shape, but adapt to
  agentpypi's verbs. The non-negotiable smoke tests at v0.0.1
  (per `../CLAUDE.md` Roadmap) are `--version` and `learn --json`.

## Wire the entry point

In `pyproject.toml` (see `./quality-pipeline.md` for the full template):

```toml
[project.scripts]
agentpypi = "agentpypi.cli:main"
```

Smoke check:

```bash
uv run agentpypi --version
uv run agentpypi learn --json | head
uv run python -m agentpypi --version
```

All three should succeed.

## Verify

`afi cli verify` is the same rubric the upstream uses on itself:

```bash
afi cli verify .              # human-readable report
afi cli verify . --json       # structured for tooling
afi cli verify . --strict     # treat warnings as failures
```

Fix every failing check before opening the first PR. Per
`../afi-cli/README.md`:

> `afi cli verify` is a hybrid auditor: static checks for repo structure
> (`pyproject.toml`, `tests/`) and black-box subprocess probes for
> behavior (`learn`, `--json`, error discipline, `explain`). Every
> failure includes a concrete `remediation` pointer.

## Re-citing later

`afi cli cite .` is idempotent. When `afi-cli` ships a new reference
tree (rubric tightened, new bundle added), re-cite, re-read the diff
in `.afi/reference/python-cli/`, and re-apply the deltas. The applied
copies under `agentpypi/cli/` don't auto-update — that's the
"cite-don't-import" tradeoff.
