# When to use auntie vs pypiserver / devpi / twine

`auntiepypi` overlaps with several existing tools but targets a
different shape: agent-friendly verbs, a single small mesh-private
index, and lifecycle for whatever's already running. It is not a
drop-in replacement for any of them.

| Tool        | Role                          | auntie's relationship                                               |
|-------------|-------------------------------|---------------------------------------------------------------------|
| pypiserver  | Minimal index daemon          | auntie wraps it as one supported `flavor`; adds detection + lifecycle. |
| devpi       | Multi-index server with mirroring + staging | Different scale tier — auntie is single-index only.              |
| twine       | Upload client for any PyPI-shaped index | `auntie publish` speaks the same wire protocol; either works against an auntie server. |

## vs pypiserver

`pypiserver` is a small, focused PyPI-compatible index daemon. If you
just need an index, `pypiserver` alone is fine — auntie itself
declares it as one of the supported `flavor`s and is happy to detect
and lifecycle-manage a `pypiserver` instance you already run.

Pick auntie over a bare `pypiserver` when you want:

- One config block (`[[tool.auntiepypi.servers]]`) describing every
  index daemon on the host, regardless of flavor.
- `auntie doctor` diagnosing what's down or half-supervised, with
  `--apply` dispatching the right `systemctl --user` invocation.
- `auntie up --all` starting the first-party server plus every
  declared `pypiserver` / `devpi` in one shot.
- The agent-readable verbs (`learn`, `explain`, `--json`) for
  programmatic use.

If none of those matter, run `pypiserver` directly.

## vs devpi

`devpi` is a much larger system: a multi-index server with mirroring,
staging, per-user namespaces, and a release-promotion pipeline. It is
the right answer for an organisation that needs proper package
promotion (dev → staging → release) or transparent mirroring of
upstream PyPI.

auntie is intentionally smaller. The first-party server is a single
read+write index, mesh-private by default, with no mirroring and no
multi-index namespacing. Pick devpi for org-scale package pipelines;
pick auntie for a loopback or small-mesh slice where the simpler
mental model is the point. auntie can also detect and lifecycle a
declared `devpi-server` instance — the two coexist fine.

## vs twine

`twine` and `auntie publish` solve the same problem on the wire: both
POST a `multipart/form-data` body with `:action=file_upload` to a
PyPI-shaped index. The auntie server accepts twine, flit, hatch, and
`auntie publish` interchangeably — pick whichever fits the
publisher's environment.

Pick `auntie publish` over `twine` when:

- The publisher is already inside the auntie CLI (one less tool in
  the agent's path).
- Credentials live in `$AUNTIE_PUBLISH_USER` / `$AUNTIE_PUBLISH_PASSWORD`
  and you want consistent exit-code semantics with the rest of
  `auntie *`.
- You're targeting an auntie server and want the flag set to match
  (`AUNTIE_INSECURE_SKIP_VERIFY=1` for self-signed, etc.).

Pick `twine` when:

- You're publishing to upstream PyPI / TestPyPI as well, and want one
  client across all targets.
- You want twine's release-engineering ergonomics (sign, check
  metadata, etc.) — `auntie publish` is intentionally minimal.

There is no lock-in either way: every artifact uploaded via one
client is downloadable by anything that speaks PEP 503.
