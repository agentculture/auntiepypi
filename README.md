# auntiepypi

> auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
> that maintains, uses, and serves the CLI for managing PyPI packages.
> It overviews packages on pypi.org, detects PyPI-flavored servers
> running locally, and starts/stops/restarts declared servers —
> informational first, actionable on demand.

**Status:** v0.7.0 — HTTPS + basic-auth landed. The first-party server
now supports optional TLS termination (operator-supplied PEM via
`[tool.auntiepypi.local].cert` / `.key`, TLS 1.2 floor) and HTTP Basic
auth (Apache htpasswd file, bcrypt-only, via
`[tool.auntiepypi.local].htpasswd`). Public binding (non-loopback) is
allowed when both are configured; either alone is rejected at
config-load time. `bcrypt>=4.0,<5` is the first runtime dependency.

Bare `auntie up` / `auntie down` / `auntie restart` (introduced in
v0.6.0) continue to start, stop, and restart auntie's own simple-index
server. Wheels in `$XDG_DATA_HOME/auntiepypi/wheels/` are served from
`http://127.0.0.1:3141/simple/` (or `https://...` when TLS is
configured) and installable via `pip install --index-url`. Lifecycle
verbs continue to work against declared servers (`managed_by ∈
{systemd-user, command}`); `--all` aggregates the first-party server
with every supervised declaration. `auntie publish` (write side) is
deferred to v0.8.0.

## Quick start

```bash
uv tool install auntiepypi
auntie --version
auntie overview --json | jq '.sections[] | select(.category == "servers")'
auntie overview requests            # deep-dive into a PyPI package
auntie doctor                       # diagnose declared servers (dry-run)
auntie doctor --apply               # act on actionable remediations
auntie up                           # start the first-party PEP 503 server
auntie up <name>                    # start one declared server
auntie up --all                     # first-party server + every supervised declaration
auntie down                         # stop the first-party server
auntie restart <name>               # atomic for systemd-user; stop+start for command
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

# v0.7.0: HTTPS + Basic auth on the first-party server.
# Loopback host (127.0.0.1, ::1, localhost) is always allowed.
# Non-loopback host requires BOTH cert+key AND htpasswd.
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"      # bcrypt-only; populate via `htpasswd -B`
```

> **pip + Basic auth note.** `pip install --index-url
> https://user:pass@host:port/simple/` works but embeds creds in URL,
> leaking them in process listings and pip's debug output. `keyring`
> integration is the long-term answer; in the meantime, an environment-
> scoped per-user `pip.conf` (path resolves via `python -m pip config
> debug`) reduces exposure.

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
