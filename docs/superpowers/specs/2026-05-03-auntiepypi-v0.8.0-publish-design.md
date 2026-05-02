# auntiepypi v0.8.0 — `auntie publish` (write side)

**Status:** approved 2026-05-03
**Implements:** the v0.8.0 entry from CLAUDE.md's roadmap (POST upload
path with v0.7.0 trust model + per-user publish authz).
**Related specs:**
[v0.7.0 TLS + basic-auth](2026-05-02-auntiepypi-v0.7.0-tls-auth-design.md),
[v0.6.0 local server](2026-05-01-auntiepypi-v0.6.0-local-server-design.md)

## Context

v0.7.0 shipped HTTPS termination and HTTP Basic auth on the existing
read-only routes (`/`, `/simple/`, `/simple/<pkg>/`,
`/files/<filename>`) and lifted the loopback restriction when both TLS
and auth are configured. The v0.7.0 spec explicitly defers the write
side to this milestone:

> `auntie publish` write side → v0.8.0. Same trust model as v0.7.0
> (TLS + basic-auth) plus an authorization step (which users can
> publish).

v0.8.0 fills that pointer. The first-party server gains:

- **A twine-compatible POST upload endpoint at `/`** — the legacy PyPI
  upload API: `multipart/form-data` with `:action=file_upload`. Existing
  Python publishing tools (`twine`, `flit publish`, `hatch publish`)
  work unchanged.
- **A `publish_users` allowlist** in `[tool.auntiepypi.local]`. Empty
  / unset → no one can publish (read-only mode preserved). Set with
  names → only those htpasswd users can POST. A strict superset of
  authentication: every publisher must already authenticate.
- **An `auntie publish <wheel>` CLI verb** that uploads via stdlib
  `urllib.request` to the configured local server. Mirrors the
  small-landable-PR cadence used for v0.5.0 / v0.6.0 / v0.7.0.

The write side narrows the v0.7.0 trust surface ("single-host LAN with
auth + TLS") to "single-host LAN with auth + TLS + per-user authz."

The "stdlib-only except crypto primitives" invariant holds: multipart
parsing uses `email.parser.BytesParser`. The `cgi` module would have
been a closer fit but it's removed in Python 3.13; we're on 3.12+.
`bcrypt>=4.0,<5` (added in v0.7.0) remains the only runtime dep.

## Locked design decisions

### D1. Twine-compatible POST upload at `/`

Endpoint: `POST /` with `Content-Type: multipart/form-data; boundary=…`.
The body must contain at least:

- A part named `:action` with value `file_upload`. Anything else → 400.
- A part named `name` with the canonical project name.
- A part named `content` with `filename=…` and the raw distribution
  bytes.

PyPI's legacy upload API sends ~20 metadata fields (`version`,
`pyversion`, `metadata_version`, `summary`, `sha256_digest`, …); the
server **ignores** all but the three above. The wheel/sdist itself is
the source of truth for metadata.

**Why POST `/` and not POST `/simple/`?** Twine hardcodes the upload
URL as the index URL with `/legacy/` appended (or the bare URL for
non-PyPI). The conventional shape is "POST to the URL twine was given."
For our index, that's `/`. (`pypiserver` uses POST `/`; `devpi` uses
per-user URLs. We follow `pypiserver`.)

### D2. `publish_users` allowlist field

```toml
[tool.auntiepypi.local]
publish_users = ["alice", "bob"]
```

- Type: `list[str]` of htpasswd usernames. Stored on `LocalConfig` as
  `publish_users: tuple[str, ...]` (frozen-dataclass-friendly).
- **Empty / unset → no one can publish.** Read-only mode is preserved
  when an operator just wants a private mirror. POST → 403 with body
  `"publish disabled"`.
- **Set with names → only those users can POST.** Authenticated user
  not in the list → 403.
- Names must reference actual htpasswd entries; loader cross-checks
  at config-load time and raises `ServerConfigError` on dangling
  references (mirrors the v0.7.0 truth-table validators).
- Requires `auth_enabled` — `publish_users` set without `htpasswd` →
  `ServerConfigError`. (You can't authorize anonymous users.)

Per-package ownership (`{"alice": ["mypkg-*"]}`) is deferred to v1.0.0.

### D3. `verify_basic` widens to return `str | None`

The v0.7.0 `verify_basic(header, map) -> bool` discards the
authenticated username. Publish authz needs it. We refactor:

```python
def authenticate_user(raw_header: str, htpasswd_map) -> str | None:
    """Same checks as v0.7.0 verify_basic; returns username on
    success, None on any failure mode."""

def verify_basic(raw_header: str, htpasswd_map) -> bool:
    return authenticate_user(raw_header, htpasswd_map) is not None
```

`authenticate_user` is the new primitive; `verify_basic` becomes a
thin bool adapter for read-side callers that don't care which user.
Cache shape unchanged — the v0.7.0 cache already stores
`(timestamp, user, expected_hash)`; `authenticate_user` returns
`cached_user` on a fresh hit. No behaviour change for v0.7.0 callers.

### D4. Existing-file POST returns 409 Conflict

PyPI returns 400 with body "File already exists." We return **409
Conflict** because it's the semantically correct status for a name
collision and gives clients a clear retry signal (don't retry; pick a
new version). No overwrite, ever. Yank/delete is out of scope.

### D5. Body size cap via `max_upload_bytes`

```toml
[tool.auntiepypi.local]
max_upload_bytes = 104857600   # default: 100 MiB
```

Enforced two ways:

1. **Pre-read** via `Content-Length` — reject before reading body.
2. **During-read** via a counted reader that aborts after the cap.
   Defends against missing/lying `Content-Length`.

Default 100 MiB; operators with multi-GiB ML wheels override. The cap
is per-request, not per-day. No rate limiting in v0.8.0.

### D6. Atomic write: `tempfile` + `os.rename` in the same dir

Storage is flat (all wheels at `cfg.root` directly). Upload flow:

1. Validate filename via `parse_filename()` + `_SAFE_FILENAME` regex.
2. Validate the multipart `name` field normalizes to the same project
   name as `parse_filename()` reports (prevents cross-project
   overwrites by an authorized user).
3. Refuse if `cfg.root / filename` already exists → 409.
4. `tempfile.NamedTemporaryFile(dir=cfg.root, delete=False, prefix=".upload-")`
   — same filesystem guarantees atomic `os.rename`.
5. Write the bytes to the temp file.
6. `os.fsync()` the file, close, then `os.rename(tmp, final)`.
7. Unlink the temp path on any error path (no-op after successful
   rename). Errors return 500 only after cleanup.

### D7. CLI: `auntie publish <path>`

```text
auntie publish dist/mypkg-1.0-py3-none-any.whl
```

- Reads `[tool.auntiepypi.local]` for `host`, `port`, `tls_enabled`.
- Username from `$AUNTIE_PUBLISH_USER` or interactive prompt.
- Password from `$AUNTIE_PUBLISH_PASSWORD` or `getpass.getpass()`.
- Builds a multipart body via `email.message.EmailMessage` (stdlib),
  sends via `urllib.request.Request(method="POST")` with
  `Authorization: Basic …` header.
- HTTPS verification: when `cfg.tls_enabled`, uses
  `ssl.create_default_context()` (verifying). Self-signed cert? The
  operator either trusts it via system CA store or sets
  `AUNTIE_INSECURE_SKIP_VERIFY=1`. We prefer secure-by-default; the
  detector's `_create_unverified_context` is for self-probing only,
  not for clients.
- Output: `{"ok": true, "filename": "…", "url": "…"}` with `--json`,
  human-readable text otherwise. Exit 0 on 2xx, 1 on 4xx/5xx, 2 on
  network/TLS errors.
- Keyring/netrc support deferred to v0.8.1.

## Architecture

### `[tool.auntiepypi.local]` config block (full)

```toml
[tool.auntiepypi.local]
host = "0.0.0.0"
port = 3141
root = "~/.local/share/auntiepypi/wheels"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"
publish_users = ["alice", "bob"]      # NEW
max_upload_bytes = 104857600          # NEW (optional; default 100 MiB)
```

### `LocalConfig` extension

```python
_DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MiB

@dataclass(frozen=True)
class LocalConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    root: Path = field(default_factory=default_root)
    cert: Path | None = None
    key: Path | None = None
    htpasswd: Path | None = None
    publish_users: tuple[str, ...] = ()                # NEW
    max_upload_bytes: int = _DEFAULT_MAX_UPLOAD_BYTES  # NEW

    @property
    def publish_enabled(self) -> bool:
        return bool(self.publish_users) and self.auth_enabled
```

Defaulting `publish_users` to `()` is friendlier than `None` for
downstream callers — `if user in cfg.publish_users` works either way.
Empty tuple = read-only. The validator still raises if the field is
set but `htpasswd` isn't.

### Auth + authz flow (POST handler)

```python
def do_POST(self) -> None:
    if htpasswd_map is None:
        return self._send_status(405)              # auth not configured
    user = authenticate_user(
        self.headers.get("Authorization", ""), htpasswd_map
    )
    if user is None:
        return self._send_401()
    if not publish_users or user not in publish_users:
        return self._send_status(
            403,
            "publish disabled" if not publish_users
            else f"user {user!r} cannot publish",
        )
    if self.path != "/":
        return self._send_status(404)
    return self._handle_upload(user)
```

`_handle_upload` parses the body, validates the filename, runs
`write_upload`, and returns 201 on success.

### Threat model (v0.8.0)

Read surface still "single-host LAN with auth + TLS." Write narrows
that to "single-host LAN with auth + TLS + per-user authz."

| Threat                                | Mitigation                              |
|---------------------------------------|-----------------------------------------|
| Anonymous publish                     | 401 unless authenticated                |
| Reader can publish                    | 403 unless in publish_users             |
| Disk fill via huge upload             | max_upload_bytes (Content-Length + counted reader) |
| Wheel name collision                  | 409 Conflict; no overwrite              |
| Path traversal via filename           | _SAFE_FILENAME regex (no `/`, no `..`)  |
| Cross-project overwrite               | normalize(name) == normalize(parsed)    |
| Partial-file litter on crash          | tempfile + atomic rename + finally cleanup |
| Memory exhaustion via giant body      | Same as disk-fill: cap + counted reader |
| Plaintext creds on POST wire          | TLS 1.2 floor (v0.7.0 carryover)        |
| Stolen htpasswd → silent publish      | Operator rotates with `htpasswd -B`;    |
|                                       | cache TTL 60s ⇒ rotation visible fast   |

Out of scope (deferred or never):

- **Yank/delete** → never as an API. Operators retract a wheel by
  deleting the file from `cfg.root` directly. Document this rather
  than ship a half-baked yank API.
- **Per-package ownership maps** → v1.0.0. The
  `{"alice": ["mypkg-*"]}` shape is on the roadmap but quadruples the
  validator and test surface; out of scope for a small landable PR.
- **Keyring / netrc** → v0.8.1. v0.8.0 reads `$AUNTIE_PUBLISH_USER` /
  `$AUNTIE_PUBLISH_PASSWORD` or prompts. Keyring lookup is a separate
  PR with its own dep choice (system keyring vs. `keyring` package).
- **Streaming multipart parse** → v0.9.0. v0.8.0 buffers the whole
  upload in memory before parsing. With `max_upload_bytes` capped at
  100 MiB, this is acceptable for the LAN-scale use case.
- **Rate limiting** → never in v0.8.0. TLS termination + bcrypt KDF
  cost + LAN scope is adequate for the threat model.
- **Detached signature uploads** (`gpg_signature` part) → twine sends
  them but PyPI deprecated signature uploads. We 200 and silently
  discard. Document so users don't expect signature storage.
- **`sha256_digest` echo** → twine optionally validates the server's
  echoed SHA256. We don't compute or echo. Twine treats absence as
  "didn't ask" and doesn't fail.

## Compat notes

- `LocalConfig` gains two optional fields; v0.7.0 default tables still
  parse identically. Existing pyprojects with `[tool.auntiepypi.local]`
  keep working.
- `_actions/auntie._argv()` adds flags conditionally; pyprojects
  without `publish_users` / `max_upload_bytes` get the same argv as in
  v0.7.0.
- `verify_basic` keeps its bool signature; read-side callers
  (`_app.do_GET` v0.7.0) need no change. Internally it delegates to
  the new `authenticate_user`.
- No new runtime dependencies. `bcrypt` (added in v0.7.0) is reused
  by the new `authenticate_user` primitive.

## Remediation example: "I forgot publish_users"

Operator wants to publish but only configured TLS + auth:

```toml
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"
```

…runs `auntie up`, then `auntie publish dist/mypkg-1.0.whl`. Result:

```text
$ auntie publish dist/mypkg-1.0.whl
HTTP 403: publish disabled
```

Fix: add the allowlist.

```toml
[tool.auntiepypi.local]
host = "0.0.0.0"
cert = "/etc/ssl/private/auntie.pem"
key  = "/etc/ssl/private/auntie.key"
htpasswd = "/etc/auntie/htpasswd"
publish_users = ["alice"]
```

Then `auntie restart` (publish_users is read at server-start time, so
the running server doesn't pick up the change otherwise). Now
`auntie publish` succeeds.

## Remediation example: "I rotated a user out of htpasswd"

Operator removes `alice` from htpasswd but leaves `publish_users` as
`["alice"]`:

```text
$ auntie up
ServerConfigError:
  [tool.auntiepypi.local] publish_users[0] = 'alice' is not present in
  /etc/auntie/htpasswd. Either remove from publish_users or re-add to
  htpasswd.
```

This is the cross-validator's job. The error fires at config-load
time so misconfigurations don't get silently shipped.

## Verification

The v0.8.0 plan's verification gauntlet (TLS + auth + publish smoke,
twine-compat smoke, idempotence check, authz failure path) lives in
the plan file at `~/.claude/plans/dazzling-snacking-kay.md`.

Quality pipeline (same as v0.7.0):

- `pytest -n auto --cov=auntiepypi`, coverage ≥ 94%
- `black`, `isort`, `flake8`, `pylint --errors-only`, `bandit`
- `markdownlint-cli2`
- `bash .claude/skills/pr-review/scripts/portability-lint.sh`

Expected SonarCloud findings (and resolutions):

- `python:S5443` (`tempfile.NamedTemporaryFile(dir=...)`) on
  `_publish.write_upload`. NOSONAR with rationale: `dir` is
  operator-controlled `cfg.root`, not `/tmp`; operating-system temp
  dir would defeat the same-filesystem-rename invariant.
- `python:S2068` (hardcoded password) on test fixtures using `secret`
  / `fixture-pw`. NOSONAR; test-only, never deployed.
- `python:S5332` (HTTP-without-TLS) on test fixtures — carryover
  pattern from v0.7.0; NOSONAR with rationale.
- No new code smells expected; the upload flow is a sequence of small
  helpers (parse, validate, write) each well under cognitive-complexity
  budget.
