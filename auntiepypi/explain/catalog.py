"""Markdown catalog for ``auntie explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty
tuple, ``("auntiepypi",)``, and ``("auntie",)`` all resolve to the root
entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# auntie

auntie (Python distribution: `auntiepypi`) is both a CLI and an agent
that maintains, uses, and serves the CLI for managing PyPI packages. It
overviews packages on pypi.org and detects PyPI-flavored servers running
locally. Informational, not gating.

## Verbs

- `auntie learn` — structured self-teaching prompt.
- `auntie explain <path>` — markdown docs for any noun/verb.
- `auntie overview [TARGET]` — composite: packages dashboard + detected
  local servers. With TARGET, drills into a detection name, bare flavor
  alias (`devpi` / `pypiserver`), or configured package. `--proc` opts
  into a /proc scan (Linux only).
- `auntie doctor [TARGET] [--apply] [--decide KEY=VALUE] [--json]` —
  probe + diagnose declared inventory; `--apply` starts servers and
  deletes half-supervised entries; `--decide` resolves ambiguous cases.
- `auntie up [name | --all]` — start a server. Bare form starts the
  first-party PEP 503 simple-index (v0.6.0+); a `<name>` targets one
  declared `[[tool.auntiepypi.servers]]`; `--all` aggregates the
  first-party server plus every supervised declaration.
- `auntie down [name | --all]` — stop a server. Same target shape as
  `up`. For `command` strategy: SIGTERM with 5 s grace, SIGKILL
  fallback.
- `auntie restart [name | --all]` — atomic restart for `systemd-user`,
  stop+start for `command`. Always re-spawns from the current
  `pyproject.toml` argv (or `[tool.auntiepypi.local]` for the bare
  form).
- `auntie publish <path>` — upload a wheel/sdist to the configured
  local index. Requires `publish_users` allowlist + htpasswd creds
  via `$AUNTIE_PUBLISH_USER` / `$AUNTIE_PUBLISH_PASSWORD`.
- `auntie whoami` — auth/env probe; reports configured indexes.

## Console scripts

The package installs two scripts that point at the same entry point:

- `auntie` — preferred.
- `auntiepypi` — alias kept for backward compatibility.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `auntie explain learn`
- `auntie explain explain`
- `auntie explain overview`
- `auntie explain doctor`
- `auntie explain up`
- `auntie explain down`
- `auntie explain restart`
- `auntie explain publish`
- `auntie explain whoami`
"""

_LEARN = """\
# auntie learn

Prints a structured self-teaching prompt covering auntie's purpose,
command map, exit-code policy, `--json` support, and `explain` pointer.

## Usage

    auntie learn
    auntie learn --json

The JSON payload's `planned` array is empty in v0.2.0+: no nouns or
verbs are catalog-known but unregistered. Future milestones repopulate
it as new work lands.
"""

_EXPLAIN = """\
# auntie explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help`
(terse, positional), `explain` is global and addressable by path.

## Usage

    auntie explain auntiepypi
    auntie explain learn
    auntie explain overview
    auntie explain --json overview

Unknown paths exit `1` with `error: no explain entry for: <path>` and a
`hint:` line listing the discovery command.
"""

_OVERVIEW = """\
# auntie overview

Composite report. With no arg: emits a packages dashboard (one section
per configured package) plus the detected-servers report (one section
per declared server, default-port find, and — when `--proc` is on —
each /proc-discovered process). With an arg, drills into one detection,
bare flavor alias, or configured package, in that priority.

## Detection sources

- **Declared inventory** — `[[tool.auntiepypi.servers]]` in pyproject.toml.
  Probes each declared host:port; carries `managed_by` / `unit` /
  `dockerfile` / etc. through to the JSON envelope.
- **Default port scan** — probes `127.0.0.1:3141` (devpi) and
  `127.0.0.1:8080` (pypiserver), skipping any (host, port) already
  covered by declarations. When declarations exist, `absent` results
  from the scan are suppressed (so a declared-only user doesn't see
  noisy `pypiserver:8080 absent` rows when their server is on 8081).
- **`/proc` scan** — opt-in via `--proc` (CLI) or
  `[tool.auntiepypi].scan_processes = true` (config). Linux-only;
  no-op elsewhere. Enriches existing detections with PIDs; appends
  proc-only finds.

## Target resolution priority

1. Exact detection name (declared `name` or auto-name `<flavor>:<port>`).
2. Bare flavor alias (`pypiserver` / `devpi` -> first detection of that
   flavor).
3. Configured package name.
4. Zero-target report (stderr warning + exit 0).

## Usage

    auntie overview
    auntie overview --json
    auntie overview --proc
    auntie overview <detection-name>          # e.g. `main` or `pypiserver:8080`
    auntie overview <flavor>                  # e.g. `pypiserver`
    auntie overview <configured-pkg>          # e.g. `requests`

## JSON envelope

    {
      "subject": "auntie",
      "sections": [
        {"category": "packages", "title": "<pkg>", "light": "...", "fields": [...]},
        {"category": "servers",  "title": "<name>", "light": "...", "fields": [...]}
      ]
    }

## Remediation for `status: absent`

See `docs/deploy/` for systemd-user unit templates that run pypiserver /
devpi as background services. Use `auntie doctor --apply` to start
declared servers.

## Exit codes

- `0` always (read-only; reds do not change the exit).
- `1` malformed `[[tool.auntiepypi.servers]]`.
- `2` only if every detector failed to run.
"""

_DOCTOR = """\
# auntie doctor

Detects the declared inventory (via `_detect/`), then adds per-server
diagnoses (`port in use`, `unexpected response`, `server not installed`,
`half-supervised`, `ambiguous`). Default is dry-run: prints the
would-be remediation for each entry.

With `--apply`, doctor acts on each actionable entry:

- **actionable** — declared, status ≠ up, strategy implemented
  (`systemd-user` or `command`): spawns the server, then re-probes
  within 5 s.
- **half-supervised** — `managed_by` set but required companion field
  missing (e.g. `managed_by=systemd-user` without `unit`): deletes the
  whole `[[tool.auntiepypi.servers]]` entry from `pyproject.toml`.
  A numbered `.bak` file is written before any mutation.
- **ambiguous** — duplicate `name` values: `--apply` without `--decide`
  prints instructions and exits `0`; with `--decide`, deletes the
  non-kept entry.
- **skip** — `manual`, unset `managed_by`, unimplemented strategies
  (`docker` / `compose`), undeclared scan-found: passed through
  unchanged.

## TARGET drill-down

With a positional `TARGET`, doctor filters to the single declared entry
whose `name` matches. Unknown TARGET → stderr warning + exit `0`
(mirrors `overview` zero-target behavior).

## `--decide`

Resolves ambiguous cases. Repeatable. v0.4.0 ships one decision type:

    --decide=duplicate:NAME=N    # keep the Nth occurrence (1-based)

Unknown decision keys exit `1` with the list of known types. Stale
decisions (ambiguity no longer present) are silently ignored so
re-runs stay idempotent.

## Backups

Before any mutation, doctor writes `pyproject.toml.<N>.bak` (next free
numbered slot). On `.bak` slot exhaustion (> 5 retries): exits `1` with
a remediation hint to clean up old `.bak` files.

## Usage

    auntie doctor                                  # dry-run; explain everything
    auntie doctor main                             # drill into one entry
    auntie doctor --apply                          # commit; spawns + deletes half-supervised
    auntie doctor --apply --decide=duplicate:main=1
    auntie doctor --json                           # for piping to jq

## Exit codes

- `0` — dry-run completed; `--apply` brought every actionable server
  up; ambiguous cases deferred via `--decide`; unknown TARGET (stderr
  warning).
- `1` — configuration / usage error (cross-field validation, unknown
  `--decide` key, unparseable block, `.bak` slot exhaustion).
- `2` — `--apply` ran but at least one actionable entry is still not
  `up` after the strategy + re-probe.
"""

_LIFECYCLE_PREAMBLE = """\
The lifecycle verbs (`up`, `down`, `restart`) operate on three classes of
target:

- The **first-party server** — auntie's own PEP 503 simple-index,
  configured by `[tool.auntiepypi.local]`. Default port 3141; default
  wheelhouse `$XDG_DATA_HOME/auntiepypi/wheels/`. Loopback-only by
  default; non-loopback bind requires both TLS (`cert` + `key`) and
  HTTP Basic auth (`htpasswd`, bcrypt-only) configured together.
- A **named declaration** in `[[tool.auntiepypi.servers]]` whose
  `managed_by` is `systemd-user` or `command`.
- All supervised targets at once via `--all`.

Other modes (`manual`, `docker`, `compose`, unset) are out-of-scope and
refused with a clear error. The name `"auntie"` is reserved — declared
specs that use it are rejected.

## Common shape

    auntie <verb>                       # first-party server
    auntie <verb> <name>                # one declared server
    auntie <verb> --all                 # first-party + every supervised
    auntie <verb> --json                # JSON envelope
    auntie <verb> --decide=duplicate:NAME=N <name>

## Exit codes

- `0` — every targeted server reached the desired state
- `1` — user / config error before any action attempted
- `2` — at least one targeted server did not reach the desired state
"""

_UP = """\
# auntie up

Start a server.

%s

## What it does

- **bare** (`auntie up`) → start the first-party PEP 503 simple-index
  on `[tool.auntiepypi.local].host:port`. The auntie strategy spawns
  `python -m auntiepypi._server --host H --port P --root R` detached
  and tracks it via `auntie_<port>.pid`. The wheelhouse is created
  with `mkdir -p` if missing.
- `managed_by = "systemd-user"` → `systemctl --user start <unit>` +
  re-probe (5 s budget; "up" wins).
- `managed_by = "command"` → detached `Popen` with
  `start_new_session=True`; logs to
  `$XDG_STATE_HOME/auntiepypi/<slug>.log`; on success writes
  `<slug>_<port>.pid` + `<slug>_<port>.json` sidecar so future
  `auntie down` / `restart` can find the process.
- Idempotent: an already-up server is a successful no-op.

## Drift handling

A stale PID file (PID dead) on `up` is silently cleared before the
fresh spawn.
""" % _LIFECYCLE_PREAMBLE

_DOWN = """\
# auntie down

Stop a server.

%s

## What it does

- **bare** (`auntie down`) → stop the first-party PEP 503 simple-index.
  Reads `auntie_<port>.pid`, SIGTERMs, escalates to SIGKILL if needed,
  clears the PID file. Idempotent.
- `managed_by = "systemd-user"` → `systemctl --user stop <unit>` +
  re-probe with `desired="down"`.
- `managed_by = "command"` → read `<slug>_<port>.pid`; SIGTERM; poll
  the port for up to 5 s; if still bound, SIGKILL with another 2 s
  grace.
- Fallback: when no PID file exists (Linux only), walks
  `/proc/net/tcp` + `/proc/<pid>/fd/*` to find the listener on the
  declared port. Refuses to kill unless the discovered process's argv
  matches the declared `command` (footgun guard against killing an
  unrelated process bound to the same port).
- Idempotent: nothing-to-stop is `ok=True, detail="already stopped"`.

## When refused

If the port is up but the discovered argv doesn't match, exit `2`
with `port <N> listener argv does not match declaration; refusing to
kill`. Inspect with `auntie overview --proc`.
""" % _LIFECYCLE_PREAMBLE

_RESTART = """\
# auntie restart

Restart a server.

%s

## What it does

- **bare** (`auntie restart`) → stop + start the first-party server
  using the current `[tool.auntiepypi.local]` config (so a port or
  wheelhouse change between starts takes effect on restart).
- `managed_by = "systemd-user"` → `systemctl --user restart <unit>`
  (atomic; faster and safer than stop+start).
- `managed_by = "command"` → `down` then `up`. The new spawn re-uses
  the **current** `[[tool.auntiepypi.servers]].command`, never the
  sidecar argv. If the sidecar argv differs from the current spec,
  a single `argv changed since last start` line is appended to the
  log (advisory; no failure).

## Drift policy

Source of truth is always current `pyproject.toml`. Edit your
`command` array (or `[tool.auntiepypi.local]` for the first-party
server), then `auntie restart [<name>]`.
""" % _LIFECYCLE_PREAMBLE

_WHOAMI = """\
# auntie whoami

Auth / environment probe. Reports which PyPI, TestPyPI, and local index
the current shell environment is pointing at. Cross-references the same
probe machinery `overview` uses to flag local indexes that are
*configured* but *down*.

## Sources inspected

- `$PIP_INDEX_URL`, `$PIP_EXTRA_INDEX_URL`
- `$UV_INDEX_URL`, `$UV_EXTRA_INDEX_URL`
- `~/.config/pip/pip.conf` `[global] index-url` / `extra-index-url`
- Active virtualenv (`$VIRTUAL_ENV`) and uv project (`$UV_PROJECT_ENVIRONMENT`)
- Local probes (cross-reference with `overview`)

## Usage

    auntie whoami
    auntie whoami --json

Read-only.
"""

_PUBLISH = """\
# auntie publish

Upload a wheel or sdist to the configured local index
(`[tool.auntiepypi.local]`).

Uses the legacy PyPI upload protocol (`POST /` with
`multipart/form-data`, `:action=file_upload`) — twine, flit, hatch,
and the v0.8.0 first-party server all speak it.

## Authorization

The server requires both authentication AND an authz allowlist:

    [tool.auntiepypi.local]
    htpasswd      = "/etc/auntie/htpasswd"
    publish_users = ["alice", "bob"]

`publish_users` empty / unset → no one publishes (read-only mode
preserved). `publish_users` set + caller in the list → upload
accepted.

## Credentials

Read from environment, then prompt:

- `$AUNTIE_PUBLISH_USER` (or `input("user: ")`)
- `$AUNTIE_PUBLISH_PASSWORD` (or `getpass.getpass()`)

Non-TTY environments without env vars set exit 2 (no silent block).

## Usage

    auntie publish dist/mypkg-1.0-py3-none-any.whl
    auntie publish dist/mypkg-1.0.tar.gz --json

## TLS

When `[tool.auntiepypi.local].cert` and `.key` are set, the URL
becomes `https://...`. Verification is on by default; for self-signed
certs, set `AUNTIE_INSECURE_SKIP_VERIFY=1` (a stderr warning fires
each invocation).

## Exit codes

- 0 — server accepted (HTTP 2xx).
- 1 — server rejected (HTTP 4xx / 5xx).
  Common: 401 (bad creds), 403 (user not in `publish_users`,
  or `publish_users` empty), 409 (file already exists — pick a new
  version), 413 (over `max_upload_bytes`).
- 2 — transport error (DNS / connect / TLS) or local file problem
  (path missing, unrecognized distribution filename).

No yank/delete: to retract a wheel, the operator deletes the file
from `cfg.root` directly. v0.8.0 does not provide a delete API.
"""

ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("auntiepypi",): _ROOT,
    ("auntie",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("up",): _UP,
    ("down",): _DOWN,
    ("restart",): _RESTART,
    ("publish",): _PUBLISH,
    ("whoami",): _WHOAMI,
}
