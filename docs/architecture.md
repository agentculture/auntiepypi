# Architecture and data flow

`auntiepypi` is a CLI plus a local HTTP server. The CLI inspects PyPI
and your local machine; the server hosts a private PEP 503 simple
index. State lives in two places — `pyproject.toml` (declared
inventory + first-party server config) and the wheelhouse directory
(`$XDG_DATA_HOME/auntiepypi/wheels/` by default). There is no hidden
global state.

## Bird's-eye view

```text
                          ┌──────────────────────────┐
   user / agent  ──────►  │  auntie <verb> [args]    │
                          │  (auntiepypi.cli)        │
                          └──────────────┬───────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
      ┌──────────────┐          ┌────────────────┐         ┌────────────────┐
      │  _detect/    │          │  _actions/     │         │  _server/      │
      │  read-only   │          │  start/stop    │         │  HTTP listener │
      │  inventory   │          │  process state │         │  PEP 503 +     │
      │  + probes    │          │  + pyproject   │         │  POST upload   │
      └──────┬───────┘          └────────┬───────┘         └────────┬───────┘
             │                           │                          │
             ▼                           ▼                          ▼
     ┌──────────────┐           ┌────────────────┐          ┌────────────────┐
     │ pyproject.toml│          │ pyproject.toml │          │ wheels/ dir    │
     │ (read)       │           │ (.bak snapshots│          │ (read + write) │
     │ pypi.org     │           │  before edit)  │          │ htpasswd, cert │
     │ /proc, ports │           │ PID files      │          │ (read)         │
     └──────────────┘           └────────────────┘          └────────────────┘
```

The CLI dispatcher is `auntiepypi.cli:main`. Each verb is a small
module under `auntiepypi/cli/_commands/` that delegates the heavy
lifting to one of the three packages above. `auntie learn` and
`auntie explain` are pure reads of the in-process `explain/catalog.py`
catalog — no network, no filesystem.

## What each module owns

**`auntiepypi/_detect/`** — read-only inventory. `_declared.py` parses
`[[tool.auntiepypi.servers]]`. `_port.py` probes the canonical
`devpi` (3141) and `pypiserver` (8080) ports. `_proc.py` walks
`/proc` (Linux only, opt-in via `--proc`) for matching argvs.
`_local.py` emits the auntie-flavored detection for the first-party
server. Together they feed `auntie overview` and the diagnosis phase
of `auntie doctor`.

**`auntiepypi/_actions/`** — process and config mutators.
`systemd_user.py` shells out to `systemctl --user`. `command.py`
spawns a subprocess from a declared `command = [...]` argv and tracks
the PID via a sidecar file. `auntie.py` wraps `command.py` with the
derived `python -m auntiepypi._server` argv. Every config edit
(`--apply` deletes a half-supervised entry; `--decide` resolves a
duplicate) writes a numbered `pyproject.toml.<N>.bak` snapshot first;
rollback is one `mv`.

**`auntiepypi/_server/`** — the first-party HTTP listener.
`_app.py` is the request handler factory. `_wheelhouse.py` enumerates
distribution files. `_auth.py` parses htpasswd (bcrypt-only) and
verifies HTTP Basic. `_tls.py` builds the `ssl.SSLContext`.
`_multipart.py` parses twine-shape upload bodies via stdlib
`email.parser.BytesParser`. `_publish.py` writes uploads atomically
via `tempfile.NamedTemporaryFile + os.rename`. `_config.py` is the
frozen `LocalConfig` dataclass.

## Where state lives

| Surface           | Owner                  | Read by                      | Mutated by                          |
|-------------------|------------------------|------------------------------|-------------------------------------|
| `pyproject.toml`  | the user / operator    | every verb                   | `auntie doctor --apply`, `--decide` |
| `wheels/` dir     | the first-party server | `auntie up` (serve), `pip`   | `auntie publish`, `twine upload`    |
| `htpasswd`, certs | the operator           | `auntie up` (load at start)  | never (out-of-band)                 |
| PID files         | `_actions/command.py`  | `auntie down`, `restart`     | `auntie up`, `down`, `restart`      |
| `.bak` snapshots  | `auntie doctor --apply`| rollback                     | `auntie doctor --apply` only        |

## Read-only vs write-capable, by surface

| Verb                              | Mutates                                  |
|-----------------------------------|------------------------------------------|
| `learn`, `explain`, `whoami`      | nothing (pure reads)                     |
| `overview`                        | nothing (probes pypi.org + local ports)  |
| `doctor` (no `--apply`)           | nothing (dry-run report)                 |
| `doctor --apply`                  | process state + `pyproject.toml`         |
| `up`, `down`, `restart`           | process state                            |
| `publish`                         | the package index (wheels directory)     |

`overview`, `learn`, `explain`, and `whoami` never write to disk and
never bind a port. `doctor` is dry-run by default; the `--apply`
opt-in is the only path that writes `pyproject.toml`. `up` / `down` /
`restart` only touch process state and PID files. `publish` is the
only verb that can change the contents of the package index — and
only against a server whose operator has opted in via `publish_users`.

## Network surface

The first-party server (`auntie up`) binds to `127.0.0.1:3141` by
default. PEP 503 routes (`GET /simple/`, `GET /simple/<pkg>/`,
`GET /files/<filename>`) are open to any client that can reach the
socket. The legacy upload route (`POST /`) is gated by HTTP Basic
auth plus the `publish_users` allowlist. Public (non-loopback)
binding is rejected at config-load time unless both TLS (cert+key)
and auth (htpasswd) are configured — see [`security.md`](security.md)
for the truth table and rationale.

## See also

- [`about.md`](about.md) — non-technical explainer.
- [`security.md`](security.md) — security model and defaults.
- [`comparison.md`](comparison.md) — when to pick auntie vs
  pypiserver / devpi / twine.
- [`superpowers/specs/`](superpowers/specs/) — design docs per
  milestone (architecture decisions and rationale).
