"""Markdown catalog for ``agentpypi explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty
tuple and ``("agentpypi",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# agentpypi

agentpypi manages both ends of the Python distribution pipe for the
AgentCulture mesh: an in-mesh local PyPI index for intra-org wheels, and
release orchestration for AgentCulture siblings against PyPI / TestPyPI.

v0.0.1 ships local-host introspection plus the agent-affordance verbs.
The `online` and `local` noun groups are planned for later milestones.

## Verbs

- `agentpypi learn` — structured self-teaching prompt.
- `agentpypi explain <path>` — markdown docs for any noun/verb.
- `agentpypi overview` — probe localhost for known PyPI server flavors.
- `agentpypi doctor [--fix]` — probe + diagnose; `--fix` starts servers.
- `agentpypi whoami` — auth/env probe; reports configured indexes.

## Planned

- `agentpypi online status SIBLING` — v0.1.0
- `agentpypi online release SIBLING [--apply]` — v0.1.0
- `agentpypi local serve | upload | mirror` — v0.2.0

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `agentpypi explain learn`
- `agentpypi explain explain`
- `agentpypi explain overview`
- `agentpypi explain doctor`
- `agentpypi explain whoami`
- `agentpypi explain online`
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

Probes `127.0.0.1` for known PyPI server flavors and reports up/down/absent.

Recognised flavors:

- `devpi` on port `3141` (`/+api`)
- `pypiserver` on port `8080` (`/`)

Read-only — no mutation flags. Use `agentpypi doctor --fix` to start
servers.

## Usage

    agentpypi overview
    agentpypi overview --json

JSON payload:

    {
      "servers": [
        {"name": "devpi", "port": 3141, "url": "...", "status": "up|down|absent",
         "version": "..."}
      ]
    }

## Exit codes

- `0` always (probe failures are reported as `down`/`absent`, not exit codes).
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

_ONLINE = """\
# agentpypi online (planned, v0.1.0)

Release orchestration for AgentCulture siblings (`afi-cli`, `cfafi`,
`ghafi`, `shushu`, `steward`, `zehut`, …). Reads PyPI + TestPyPI state,
diffs against `CHANGELOG.md` / `main`, and triggers each sibling's
`publish.yml` workflow over OIDC Trusted Publishing.

This noun is **not yet registered** in v0.0.1. The catalog entry exists so
agents querying the roadmap get an honest answer.

## Planned verbs

- `agentpypi online status SIBLING` — read-only diff: PyPI vs CHANGELOG vs
  main vs latest tag.
- `agentpypi online release SIBLING [--apply]` — dry-run by default;
  `--apply` triggers the sibling's `publish.yml`.

Track at https://github.com/agentculture/agentpypi/milestones — milestone
v0.1.0.
"""

_LOCAL = """\
# agentpypi local (planned, v0.2.0)

Run / mirror / publish to an in-mesh PyPI index so AgentCulture agents can
exchange wheels without leaving the org's trust boundary.

This noun is **not yet registered** in v0.0.1. v0.0.1 ships `overview`
and `doctor` instead, which probe localhost for PyPI server flavors but
don't yet manage one.

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
    ("online",): _ONLINE,
    ("local",): _LOCAL,
}
