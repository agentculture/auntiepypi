# auntiepypi v0.0.1 — design

**Status:** approved 2026-04-28. The Claude Code planning harness wrote a
machine-side plan file outside the repo; this file is the project-side
spec, committed and authoritative. If they drift, the spec wins.

## Context

`auntiepypi` is a warm-up repo: only `README.md`, `LICENSE`, `.gitignore`,
`CLAUDE.md`, and `docs/` exist before this PR. v0.0.1 lands the twelve
required AgentCulture sibling artifacts plus the agent-affordance verbs.
The user's framing: **the quality pipeline is the central deliverable**.

## Surface (v0.0.1)

Five flat verbs. All support `--json`. Mutating verbs are dry-run by
default (`overview`/`whoami` are read-only; `doctor` requires `--fix`).
Exit codes: `0` success / `1` user error / `2` env error (AFI rubric).

| Verb | Behavior |
|------|----------|
| `overview` | Probe `127.0.0.1` for known PyPI server flavors (devpi:3141, pypiserver:8080); report up/down/absent. Read-only. |
| `doctor` | Same probes + diagnoses + (with `--fix`) start/restart configured servers. |
| `learn` | Markdown self-teaching guide for an agent using auntiepypi. Generated from the explain catalog. |
| `explain <topic>` | Markdown drilldown for any verb or planned noun. `online`/`local` resolve to `status: planned` entries. |
| `whoami` | Auth/env probe — reports configured PyPI / TestPyPI / local index from `pip` / `uv` config. |

`online` and `local` are NOT registered as argparse subcommands at
v0.0.1 — only present in the explain catalog as roadmap entries.

## Architecture

```text
auntiepypi/
├── __init__.py            # __version__ via importlib.metadata
├── __main__.py
├── cli/
│   ├── __init__.py        # main(); argparse top-level
│   ├── _errors.py         # AuntiepypiError + exit codes — STABLE
│   ├── _output.py         # stdout/stderr split, --json — STABLE
│   ├── _explain_catalog.py
│   └── _commands/
│       ├── overview.py
│       ├── doctor.py
│       ├── learn.py
│       ├── explain.py
│       └── whoami.py
└── _probes/
    ├── __init__.py
    ├── devpi.py
    └── pypiserver.py
```

Zero runtime deps; stdlib only.

## Quality pipeline (the centerpiece)

Eight gates, every one a hard CI block; pre-commit mirrors the lint chain
to prevent local/CI drift.

| Gate | Pre-commit | tests.yml | publish.yml |
|------|:----------:|:---------:|:-----------:|
| black | ✓ | lint | — |
| isort | ✓ | lint | — |
| flake8 (+bandit, +bugbear) | ✓ | lint | — |
| pylint --errors-only | — | lint | — |
| bandit -r auntiepypi | ✓ | lint | — |
| markdownlint-cli2 | ✓ (check) | lint | — |
| portability-lint | ✓ | lint | — |
| pytest + 60 % coverage | — | test | test |
| version-check (vs main) | — | version-check | — |
| OIDC Trusted Publishing | — | — | test-publish / publish |

Configs land verbatim from `docs/quality-pipeline.md`.

## Implementation order

1. Toolchain bootstrap (pyproject + lint configs + dynamic `__version__`).
2. Vendor steward's `version-bump` + `pr-review` skills.
3. AFI cite + apply (`afi cli cite .` → write stable-contract files
   verbatim, shape-adapt the rest).
4. `_probes/` (devpi, pypiserver) + thread-server fixture.
5. `overview` / `doctor` / `whoami` implementations + tests.
6. `CHANGELOG.md`.
7. `.github/workflows/tests.yml`, `.github/workflows/publish.yml`.
8. `.pre-commit-config.yaml`.
9. `steward doctor --scope self ../auntiepypi` clean.
10. `afi cli verify . --strict` clean.
11. `culture.yaml` via `culture agent learn` → `culture agent create`.
12. End-to-end smoke + version bump + open PR.

## Drift acknowledged

CLAUDE.md sketches `online`/`local` nouns; v0.0.1 ships flat verbs. The
implementation PR includes a small CLAUDE.md edit moving `online`/`local`
into the Roadmap section and reflecting the actual five-verb v0.0.1
surface. `whoami` stays as required by the AFI rubric.

## Verification

```bash
uv sync
uv run pytest -n auto --cov=auntiepypi --cov-report=term -v
uv run black --check auntiepypi tests
uv run isort --check-only auntiepypi tests
uv run flake8 auntiepypi tests
uv run pylint --errors-only auntiepypi
uv run bandit -c pyproject.toml -r auntiepypi
markdownlint-cli2 "**/*.md" "#node_modules"
bash .claude/skills/pr-review/scripts/portability-lint.sh

uv run auntiepypi --version
uv run auntiepypi learn --json | head
uv run auntiepypi overview
uv run auntiepypi doctor
uv run auntiepypi explain learn
uv run auntiepypi whoami
uv run python -m auntiepypi --version

(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
afi cli verify . --strict
uv run pre-commit run --all-files
```

After PR: `tests`, `lint`, `version-check` green; `test-publish` ships
`0.0.1.dev<n>` to TestPyPI; on merge, `publish` ships `0.0.1` to PyPI.
