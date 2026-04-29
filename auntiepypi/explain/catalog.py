"""Markdown catalog for ``auntiepypi explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty
tuple and ``("auntiepypi",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# auntiepypi

auntiepypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## Verbs

- `auntiepypi learn` — structured self-teaching prompt.
- `auntiepypi explain <path>` — markdown docs for any noun/verb.
- `auntiepypi overview [TARGET]` — composite: packages dashboard + local
  server probes. With TARGET, drills into one server flavor or one
  configured package.
- `auntiepypi packages overview [PKG]` — read-only PyPI maturity dashboard
  (no arg) or per-package deep-dive (with arg).
- `auntiepypi doctor [--fix]` — probe + diagnose; `--fix` starts servers.
- `auntiepypi whoami` — auth/env probe; reports configured indexes.

## Planned

- `auntiepypi local serve | upload | mirror` — v0.2.0
- `auntiepypi servers …` — v0.2.0 (formal home for server lifecycle)

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `auntiepypi explain learn`
- `auntiepypi explain explain`
- `auntiepypi explain overview`
- `auntiepypi explain packages`
- `auntiepypi explain packages overview`
- `auntiepypi explain doctor`
- `auntiepypi explain whoami`
- `auntiepypi explain local`
"""

_LEARN = """\
# auntiepypi learn

Prints a structured self-teaching prompt covering auntiepypi's purpose,
command map, exit-code policy, `--json` support, and `explain` pointer.

## Usage

    auntiepypi learn
    auntiepypi learn --json

The JSON payload includes a `planned` array enumerating verbs that are
catalog-known but not yet registered as argparse subcommands. An agent
consuming `learn --json` can therefore reason about the roadmap without
chasing a separate doc.
"""

_EXPLAIN = """\
# auntiepypi explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help`
(terse, positional), `explain` is global and addressable by path.

## Usage

    auntiepypi explain auntiepypi
    auntiepypi explain learn
    auntiepypi explain overview
    auntiepypi explain --json overview

Unknown paths exit `1` with `error: no explain entry for: <path>` and a
`hint:` line listing the discovery command.
"""

_OVERVIEW = """\
# auntiepypi overview

Composite report. With no arg: emits a packages dashboard (one section
per configured package) plus the local PyPI server probes (one section
per known flavor). With an arg, drills into one server flavor or one
configured package, in that priority.

Recognised server flavors:

- `devpi` on port `3141` (`/+api`)
- `pypiserver` on port `8080` (`/`)

Read-only — no mutation flags. Use `auntiepypi doctor --fix` to start
servers.

## Usage

    auntiepypi overview
    auntiepypi overview --json
    auntiepypi overview <server-flavor>      # e.g. `devpi`
    auntiepypi overview <configured-pkg>     # e.g. `requests`

## JSON envelope

    {
      "subject": "auntiepypi",
      "sections": [
        {"category": "packages", "title": "<pkg>", "light": "green|...", "fields": [...]},
        {"category": "servers",  "title": "<flavor>", "light": "...", "fields": [...]}
      ]
    }

## Exit codes

- `0` always.
"""

_DOCTOR = """\
# auntiepypi doctor

Same probes as `overview`, plus per-server diagnoses (`port in use`,
`unexpected response`, `server not installed`). Default is dry-run: prints
the would-be remediation command. With `--fix`, runs each server's
configured `start_command`.

## Usage

    auntiepypi doctor                # dry-run; no mutations
    auntiepypi doctor --fix          # start any server reporting `down`
    auntiepypi doctor --json
    auntiepypi doctor --fix --json

## Exit codes

- `0` all servers healthy (or `--fix` brought every reporting `down` server up).
- `2` a `--fix` attempt failed (e.g. `start_command` not on `$PATH`).
"""

_WHOAMI = """\
# auntiepypi whoami

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

    auntiepypi whoami
    auntiepypi whoami --json

Read-only.
"""

_PACKAGES = """\
# auntiepypi packages

Read-only verbs against PyPI for the configured set of packages.

The configured set lives in `pyproject.toml`:

    [tool.auntiepypi]
    packages = ["pkg-a", "pkg-b"]

## Verbs

- `auntiepypi packages overview` — dashboard over all configured packages.
- `auntiepypi packages overview <pkg>` — deep-dive over the rubric for one.

Read-only by design. Reports — never gates. Exit code is `0` regardless
of how many packages roll up `red`.
"""

_PACKAGES_OVERVIEW = """\
# auntiepypi packages overview

Roll-up dashboard over the configured package list, or per-package
deep-dive when called with an argument.

## Usage

    auntiepypi packages overview            # dashboard
    auntiepypi packages overview <pkg>      # deep-dive
    auntiepypi packages overview --json
    auntiepypi packages overview <pkg> --json

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

_LOCAL = """\
# auntiepypi local (planned, v0.2.0)

Run / mirror / publish to an in-mesh PyPI index so AgentCulture agents can
exchange wheels without leaving the org's trust boundary.

This noun is **not yet registered**. v0.1.0 ships `overview`, `doctor`,
and `packages overview` — the first two probe localhost for PyPI server
flavors; the third reports on remote PyPI packages. None of them manage
a local index yet.

## Planned verbs

- `auntiepypi local serve` — foreground PEP 503 simple index.
- `auntiepypi local upload PATH [--apply]` — publish a wheel/sdist.
- `auntiepypi local mirror PACKAGE [--apply]` — snapshot a public package.
- `auntiepypi local list` — show locally hosted distributions.

Track at https://github.com/agentculture/auntiepypi/milestones — milestone
v0.2.0.
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("auntiepypi",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("whoami",): _WHOAMI,
    ("packages",): _PACKAGES,
    ("packages", "overview"): _PACKAGES_OVERVIEW,
    ("local",): _LOCAL,
}
