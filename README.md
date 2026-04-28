# agentpypi

> **Status: warm-up.** Repo skeleton only — intent + conventions are written
> down here so the first implementation PR has a target to aim at. No code,
> `pyproject.toml`, or tests have landed yet.

PyPI for the agents. `agentpypi` is the AgentCulture sibling that manages
**both ends of the Python distribution pipe**:

- **Online PyPI** — release orchestration for AgentCulture siblings
  (`afi-cli`, `cfafi`, `ghafi`, `shushu`, `steward`, `zehut`, …): version
  checks, TestPyPI smoke installs, PyPI publishing dashboards. Uses the
  `pypi` / `testpypi` GitHub Environments that `ghafi` provisions, and the
  Trusted Publishing flow each sibling already wires into
  `.github/workflows/publish.yml`.
- **Local PyPI** — a private index running on the Culture mesh so agents can
  publish and pull intra-mesh wheels (pre-release builds, internal-only
  packages, vendored mirrors) without leaving the org's trust boundary.

Part of the [AgentCulture](https://github.com/agentculture) OSS org —
maintained jointly by agents and one human (Ori Nachum). Sibling to
[`afi-cli`](https://github.com/agentculture/afi-cli) (the agent-first CLI
scaffolder this repo will be built from), [`ghafi`](https://github.com/agentculture/ghafi)
(GitHub-side bootstrapper), and [`steward`](https://github.com/agentculture/steward)
(alignment / skills supplier).

## Install (planned)

```bash
uv tool install agentpypi
agentpypi --version
```

Python ≥ 3.12. `uv tool install` is the supported path — not `pip install`.

## Intended surface (planned)

Every verb defaults to dry-run; `--apply` to commit. Every command supports
`--json`. Exit-code policy follows the [afi rubric](https://github.com/agentculture/afi-cli/blob/main/docs/rubric.md#exit-code-policy)
(`0` success / `1` user error / `2` env error).

```bash
# Self-teaching surface — same shape as every AgentCulture CLI
agentpypi learn                       # markdown summary of every verb
agentpypi learn --json                # structured payload for agents
agentpypi explain release             # explain a verb
agentpypi explain online              # explain a noun

# Auth probe
agentpypi whoami                      # which PyPI / TestPyPI / local index am I talking to?

# Online — orchestrate releases of AgentCulture siblings
agentpypi online status SIBLING       # PyPI vs CHANGELOG vs main vs latest tag
agentpypi online release SIBLING      # dry-run: would-be tag + workflow trigger
agentpypi online release SIBLING --apply

# Local — manage the in-mesh index
agentpypi local serve                 # run the local index (foreground)
agentpypi local upload PATH           # publish a wheel/sdist to the local index
agentpypi local mirror PACKAGE        # snapshot a public package into local
agentpypi local list                  # what's hosted locally
```

The exact verb set is **not frozen** — these are sketches, not contracts.
The first implementation PR brainstorms the noun set with the
`superpowers:brainstorming` skill before any code lands.

## Develop (planned)

```bash
uv sync                          # install + dev deps
uv run pytest -n auto -v         # tests
uv run agentpypi --version       # smoke
uv run pre-commit install        # enable lint hooks
```

Quality pipeline mirrors the rest of the AgentCulture mesh: `black`, `isort`,
`flake8` (+ `flake8-bandit`, `flake8-bugbear`), `pylint`, `bandit`,
`markdownlint-cli2`. CI runs on every PR + push to `main`.

## Trusted Publishing

Once `pyproject.toml` lands, `ghafi` provisions the `pypi` / `testpypi`
GitHub Environments and `.github/workflows/publish.yml` follows the same
OIDC Trusted Publishing pattern every sibling uses — no secrets in the repo.

## License

MIT. © 2026 Ori Nachum / AgentCulture.

— Claude
