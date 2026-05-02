# auntiepypi

> auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
> that maintains, uses, and serves the CLI for managing PyPI packages.
> It overviews packages on pypi.org, detects PyPI-flavored servers
> running locally, starts/stops/restarts declared servers, and hosts a
> first-party PEP 503 simple-index — informational first, actionable
> on demand.

## What auntie is

A small CLI plus a stable plumbing layer that an agent inside the
AgentCulture mesh can call. Read verbs (`overview`, `learn`,
`explain`, `whoami`) never touch disk or bind ports. Mutation verbs
(`doctor --apply`, `up`, `down`, `restart`, `publish`) do exactly one
thing each, and every dangerous surface (public binding, POST upload,
config edits) requires explicit operator opt-in. The first-party
server runs on loopback by default and stays read-only until
`publish_users` is set. See [`docs/architecture.md`](docs/architecture.md)
for the module map and [`docs/security.md`](docs/security.md) for the
threat model.

## Status

| Version | Capability                                       | Mutates           | Status   |
|---------|--------------------------------------------------|-------------------|----------|
| v0.0.1  | Package skeleton (`learn`, `explain`, `whoami`)  | nothing           | shipped  |
| v0.1.0  | `auntie overview` packages dashboard             | nothing           | shipped  |
| v0.3.0  | `auntie overview` server detection (`_detect/`)  | nothing           | shipped  |
| v0.4.0  | `auntie doctor` lifecycle (`--apply`)            | `pyproject.toml`  | shipped  |
| v0.5.0  | `auntie up` / `down` / `restart` (declared)      | process state     | shipped  |
| v0.6.0  | First-party PEP 503 simple-index (read-only)     | wheelhouse (read) | shipped  |
| v0.7.0  | HTTPS + Basic auth on the first-party server     | nothing           | shipped  |
| v0.8.0  | `auntie publish` — twine-compatible POST upload  | package index     | shipped  |
| v0.8.x  | Keyring / netrc credential plumbing              | nothing           | planned  |
| v0.9.0  | Streaming multipart (multi-GiB ML wheels)        | package index     | planned  |
| v1.0.0  | Mesh-aware: Culture-mesh service-registry discovery | nothing        | planned  |

Roadmap is descriptive of intent, not a commitment.

## Docs

- [`docs/about.md`](docs/about.md) — non-technical explainer.
- [`docs/architecture.md`](docs/architecture.md) — module map, state
  surfaces, read-only vs write-capable verbs.
- [`docs/security.md`](docs/security.md) — defaults, public-binding
  rules, publish authorization, body cap, file permissions.
- [`docs/comparison.md`](docs/comparison.md) — when to pick auntie vs
  pypiserver / devpi / twine.
- [`docs/superpowers/specs/`](docs/superpowers/specs/) — per-milestone
  design docs (decisions and rationale).

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
AUNTIE_PUBLISH_USER=alice \
AUNTIE_PUBLISH_PASSWORD=secret \
  auntie publish dist/mypkg-1.0.whl  # upload via twine-compatible POST (v0.8.0)
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
# v0.8.0: publish_users gates the POST upload endpoint; empty list
# preserves read-only mode. max_upload_bytes caps per-request body.
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"      # bcrypt-only; populate via `htpasswd -B`
publish_users = ["alice", "bob"]       # v0.8.0: who can POST uploads
max_upload_bytes = 104857600           # v0.8.0: 100 MiB default
```

### Publishing a wheel (v0.8.0)

```bash
# Operator: configure auth + publish_users (above), then start the server.
auntie up

# Publisher: build a wheel and upload via auntie's CLI.
uv build
AUNTIE_PUBLISH_USER=alice AUNTIE_PUBLISH_PASSWORD=secret \
  auntie publish dist/mypkg-1.0-py3-none-any.whl
# expect: "published mypkg-1.0-py3-none-any.whl → /files/..."

# Or via twine — the server speaks the legacy PyPI upload protocol.
TWINE_USERNAME=alice TWINE_PASSWORD=secret \
  twine upload --repository-url https://0.0.0.0:3141/ dist/*.whl
```

Self-signed certs need `AUNTIE_INSECURE_SKIP_VERIFY=1` (loud stderr
warning fires on each invocation). Existing-file uploads return 409
(no overwrite, ever — pick a new version).

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
