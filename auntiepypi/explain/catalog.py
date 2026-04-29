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
- `auntie packages overview [PKG]` — read-only PyPI maturity dashboard
  (no arg) or per-package deep-dive (with arg).
- `auntie doctor [--fix]` — probe + diagnose; `--fix` starts servers.
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
- `auntie explain packages`
- `auntie explain packages overview`
- `auntie explain doctor`
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
  `dockerfile` / etc. through to the JSON envelope (reserved for v0.3.0
  lifecycle work).
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
devpi as background services. `auntie` does not start servers itself
(see `auntie doctor --fix` for the existing raise capability).

## Exit codes

- `0` always (read-only; reds do not change the exit).
- `1` malformed `[[tool.auntiepypi.servers]]`.
- `2` only if every detector failed to run.
"""

_DOCTOR = """\
# auntie doctor

Same probes as `overview`, plus per-server diagnoses (`port in use`,
`unexpected response`, `server not installed`). Default is dry-run: prints
the would-be remediation command. With `--fix`, runs each server's
configured `start_command`.

## Usage

    auntie doctor                # dry-run; no mutations
    auntie doctor --fix          # start any server reporting `down`
    auntie doctor --json
    auntie doctor --fix --json

## Exit codes

- `0` all servers healthy (or `--fix` brought every reporting `down` server up).
- `2` a `--fix` attempt failed (e.g. `start_command` not on `$PATH`).
"""

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

_PACKAGES = """\
# auntie packages

Read-only verbs against PyPI for the configured set of packages.

The configured set lives in `pyproject.toml`:

    [tool.auntiepypi]
    packages = ["pkg-a", "pkg-b"]

## Verbs

- `auntie packages overview` — dashboard over all configured packages.
- `auntie packages overview <pkg>` — deep-dive over the rubric for one.

Read-only by design. Reports — never gates. Exit code is `0` regardless
of how many packages roll up `red`.
"""

_PACKAGES_OVERVIEW = """\
# auntie packages overview

Roll-up dashboard over the configured package list, or per-package
deep-dive when called with an argument.

## Usage

    auntie packages overview            # dashboard
    auntie packages overview <pkg>      # deep-dive
    auntie packages overview --json
    auntie packages overview <pkg> --json

## Rubric (deep-dive)

Seven dimensions, each scored pass / warn / fail / unknown, rolled up
to a green / yellow / red / unknown traffic light:

- recency — days since last non-yanked release
- cadence — median gap between last 5 releases
- downloads — pypistats `last_week`
- lifecycle — Trove `Development Status` classifier
- distribution — wheel + sdist availability
- metadata — license / requires_python / Homepage / Source / README
- versioning — PEP 440 maturity

## Exit codes

- `0` always (read-only; reds do not change the exit).
- `1` on missing config (no `[tool.auntiepypi].packages`) or invalid name.
- `2` only if every fetch failed.
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("auntiepypi",): _ROOT,
    ("auntie",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("whoami",): _WHOAMI,
    ("packages",): _PACKAGES,
    ("packages", "overview"): _PACKAGES_OVERVIEW,
}
