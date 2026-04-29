# auntiepypi — deployment templates

`auntie overview` is **detect-only**: it reports what's running, it does
not raise servers. To run a local PyPI server in the background, use
the systemd-user unit templates in this directory.

## Why systemd-user?

A user-scoped unit needs no root, persists across logins (with
`loginctl enable-linger <user>`), and is what `auntie` v0.3.0 will
integrate with for lifecycle management. Until then,
`systemctl --user` is the recommended supervisor.

## Templates

- [`pypi-server.service`](pypi-server.service) — `pypi-server` on port 8080.
- [`devpi.service`](devpi.service) — `devpi-server` on port 3141.

Both contain inline install + declaration instructions.

## After install

Add a matching `[[tool.auntiepypi.servers]]` block to your project's
`pyproject.toml` so `auntie overview` reports it as `declared`:

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
