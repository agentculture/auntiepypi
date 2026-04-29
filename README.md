# auntiepypi

> auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
> that maintains, uses, and serves the CLI for managing PyPI packages.
> It overviews packages on pypi.org and detects PyPI-flavored servers
> running locally — informational, not gating.

**Status:** v0.2.0 — read-only PyPI maturity dashboard + detection-driven
servers section in the composite `auntie overview`. CLI binary is now
`auntie` (`auntiepypi` stays as an alias). Lifecycle / serve work is
planned for v0.3.0 (no new noun).

## Quick start

```bash
uv tool install auntiepypi
auntie --version
auntie packages overview --json | jq
auntie overview --json | jq '.sections[] | select(.category == "servers")'
```

Example servers-section output (one declared server):

```json
{
  "category": "servers",
  "title": "main",
  "light": "green",
  "fields": [
    {"name": "flavor", "value": "pypiserver"},
    {"name": "port",   "value": "8080"},
    {"name": "status", "value": "up"},
    {"name": "source", "value": "declared"}
  ]
}
```

For the dashboard and the declaration-driven servers report to show
anything, add the relevant blocks to your repo's `pyproject.toml`:

```toml
[tool.auntiepypi]
packages = ["requests", "pip"]
scan_processes = false             # opt into /proc scan; same as `--proc`

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"        # reserved metadata for v0.3.0 lifecycle
unit = "pypi-server.service"
```

See [`docs/about.md`](docs/about.md) for the longer non-technical
explainer. systemd-user unit templates for `pypiserver` / `devpi-server`
live in [`docs/deploy/`](docs/deploy/).

## Develop

```bash
uv sync                          # install + dev deps
uv run pytest -n auto -v         # tests
uv run auntie --version          # smoke
uv run pre-commit install        # enable lint hooks
```

Quality pipeline mirrors the rest of the AgentCulture mesh: `black`,
`isort`, `flake8` (+ `flake8-bandit`, `flake8-bugbear`), `pylint`,
`bandit`, `markdownlint-cli2`. CI runs on every PR + push to `main`.

## Trusted Publishing

`ghafi` provisions the `pypi` / `testpypi` GitHub Environments and
`.github/workflows/publish.yml` follows the same OIDC Trusted Publishing
pattern every sibling uses — no secrets in the repo.

## License

MIT. © 2026 Ori Nachum / AgentCulture.

— Claude
