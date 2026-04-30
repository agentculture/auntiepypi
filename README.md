# auntiepypi

> auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
> that maintains, uses, and serves the CLI for managing PyPI packages.
> It overviews packages on pypi.org, detects PyPI-flavored servers
> running locally, and can start declared servers — informational
> first, actionable with `--apply`. Stop/restart lands in v0.5.0.

**Status:** v0.4.0 — doctor lifecycle landed. `auntie doctor` is now a
managed_by-aware lifecycle dispatcher: `--apply` replaces `--fix`,
`_actions/` provides `systemd-user` and `command` strategies,
numbered `.bak` snapshots guard every `pyproject.toml` mutation. The
`packages` noun is removed — use `auntie overview <PKG>` instead.

## Quick start

```bash
uv tool install auntiepypi
auntie --version
auntie overview --json | jq '.sections[] | select(.category == "servers")'
auntie overview requests            # deep-dive into a PyPI package
auntie doctor                       # diagnose declared servers (dry-run)
auntie doctor --apply               # act on actionable remediations
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

For the overview and doctor to show anything, add the relevant blocks
to your repo's `pyproject.toml`:

```toml
[tool.auntiepypi]
packages = ["requests", "pip"]
scan_processes = false             # opt into /proc scan; same as `--proc`

[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "pypi-server.service"
```

### `auntie doctor` walkthrough

`auntie doctor` classifies every known server into one of four
categories and explains exactly what to do next:

```text
$ auntie doctor
# auntie doctor
summary: 1 actionable, 1 half-supervised, 1 skip, 0 ambiguous (3 total)

  main          down     declared    managed_by=command
      diagnosis: down; would dispatch managed_by='command'
      remediation: auntie doctor --apply

  stale         down     declared    managed_by=systemd-user
      config_gap: managed_by="systemd-user" requires `unit`
      diagnosis: half-supervised; --apply would delete this entry
      remediation: add `unit = "…"` to keep supervision, or run `auntie doctor --apply`

  pypiserver:8080  up    port        observed; not declared
      remediation:
          [[tool.auntiepypi.servers]]
          name = "…"
          flavor = "pypiserver"
          port = 8080
          managed_by = "manual"

(dry-run; pass --apply to act on 2 remediations)
```

Pass `--apply` to act. A numbered snapshot is written before any edit:

```text
$ auntie doctor --apply
wrote pyproject.toml.1.bak (rollback: mv pyproject.toml.1.bak pyproject.toml)
...
```

If two entries share the same name, use `--decide` to choose which to
keep (or remove):

```text
$ auntie doctor --apply --decide=duplicate:main=1
wrote pyproject.toml.1.bak (rollback: mv pyproject.toml.1.bak pyproject.toml)
wrote pyproject.toml: removed [[tool.auntiepypi.servers]] entry 'main' occurrence 1 (lines 7-12)
...
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
