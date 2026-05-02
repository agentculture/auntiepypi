# Security model

`auntiepypi` ships with safe defaults: loopback bind, read-only mode,
no auth required for loopback, empty `publish_users` so POST uploads
are disabled even when auth is configured. Every dangerous surface
requires explicit operator opt-in. This page summarises the
guarantees the server enforces and where they live in code.

For the detailed design rationale, see
[`superpowers/specs/2026-05-02-auntiepypi-v0.7.0-tls-auth-design.md`](superpowers/specs/2026-05-02-auntiepypi-v0.7.0-tls-auth-design.md)
and
[`superpowers/specs/2026-05-03-auntiepypi-v0.8.0-publish-design.md`](superpowers/specs/2026-05-03-auntiepypi-v0.8.0-publish-design.md).

## Defaults are safe

- Default bind is `127.0.0.1:3141` (loopback). No remote host can
  connect without explicit reconfiguration.
- No auth required for loopback. Plausible single-user setup.
- `publish_users` is empty by default. With no `htpasswd`
  configured, POST is disabled at the protocol level (405 Method Not
  Allowed). With `htpasswd` configured but `publish_users` empty,
  authenticated POSTs return 403 "publish disabled" — read-only mode
  is preserved either way until an operator names at least one
  publisher.
- Existing files in the wheelhouse are never overwritten. A POST that
  would clobber an existing distribution returns 409 Conflict; the
  publisher must pick a new version.

## Public binding requires both TLS and Basic auth

When `[tool.auntiepypi.local].host` resolves to anything other than
`127.0.0.1` / `::1` / `localhost`, the config loader requires **both**
of:

- `cert` and `key` — operator-supplied PEM paths. Loaded via
  `ssl.SSLContext.load_cert_chain`; minimum version pinned to TLS 1.2.
  auntie does not auto-generate certs.
- `htpasswd` — Apache htpasswd file with bcrypt-only entries
  (`$2y$` / `$2b$` / `$2a$`). Non-bcrypt lines are rejected at load
  time with the offending line number; silent skip would be how an
  auth bypass ships.

Either alone fails fast with `ServerConfigError`. The truth-table
check fires before the listener binds — see `_server/_config.py` and
`_detect/_config.py`.

## Publish authorization is a strict superset of authentication

Every uploader must be both authenticated AND in `publish_users`.
The cross-check fires at config-load time: every name in
`publish_users` must reference an actual htpasswd entry, and a
non-empty `publish_users` without `htpasswd` is rejected.

| State                                              | POST `/` returns      |
|----------------------------------------------------|-----------------------|
| `htpasswd` not configured                          | 405 Method Not Allowed|
| `htpasswd` configured, no/invalid creds            | 401 Unauthorized      |
| valid creds, `publish_users` empty                 | 403 "publish disabled"|
| valid creds, user not in `publish_users`           | 403 "user … cannot publish" |
| valid creds, user in `publish_users`, valid upload | 201 Created           |

## Body cap and atomic writes

`max_upload_bytes` (default 100 MiB) caps every request body. The
cap is enforced **twice**:

- Pre-read via `Content-Length` — a 413 fires before any bytes are
  consumed. `Content-Length` is required (411 Length Required when
  absent); read-until-EOF would block on keep-alive.
- During-read via a counted reader — a lying `Content-Length` cannot
  push past the cap. Truncated bodies surface as 400.

Writes are atomic and no-clobber. `_server/_publish.py` opens
`tempfile.NamedTemporaryFile(dir=root, prefix=".upload-",
suffix=".part")` (same filesystem so the link is atomic), fsyncs,
then commits via `os.link(tmp, target)` — which fails with
`FileExistsError` if the target already exists. `os.link` is the
no-clobber primitive on POSIX; using `os.rename` would have left a
TOCTOU window in which a competing writer could materialise the
target between an existence check and the rename. Errors during
write unlink the temp; partial uploads never litter the wheelhouse.

## Basic auth caveat (pip URL-embedded credentials)

`pip install --index-url https://user:pass@host:port/simple/` works,
but credentials in URLs leak into process listings, shell history,
and pip's own debug output. Until keyring integration lands
(planned post-v0.8.0), prefer a per-user `pip.conf` with restrictive
permissions (`python -m pip config debug` shows the resolved path):

```ini
[global]
index-url = https://alice:secret@auntie.example.lan:3141/simple/
```

The same caveat applies to `twine upload --repository-url` URLs.
For `auntie publish`, credentials come from
`$AUNTIE_PUBLISH_USER` / `$AUNTIE_PUBLISH_PASSWORD` (or interactive
prompt) — they never appear in argv.

## File permissions

- htpasswd: readable by the user running `auntie up`, ideally not
  world-readable. Populate via `htpasswd -B` (bcrypt). Any non-bcrypt
  entry is rejected at load time, not silently skipped.
- TLS key file: readable by the same user, never world-readable.
  auntie does not auto-generate keys; use `mkcert`, `certbot`, or
  your internal CA.
- Wheelhouse directory: readable by anyone who needs to install from
  the index; writable by the user running `auntie up` (so atomic
  rename succeeds). Distribution files inherit umask.

## Self-signed certificates

The `auntie publish` client validates server certificates by default.
For self-signed setups (typical on a single-host LAN), set
`AUNTIE_INSECURE_SKIP_VERIFY=1`. The flag is loud — every invocation
prints a stderr warning — and is intended for local-only use. There
is no equivalent flag on the server itself; the server presents the
operator-supplied cert verbatim.

## Threat model summary

| Surface | Posture                                                |
|---------|--------------------------------------------------------|
| Read    | "single-host LAN with auth + TLS." Plain HTTP is loopback-only; non-loopback requires auth + TLS at config-load time. |
| Write   | "single-host LAN with auth + TLS + per-user authz." Every publisher authenticated AND in `publish_users`. |
| Local   | No process isolation between the CLI and the server when both run as the same user — auntie does not implement privilege separation. |

A multi-tenant deployment is out of scope; the v1.0.0 mesh-aware
milestone will revisit the trust boundary.
