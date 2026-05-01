# auntiepypi v0.7.0 — HTTPS + basic-auth

**Status:** approved 2026-05-02
**Implements:** the v0.7.0 entry from CLAUDE.md's roadmap (auth + TLS,
lifting the loopback restriction).
**Related specs:**
[v0.6.0 local server](2026-05-01-auntiepypi-v0.6.0-local-server-design.md),
[v0.5.0 lifecycle verbs](2026-04-30-auntiepypi-v0.5.0-lifecycle-verbs-design.md)

## Context

v0.6.0 shipped the read-only first-party PEP 503 simple-index server bound
to **loopback only** by config-load-time enforcement
(`auntiepypi/_detect/_config.py:_validate_local_host`). The validator's
error message even names this milestone:

> "v0.6.0 binds loopback only (auth + TLS land in v0.7.0)."

v0.7.0 fills that pointer. The server gains:

- **HTTPS termination** via stdlib `ssl.SSLContext.load_cert_chain` against
  user-supplied `cert` / `key` PEM paths.
- **HTTP Basic auth** against an Apache htpasswd file (bcrypt-only —
  `$2y$` / `$2b$` / `$2a$` entries).
- **Public binding** when both TLS and auth are configured. Either alone
  is rejected at config-load time.

The read-only invariant holds: routes are unchanged from v0.6.0
(`/`, `/simple/`, `/simple/<pkg>/`, `/files/<filename>`). `auntie publish`
is deferred to v0.8.0. The slice is "make read-only safe to expose to
the LAN," consistent with the small-landable-PR pattern adopted for
v0.5.0 and v0.6.0.

`bcrypt>=4.0,<5` becomes the **first runtime dependency**, breaking the
codebase's stdlib-only invariant. The trade-off:

- stdlib has no htpasswd-compatible verifier (`crypt` was removed in
  Python 3.13; `hashlib.scrypt` doesn't speak htpasswd format).
- Rolling our own bcrypt is a non-starter (cryptographic primitive
  reimplementation is malpractice).
- `passlib` would be a heavier transitive surface than `bcrypt`.

`bcrypt` is the de-facto choice; the cost is a single runtime dep. The
constraint pin (`>=4.0,<5`) avoids surprise majors.

## Locked design decisions

### D1. Read-only slice; write side deferred to v0.8.0

v0.7.0 ships HTTPS + auth on the existing read routes. No new verbs.
`auntie publish` remains in v0.8.0. `auntie` consumers (mesh agents)
populating wheels still drop them into `cfg.root` directly.

### D2. User-supplied PEM via `[tool.auntiepypi.local].cert` / `.key`

```toml
[tool.auntiepypi.local]
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
```

Loaded via `ssl.SSLContext(PROTOCOL_TLS_SERVER).load_cert_chain(cert, key)`.
TLS minimum pinned to 1.2 explicitly:

```python
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))
```

No auto-generation. Operators run `mkcert`, `certbot`, or their internal
CA. Cert reload requires `auntie restart` (no file-watcher in v0.7.0).

### D3. htpasswd file, bcrypt-only

```toml
[tool.auntiepypi.local]
htpasswd = "/etc/auntie/htpasswd"
```

Generated with the standard `htpasswd -B -c -b <file> <user> <pass>`
tool (the `-B` flag selects bcrypt). Parser rules:

- Strip `\r\n`; skip blank lines and `#` comments.
- Split on **first** `:` only (`line.split(":", 1)`); bcrypt hashes
  themselves have no `:` but defensive split-1 is free.
- **Reject** entries whose hash doesn't start with `$2y$`/`$2b$`/`$2a$`
  at load time, citing line number. Silent skip is how auth bypasses
  ship.

`bcrypt.checkpw` with a **positive-only LRU cache** (TTL 60 s, size 128)
keyed on the raw `Authorization` header bytes. Cost-12 bcrypt verify is
~200–300 ms per check; `pip install` opens many connections, so per-
request bcrypt without caching makes installs feel laggy. Cache positive
only; misses always re-verify. Threadsafe via `threading.Lock`.

### D4. Loopback restriction lifts only when BOTH TLS + auth configured

| host          | cert+key | htpasswd | result            |
|---------------|----------|----------|-------------------|
| loopback      | any      | any      | allowed           |
| non-loopback  | both set | set      | allowed           |
| non-loopback  | partial  | any      | ServerConfigError |
| non-loopback  | unset    | unset    | ServerConfigError |
| non-loopback  | set      | unset    | ServerConfigError |
| non-loopback  | unset    | set      | ServerConfigError |

Loopback covers IPv4 `127.0.0.0/8`, IPv6 `::1`, and the literal
`localhost`. Anything else (including `0.0.0.0`, `::`, `::0`, LAN IPs,
hostnames) is non-loopback and requires the full TLS+auth bundle.

Error message format (Plan-validated for actionability):

```text
[tool.auntiepypi.local] host='0.0.0.0' is non-loopback;
non-loopback binds require BOTH 'cert'+'key' (TLS) AND
'htpasswd' (auth). missing: htpasswd.
```

The `missing: …` tail tells operators with a single gap exactly which
field to add; in the both-missing case the headline rule is enough.

### D5. Detection probes HTTPS; 401 counts as "up"

`_detect/_local.detect()` reads `cfg.tls_enabled` / `cfg.auth_enabled`
from `LocalConfig` (new properties).

When TLS is on:

- Probe URL becomes `https://host:port/`.
- `ssl.SSLContext` with `check_hostname=False` and
  `verify_mode=ssl.CERT_NONE`.

This is a **self-probe** of our own listener on the configured
`(host, port)` from our own `pyproject.toml` — not a trust decision.
Self-signed certs are common in mesh-internal use (devs run mkcert with
their own root, or the operator hasn't yet plumbed their CA). The
detector does not validate certificate identity; the operator does that
separately when they configure pip / uv to consume the index.

When auth is on, **401 with `WWW-Authenticate: Basic` counts as `up`**.
A 401 from our server is a stronger liveness signal than a 200: it
proves the auth wiring is functioning end-to-end. The detector does not
read htpasswd to extract credentials; that would mean auth-bypass-by-
detection.

`format_http_url` gains a `scheme="http"` parameter (backward-compatible
default). `probe_endpoint` accepts `scheme` and an optional
`ssl_context`.

## Architecture

### `LocalConfig` extension

```python
# auntiepypi/_server/_config.py
@dataclass(frozen=True)
class LocalConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    root: Path = field(default_factory=default_root)
    cert: Path | None = None
    key: Path | None = None
    htpasswd: Path | None = None

    @property
    def tls_enabled(self) -> bool:
        return self.cert is not None and self.key is not None

    @property
    def auth_enabled(self) -> bool:
        return self.htpasswd is not None
```

The properties enable downstream callers (`_detect/_local`, `_actions/auntie`,
`_server/__main__`) to dispatch on configuration without re-reading the
TOML on every check.

### Auth flow (handler)

```python
# auntiepypi/_server/_app.py — inside _Handler
def do_GET(self) -> None:
    if htpasswd_map is not None and not self._authenticate():
        return self._send_401()
    # existing dispatch unchanged

def _authenticate(self) -> bool:
    return verify_basic(self.headers.get("Authorization", ""), htpasswd_map)
```

`verify_basic`:

1. Cache lookup on raw header bytes; return cached True if hot.
2. Strip `"Basic "` prefix, base64-decode (`binascii.Error` → False).
3. Split on first `:`, lookup user in map, `bcrypt.checkpw`.
4. On True, write to cache. Always return result.

`_send_401`:

```python
def _send_401(self) -> None:
    body = b"401\n"
    self.send_response(401)
    self.send_header("WWW-Authenticate",
                     'Basic realm="auntiepypi", charset="UTF-8"')
    self.send_header("Connection", "close")
    self.send_header("Content-Type", "text/plain; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```

`charset="UTF-8"` per RFC 7617; `Connection: close` prevents header
confusion across a stale keep-alive.

### TLS flow (serve)

```python
# auntiepypi/_server/__init__.py
def serve(host, port, root, *, ssl_context=None, htpasswd_map=None,
          server_factory=ThreadingHTTPServer):
    handler_cls = make_handler(root, htpasswd_map=htpasswd_map)
    httpd = server_factory((host, port), handler_cls)
    if ssl_context is not None:
        httpd.socket = ssl_context.wrap_socket(httpd.socket, server_side=True)
    # signal setup, serve_forever, server_close — unchanged
```

`ThreadingHTTPServer.daemon_threads` defaults to True, so a slow TLS
handshake on shutdown won't block. In-flight TLS connections may log
noisy `ssl.SSLError` on abrupt shutdown; that is acceptable.

### Dispatch flow (`auntie up` with TLS+auth)

```text
auntie up
  → _local_pair() reads LocalConfig
  → _actions.dispatch("start", detection, spec)
  → auntie.start():
      readability guards on cert/key/htpasswd
        → ActionResult(ok=False) on miss (no raise)
      → _argv(cfg) appends --cert / --key / --htpasswd as configured
      → _command.start() spawns:
          python -m auntiepypi._server [--host ... --port ... --root ...
            (--cert ... --key ...)? (--htpasswd ...)?]
  → _server.__main__:
      argparse → build_ssl_context + parse_htpasswd → serve()
  → ThreadingHTTPServer wrapped with TLS, handler enforces basic-auth
  → _detect/_local.detect() probes https://host:port/, 401 → status="up"
```

## Threat model (v0.7.0)

Surface expands from "loopback only" (v0.6.0) to "single-host LAN with
auth + TLS" (v0.7.0).

| Threat                            | Mitigation                              |
|-----------------------------------|-----------------------------------------|
| Plaintext creds on the wire       | TLS 1.2 floor, `load_cert_chain`        |
| Brute-force password guessing     | bcrypt KDF cost (no rate limiting)      |
| Timing attacks within a hash      | bcrypt is constant-time within work     |
| Auth bypass via malformed B64     | `binascii.Error` → 401, never 500       |
| Stale auth bypass via cache       | Positive-only, 60s TTL, 128 max         |
| World-readable htpasswd           | Warn at load time, do not fail          |
| Cert rotation                     | Operator runs `auntie restart`, doc'd   |
| Path traversal (carryover)        | Existing `_app.py` guard                |
| Self-probe trust shortcuts        | Not a trust decision — own-listener     |

Out of scope (deferred to later milestones or never):

- **`auntie publish` write side** → v0.8.0. Same trust model as v0.7.0
  (TLS + basic-auth) plus an authorization step (which users can
  publish).
- **Brute-force throttling** → never in v0.7.0. bcrypt's KDF cost is the
  throttle. Add `fail2ban`-style logging for ops who want it via the
  request-log warning lines (failed-auth lines log at WARNING with
  source IP).
- **Token / OIDC auth** → not on roadmap. Basic-auth is enough for the
  mesh-internal threat model.
- **Auto-generated certs** → never. Operator brings their own PEM. The
  test fixture uses `cryptography` to generate a 1-day cert at session
  scope, but production code never calls into `cryptography`.
- **Cert reload without restart** → never in v0.7.0. The
  `SSLContext` snapshot is bound at `serve()` start; rotating the file
  doesn't invalidate the in-memory context. Document; don't engineer.
- **HSTS / redirects** → never. auntie is a single-port server.
- **`auntie doctor` lenient validation of TLS/auth misconfig** → out of
  scope. v0.7.0 raises hard at config-load. A v0.7.x or v0.8.0 PR could
  surface the gaps as `ConfigGap` entries via a lenient loader path,
  mirroring `load_servers_lenient`.

## Compat notes

- The `[tool.auntiepypi.local].host` validator's error message is
  rewritten. Previously it ended with "v0.6.0 binds loopback only (auth
  - TLS land in v0.7.0)." Now it ends with the truth-table-aware
  diagnostic naming the missing field group(s).
- `format_http_url` and `probe_endpoint` gain a `scheme` keyword
  parameter with `"http"` default. All v0.6.0 call sites
  (`_declared`, `_port`, `_local`-without-TLS) pass nothing and keep
  HTTP. `_local`-with-TLS passes `scheme="https"`.
- `LocalConfig` gains three optional fields; the v0.6.0 default-only
  table still parses identically. Existing pyprojects with
  `[tool.auntiepypi.local]` keep working.
- `_actions/auntie._argv()` adds flags conditionally; v0.6.0
  pyprojects (no cert/key/htpasswd) get the same argv as before.
- The new `bcrypt>=4.0,<5` dependency adds ~600 KB to the install
  footprint. Mesh-internal use accepts this; agents already ship
  Python.

## Remediation example: "I forgot htpasswd"

Operator writes:

```toml
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
```

…and runs `auntie up`. Result:

```text
$ auntie up
ServerConfigError:
  [tool.auntiepypi.local] host='0.0.0.0' is non-loopback;
  non-loopback binds require BOTH 'cert'+'key' (TLS) AND
  'htpasswd' (auth). missing: htpasswd.
```

Fix:

```bash
htpasswd -B -c /etc/auntie/htpasswd alice
htpasswd -B    /etc/auntie/htpasswd bob   # additional users without -c
```

```toml
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"
```

`auntie up` now succeeds; `auntie overview` reports the local section
as `up`.

## Verification

The v0.7.0 plan's verification gauntlet (loopback regression, TLS+auth
smoke, misconfig path, pip round-trip with auth) lives in the plan file.

Quality pipeline (same as v0.5.0/v0.6.0):

- `pytest -n auto --cov=auntiepypi`, coverage ≥ 94%
- `black`, `isort`, `flake8`, `pylint --errors-only`, `bandit`
- `markdownlint-cli2`
- `bash .claude/skills/pr-review/scripts/portability-lint.sh`

Expected SonarCloud findings (and resolutions):

- `python:S5332` (HTTP-without-TLS hotspot) on test fixtures only —
  the production server now defaults to HTTPS when configured.
  Test fixtures use HTTP for simplicity; NOSONAR with rationale.
- `python:S4830` (insecure SSL) on `_detect/_local.detect()` for the
  `_create_unverified_context()` self-probe. NOSONAR with rationale:
  self-probe of our own listener, not a trust decision.
- No new code smells expected; the auth gate and TLS wrap are thin
  helpers that should stay under cognitive-complexity budget.
