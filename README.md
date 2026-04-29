# auntiepypi

> auntiepypi is both a CLI and an agent that maintains, uses, and serves
> the CLI for managing PyPI packages. It supports remote (pypi.org)
> today and local (mesh-hosted) indexes in future milestones. It
> overviews packages — informational, not gating.

**Status:** v0.1.0 — read-only PyPI maturity dashboard + composite
overview shipped. `local` (in-mesh PyPI server) and `servers` (lifecycle
management) are planned for v0.2.0.

## Quick start

```bash
uv tool install auntiepypi
auntiepypi --version
auntiepypi packages overview --json | jq
```

For the dashboard to show anything, add a configured package list to
your repo's `pyproject.toml`:

```toml
[tool.auntiepypi]
packages = ["requests", "pip"]
```

See [`docs/about.md`](docs/about.md) for the longer non-technical explainer.

## Develop

```bash
uv sync                          # install + dev deps
uv run pytest -n auto -v         # tests
uv run auntiepypi --version       # smoke
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
