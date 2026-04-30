# auntiepypi — deployment templates

`auntie overview` detects what's running. `auntie doctor --apply` can
start what's down. To supervise a local PyPI server persistently, use
the systemd-user unit templates in this directory.

## Why systemd-user?

A user-scoped unit needs no root, persists across logins (with
`loginctl enable-linger <user>`), and pairs directly with `auntie
doctor`'s `systemd-user` action strategy — `--apply` calls
`systemctl --user start <unit>` and re-probes.

## Templates

- [`pypi-server.service`](pypi-server.service) — `pypi-server` on port 8080.
- [`devpi.service`](devpi.service) — `devpi-server` on port 3141.

Both contain inline install + declaration instructions.

## After install

Add a matching `[[tool.auntiepypi.servers]]` block to your project's
`pyproject.toml` so `auntie overview` reports it as `declared` and
`auntie doctor` knows how to manage it:

```toml
[[tool.auntiepypi.servers]]
name = "main"
flavor = "pypiserver"
port = 8080
managed_by = "systemd-user"
unit = "pypi-server.service"
```

`auntie overview --json | jq` will then show the server with
`source: "declared"` and the `unit` field echoed through.

## Use with `auntie doctor`

Once you have a unit installed and a declaration in `pyproject.toml`,
`auntie doctor` can diagnose and start the server for you:

```bash
$ auntie doctor
# auntie doctor
summary: 1 actionable, 0 half-supervised, 0 skip, 0 ambiguous (1 total)

  main          down     declared    managed_by=systemd-user
      diagnosis: down; would dispatch managed_by='systemd-user'
      remediation: auntie doctor --apply

(dry-run; pass --apply to act on 1 remediation)

$ auntie doctor --apply
# auntie doctor --apply
wrote pyproject.toml.1.bak (rollback: mv pyproject.toml.1.bak pyproject.toml)
dispatching systemd-user: systemctl --user start pypi-server.service
re-probe main: up
summary: 0 actionable, 0 half-supervised, 0 skip, 0 ambiguous (1 total)
```

If the `unit` field is missing from the declaration, doctor classifies
the entry as `half-supervised` and `--apply` will remove it from
`pyproject.toml` (after writing a `.bak`). Add `unit = "…"` to keep
the entry under supervision.
