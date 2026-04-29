"""Markdown catalog for ``agentpypi explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty
tuple and ``("agentpypi",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# agentpypi

agentpypi is both a CLI and an agent that maintains, uses, and serves
the CLI for managing PyPI packages. It supports remote (pypi.org) today
and local (mesh-hosted) indexes in future milestones. It overviews
packages — informational, not gating.

## Verbs

- `agentpypi learn` — structured self-teaching prompt.
- `agentpypi explain <path>` — markdown docs for any noun/verb.
- `agentpypi overview [TARGET]` — composite: packages dashboard + local
  server probes. With TARGET, drills into one server flavor or one
  configured package.
- `agentpypi packages overview [PKG]` — read-only PyPI maturity dashboard
  (no arg) or per-package deep-dive (with arg).
- `agentpypi doctor [--fix]` — probe + diagnose; `--fix` starts servers.
- `agentpypi whoami` — auth/env probe; reports configured indexes.

## Planned

- `agentpypi local serve | upload | mirror` — v0.2.0
- `agentpypi servers …` — v0.2.0 (formal home for server lifecycle)

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `agentpypi explain learn`
- `agentpypi explain explain`
- `agentpypi explain overview`
- `agentpypi explain packages`
- `agentpypi explain packages overview`
- `agentpypi explain doctor`
- `agentpypi explain whoami`
- `agentpypi explain local`
"""

_LEARN = """\
# agentpypi learn

Prints a structured self-teaching prompt covering agentpypi's purpose,
command map, exit-code policy, `--json` support, and `explain` pointer.

## Usage

    agentpypi learn
    agentpypi learn --json

The JSON payload includes a `planned` array enumerating verbs that are
catalog-known but not yet registered as argparse subcommands. An agent
consuming `learn --json` can therefore reason about the roadmap without
chasing a separate doc.
"""

_EXPLAIN = """\
# agentpypi explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help`
(terse, positional), `explain` is global and addressable by path.

## Usage

    agentpypi explain agentpypi
    agentpypi explain learn
    agentpypi explain overview
    agentpypi explain --json overview

Unknown paths exit `1` with `error: no explain entry for: <path>` and a
`hint:` line listing the discovery command.
"""

_OVERVIEW = """\
# agentpypi overview

Composite report. With no arg: emits a packages dashboard (one section
per configured package) plus the local PyPI server probes (one section
per known flavor). With an arg, drills into one server flavor or one
configured package, in that priority.

Recognised server flavors:

- `devpi` on port `3141` (`/+api`)
- `pypiserver` on port `8080` (`/`)

Read-only — no mutation flags. Use `agentpypi doctor --fix` to start
servers.

## Usage

    agentpypi overview
    agentpypi overview --json
    agentpypi overview <server-flavor>      # e.g. `devpi`
    agentpypi overview <configured-pkg>     # e.g. `requests`

## JSON envelope

    {
      "subject": "agentpypi",
      "sections": [
        {"category": "packages", "title": "<pkg>", "light": "green|...", "fields": [...]},
        {"category": "servers",  "title": "<flavor>", "light": "...", "fields": [...]}
      ]
    }

## Exit codes

- `0` always.
"""

_DOCTOR = """\
# agentpypi doctor

Same probes as `overview`, plus per-server diagnoses (`port in use`,
`unexpected response`, `server not installed`). Default is dry-run: prints
the would-be remediation command. With `--fix`, runs each server's
configured `start_command`.

## Usage

    agentpypi doctor                # dry-run; no mutations
    agentpypi doctor --fix          # start any server reporting `down`
    agentpypi doctor --json
    agentpypi doctor --fix --json

## Exit codes

- `0` all servers healthy (or `--fix` brought every reporting `down` server up).
- `2` a `--fix` attempt failed (e.g. `start_command` not on `$PATH`).
"""

_WHOAMI = """\
# agentpypi whoami

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

    agentpypi whoami
    agentpypi whoami --json

Read-only.
"""

_PACKAGES = """\
# agentpypi packages

Read-only verbs against PyPI for the configured set of packages.

The configured set lives in `pyproject.toml`:

    [tool.agentpypi]
    packages = ["pkg-a", "pkg-b"]

## Verbs

- `agentpypi packages overview` — dashboard over all configured packages.
- `agentpypi packages overview <pkg>` — deep-dive over the rubric for one.

Read-only by design. Reports — never gates. Exit code is `0` regardless
of how many packages roll up `red`.
"""

_PACKAGES_OVERVIEW = """\
# agentpypi packages overview

Roll-up dashboard over the configured package list, or per-package
deep-dive when called with an argument.

## Usage

    agentpypi packages overview            # dashboard
    agentpypi packages overview <pkg>      # deep-dive
    agentpypi packages overview --json
    agentpypi packages overview <pkg> --json

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
- `1` on missing config (no `[tool.agentpypi].packages`) or invalid name.
- `2` only if every fetch failed.
"""

_LOCAL = """\
# agentpypi local (planned, v0.2.0)

Run / mirror / publish to an in-mesh PyPI index so AgentCulture agents can
exchange wheels without leaving the org's trust boundary.

This noun is **not yet registered**. v0.1.0 ships `overview`, `doctor`,
and `packages overview` — the first two probe localhost for PyPI server
flavors; the third reports on remote PyPI packages. None of them manage
a local index yet.

## Planned verbs

- `agentpypi local serve` — foreground PEP 503 simple index.
- `agentpypi local upload PATH [--apply]` — publish a wheel/sdist.
- `agentpypi local mirror PACKAGE [--apply]` — snapshot a public package.
- `agentpypi local list` — show locally hosted distributions.

Track at https://github.com/agentculture/agentpypi/milestones — milestone
v0.2.0.
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("agentpypi",): _ROOT,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("whoami",): _WHOAMI,
    ("packages",): _PACKAGES,
    ("packages", "overview"): _PACKAGES_OVERVIEW,
    ("local",): _LOCAL,
}
