# auntiepypi v0.4.0 — `doctor` lifecycle design

**Status:** approved 2026-04-30 via brainstorming session. This document is
the project-side spec; if a planning artifact written elsewhere drifts,
this file wins.

## Statement of purpose

> v0.4.0 turns `doctor` from a static probe over two hardcoded flavors
> into a **`managed_by`-aware lifecycle dispatcher** over the declared
> inventory `_detect/` already produces. `_probes/` is deleted; its sole
> consumer (`doctor`) now consumes `_detect/`. A new `_actions/` module
> holds the strategies, one per `managed_by` value. Two strategies ship:
> `systemd-user` (`systemctl --user start <unit>`) and `command`
> (detached `Popen` + synchronous re-probe + XDG state logs).

The mutating flag rename `--fix → --apply` (sibling-pattern alignment)
and the removal of the `packages` noun (already redundant with
`auntie overview <PKG>`) ride along in this milestone. We are in 0.x;
breaking changes are explicit and small in number.

Out of scope, deferred to later milestones:

- `auntie up` and any "run our own PyPI server" code → **v0.5.0**.
- `auntie down` / `restart` → v0.5.0 (paired with `up`'s lifecycle
  ownership).
- `managed_by = "docker"` / `"compose"` strategies — schemas remain
  valid in v0.4.0; doctor reports them as not-implemented and `--apply`
  skips them.
- Mesh discovery → **v1.0.0**.
- Auto-rewriting `pyproject.toml` *values* — never. The only mutation
  v0.4.0 ships is **deletion** of half-supervised entries (and
  `--decide`-resolved duplicates).

## Brainstorm decisions (machine-readable)

| Question | Decision |
|---|---|
| Scope of v0.4.0 | Lifecycle minimal slice: `systemd-user` + `command` only |
| Verb shape | Extend `doctor`; `auntie up` reserved for v0.5.0 (own-server) |
| `_probes/` vs `_detect/` | Delete `_probes/`; doctor consumes `_detect/`; new `_actions/` keyed on `managed_by` |
| `command` strategy semantics | Detached `Popen(start_new_session=True)` + synchronous re-probe + XDG state log; doctor does not track child past spawn |
| Cross-field config validation | Hard-fail in non-doctor verbs; lenient in doctor (per-entry diagnoses) |
| Config write semantics | Delete-whole-entry for half-supervised; ambiguous → `--decide` rerun pattern |
| `pyproject.toml` backups | Numbered `<name>.<N>.bak`, never overwritten; one per mutating session |
| Doctor's view scope | Declared + scan-found; only declared are actionable |
| Mutating flag name | `--apply` replaces `--fix` outright (no alias, no deprecation period) |
| `packages` noun | Deleted; `auntie overview <PKG>` already covers the drill-down |
| `--proc` on doctor | Not added — overview owns proc detection; doctor's job is action |

## Surface

```text
auntie doctor [TARGET] [--apply] [--decide KEY=VALUE]... [--json]
auntie overview [TARGET] [--proc] [--json]            # unchanged from v0.3.0
auntie explain <path> [--json]                        # unchanged
auntie learn [--json]                                 # unchanged (planned[] = [])
auntie whoami [--json]                                # unchanged
```

`auntie packages overview` is **gone**. Its functionality is fully
covered by `auntie overview <PKG>` (configured-package resolution path
in v0.3.0's TARGET priority). Both `auntie` and `auntiepypi` remain
registered console scripts, both → `auntiepypi.cli:main`.

### `doctor` behavior

**Without `--apply` (dry-run, default).** For each declared server:
print `name`, `status`, `flavor`, `host:port`, `diagnosis`,
`remediation`. For scan-found-undeclared servers: print observation +
a TOML stub the user can paste into `[[tool.auntiepypi.servers]]`.
Closing line: `(dry-run; pass --apply to act on N remediations)` where
`N` counts entries where `--apply` would do something.

**With `--apply`.** For each declared server with `status != "up"` and
an implemented strategy: spawn via the strategy module, re-probe within
5 s, mutate the per-item payload in place. For half-supervised entries:
delete the whole `[[tool.auntiepypi.servers]]` block, audit-line on
stderr, re-load config (do not retry the start — manual is the new
state). For ambiguous cases (duplicate `name`): print the `--decide`
instructions and skip; doctor still exits cleanly. For unimplemented
strategies (`docker` / `compose`): skip with diagnosis. For undeclared
scan-found: skip silently (out of scope for `--apply`).

**`--decide KEY=VALUE` (repeatable).** Resolves a previously-printed
ambiguity. Format `key=value`; `argparse` `action="append"`. v0.4.0
ships exactly one decision type — `duplicate:<name>=<index>` — with
the convention documented for future PRs to extend (e.g. v0.5.0 might
add `decide=stop-strategy:<name>=hard|graceful` for `auntie down`).
Unknown decision keys exit `1` with a list of known types. Agents can
stack decisions across multiple ambiguities in one re-run.

**`TARGET` positional.** Resolves to a declared `name`. Unknown TARGET
→ stderr warning + exit `0` (mirrors `overview`'s zero-target
behavior). Drill-down output is the same per-entry format, just for one
entry.

**`--json`.** Same envelope shape as v0.3.0's `overview`
(`{"subject", "sections": [...]}`); doctor's sections add `diagnosis`
and `remediation` fields per item.

**No `--proc` flag on doctor.** Overview owns proc detection; doctor's
job is action over the inventory `_detect/` already produces.

### Examples

```bash
auntie doctor                                  # dry-run; explain everything
auntie doctor main                             # drill into one entry
auntie doctor --apply                          # commit; spawns + deletes half-supervised
auntie doctor --apply --decide=duplicate:main=1
auntie doctor --json                           # for piping to jq
```

## Architecture

```text
auntiepypi/
├── _detect/                      # UNCHANGED from v0.3.0 (declared + port + proc)
│   ├── _config.py                # gains cross-field validation
│   └── ...
├── _actions/                     # NEW — one file per managed_by strategy
│   ├── __init__.py               # ACTIONS = {"systemd-user": ..., "command": ...}; dispatch()
│   ├── _action.py                # frozen @dataclass ActionResult; Strategy protocol
│   ├── _logs.py                  # XDG state dir resolver, log-path helper
│   ├── _reprobe.py               # post-spawn re-probe loop (5s, TCP+HTTP)
│   ├── systemd_user.py           # systemctl --user start <unit>
│   ├── command.py                # detached Popen + sync re-probe
│   └── _config_edit.py           # delete-whole-entry stdlib edit + numbered .bak
├── _probes/                      # DELETED
├── cli/_commands/
│   ├── doctor.py                 # rewritten: detect_all + dispatch + diagnose
│   ├── overview.py               # unchanged
│   ├── _decide.py                # NEW — decision-type registry
│   └── _packages/                # DELETED (packages noun removed)
└── ...
```

### Strategy protocol

Each `_actions/<strategy>.py` exposes one function:

```python
def apply(detection: Detection, declaration: ServerSpec) -> ActionResult: ...
```

`ActionResult` is a frozen dataclass:

```python
@dataclass(frozen=True)
class ActionResult:
    ok: bool
    detail: str
    log_path: str | None = None
    pid: int | None = None
```

The strategy is responsible for spawn + re-probe; doctor receives the
post-action result and updates the JSON envelope. Re-probe lives in
`_actions/_reprobe.py` so both strategies share it.

### Dispatch

`_actions/__init__.py` exposes:

```python
ACTIONS: dict[str, Callable[[Detection, ServerSpec], ActionResult]] = {
    "systemd-user": systemd_user.apply,
    "command":      command.apply,
}

def dispatch(detection, declaration) -> ActionResult: ...
```

`docker` and `compose` are **absent** from `ACTIONS`. `dispatch()`
returns `ActionResult(ok=False, detail="not implemented in v0.4.0")`
for those — never raises — so doctor surfaces them uniformly with the
rest. `manual` is also absent and dispatches to a no-op result so the
loop is uniform. **Unset `managed_by` is treated identically to
`manual`** — observed-only, dispatched to the same no-op; doctor's
action-class grouping classes both as `skip`.

### Doctor's wiring (`cli/_commands/doctor.py`, rewritten)

1. `detect_all()` from `_detect/` — same call `overview` makes. Returns
   `list[Detection]` for declared + port-scan.
2. For each detection: build `diagnosis` text (rule-based on `status` +
   `managed_by` + cross-field state from lenient config load).
3. **Dry-run output** (no `--apply`): emit text + diagnosis +
   remediation; close with
   `(dry-run; pass --apply to act on N remediations)`.
4. **Apply path** (`--apply`):
   - Group by action class — `actionable` (declared, status≠up,
     strategy implemented), `half_supervised` (cross-field gap),
     `ambiguous` (matched a `--decide` key not yet provided), `skip`
     (everything else).
   - **Stage** all pending mutations first. If any exist, write
     `pyproject.toml.<N>.bak` (next free numbered slot) before any
     mutation.
   - For each `half_supervised` entry: call
     `_actions/_config_edit.delete_entry(name)`. Each deletion re-loads
     config; the entry vanishes from subsequent passes.
   - For each `actionable` entry: call `_actions.dispatch()`; merge the
     `ActionResult` into the per-item payload.
   - For each `ambiguous` entry: emit the `--decide` rerun text on
     stderr; doctor still exits cleanly with code `0`.
   - For each `skip`: pass through unchanged.
5. Emit final payload (text or JSON).

### `--decide` registry (`cli/_commands/_decide.py`)

```python
DECISIONS: dict[str, DecisionResolver] = {
    "duplicate": resolve_duplicate_name,   # the only v0.4.0 decision type
}
```

Unknown keys → exit `1` with the list of known types. **Stale decision
values** (well-formed `key=value` whose `key` is registered but whose
ambiguity is no longer present in the current run — e.g.
`--decide=duplicate:main=1` after the duplicate has already been
resolved) are silently ignored, so re-runs stay idempotent. Mechanism
is stable; future PRs add entries without changing the surface.

### Plug-in pattern, recap

Each axis has its own plug-in module: `_detect/` plugs detectors,
`_actions/` plugs strategies, `cli/_commands/_decide.py` plugs
ambiguity resolvers. Adding a docker strategy in v0.4.x is one new
file in `_actions/` plus one entry in `ACTIONS` — no surgery to doctor
itself. Same pattern v0.3.0 already established.

### Stdlib only

- `_actions/_config_edit.py` — line-scoped regex; no `tomlkit`.
- `_actions/command.py` — `subprocess.Popen(start_new_session=True)`;
  no `psutil`.
- `_actions/systemd_user.py` — shells out to `systemctl`; no
  `dbus-python`.

## Configuration & cross-field validation

### Schema (unchanged from v0.3.0; this PR adds enforcement, not fields)

```toml
[[tool.auntiepypi.servers]]
name        = "main"           # required, unique
flavor      = "pypiserver"     # required: "pypiserver" | "devpi" | "unknown"
host        = "127.0.0.1"      # default
port        = 8080             # required, 1..65535
managed_by  = "systemd-user"   # "systemd-user" | "docker" | "compose" | "command" | "manual" | (unset)
unit        = "pypi-server.service"
dockerfile  = "./infra/pypi/Dockerfile"
compose     = "./infra/pypi/docker-compose.yml"
service     = "pypi"
command     = ["pypi-server", "run", "-p", "8080", "/srv/wheels"]
```

### Cross-field rules

| `managed_by` | Required companions | "half-supervised" if missing |
|---|---|---|
| `"systemd-user"` | `unit` | yes — strict fails; lenient diagnoses; `--apply` deletes the whole entry |
| `"command"` | `command` (non-empty list, all strings) | yes — same |
| `"docker"` | `dockerfile` | yes (validation-wise) — strict fails; lenient diagnoses; `--apply` skips ("not implemented in v0.4.0") |
| `"compose"` | `compose` | same as docker |
| `"manual"` | none — explicit "I supervise myself" escape | n/a |
| unset | none — equivalent to `"manual"` for validation; observed-only | n/a |

### `load_servers(strict: bool = True)` in `_detect/_config.py`

**Strict mode (default).** Called by `overview` and any future verb
that loads the array. On any rule violation: report **all** violations
in one pass, then exit `1` with structured stderr (don't fail-fast on
the first one — agents fix one and re-run; reporting all at once cuts
the round-trip count):

```text
servers entry 'main' (line 42): managed_by="systemd-user" requires `unit`.
  Run `auntie doctor` for a full diagnosis and remediation guidance.
  Run `auntie doctor --apply` to delete the half-supervised declaration.
  hint: docs/superpowers/specs/2026-04-30-auntiepypi-v0.4.0-doctor-lifecycle-design.md
```

**Lenient mode.** Called by `doctor` only. Returns
`tuple[list[ServerSpec], list[ConfigGap]]`. Doctor's diagnosis logic
uses both: per-entry diagnosis, with `ConfigGap` driving the
remediation text and the `--apply` action class (`half_supervised` vs
`actionable` vs `skip`).

### Duplicate-name handling

Both modes detect duplicates. Strict mode exits `1` (same shape as
above). Lenient mode emits one
`ConfigGap(kind="duplicate", name=..., lines=[42, 67])` and doctor
surfaces it as the **ambiguous** action class — `--apply` *without*
`--decide=duplicate:<name>=N` prints the rerun instructions and exits
`0` (decision required, nothing went wrong). With the `--decide`,
doctor deletes the non-kept entry exactly like a half-supervised
deletion.

### Validation precedence

Within one entry: structural (closed-set values, port range, types) →
cross-field (required companions). Within the file: per-entry first,
then file-level (duplicate names). This ordering matters because a
duplicate-name check on entries that haven't passed structural
validation can crash on missing `name` keys.

### `_actions/_config_edit`

- `delete_entry(name: str) → DeleteResult` — read `pyproject.toml` as
  text; find the `[[tool.auntiepypi.servers]]` block whose entry has
  the matching `name = "..."`; block bounds: from the `[[...]]` header
  line through the line before the next `[`-prefixed table header (or
  EOF); refuse to delete if any line in the block matches a
  "we can't safely parse" pattern (inline-table syntax `{ … }` on the
  header line, multi-line strings inside the block); on refusal:
  `DeleteResult(ok=False, reason=...)` and doctor reports
  "could not auto-delete; remove the entry manually"; on success: write
  the new file content, return `DeleteResult(ok=True, lines_removed=(start, end))`;
  loud audit on stderr:
  `wrote pyproject.toml: removed [[tool.auntiepypi.servers]] entry 'main' (lines 42-49)`.
- `snapshot() → Path` — write `pyproject.toml.<N>.bak` with the next
  free `N` (scan parent dir for existing `.<N>.bak` files, take
  `max(N) + 1`, default `1`); use `open(path, "x")` for exclusive
  create; on `FileExistsError`, retry up to 5 times with `N+1`,
  `N+2`, …; after that, raise `AfiError` with exit code `1` and
  remediation "clean up old `.bak` files"; audit on stderr:
  `wrote pyproject.toml.3.bak (rollback: mv pyproject.toml.3.bak pyproject.toml)`;
  called once at the start of any mutating `--apply` session.

No backup-cleanup logic — `.bak` files persist until the user removes
them. `.gitignore` pattern: `*.toml.*.bak` (the simpler `*.toml.bak`
wouldn't catch the numbered form). Auntiepypi's own `.gitignore`
carries this; user-facing docs ("using auntie in your project") tell
consumer projects to do the same.

## Lifecycle strategies

Both strategies return `ActionResult(ok, detail, log_path, pid)`.
Doctor's per-item payload merges these as `fix_attempted` (always
`True` post-dispatch), `fix_ok`, `fix_detail`, `log_path`, `pid`,
plus the post-action re-detect status.

### Strategy 1: `managed_by = "systemd-user"`

**File:** `_actions/systemd_user.py`

**Action:**
`subprocess.run(["systemctl", "--user", "start", spec.unit], check=False, capture_output=True, text=True, timeout=15)`.

**Success criterion:** `returncode == 0` **and** post-spawn re-probe
via `_actions/_reprobe.probe(detection)` returns `up` within 5 s.

**Why two layers:** systemctl returns 0 once the unit is `active` per
its `Type=`. For `Type=simple` units that means "process spawned," not
"port bound and serving." The re-probe is the real success signal.

**Error mapping:**

| Outcome | `ActionResult` |
|---|---|
| systemctl exit 0, re-probe `up` | `ok=True, detail="started"` |
| systemctl exit 0, re-probe still `down`/`absent` after 5 s | `ok=False, detail="systemctl ok but server not responding (check unit logs: journalctl --user -u <unit>)"` |
| systemctl exit ≠ 0 | `ok=False, detail=f"systemctl exit {rc}: {first_stderr_line}"` |
| `systemctl` not on PATH | `ok=False, detail="systemctl not found; install systemd-user or use managed_by=command"` |
| timeout (>15s) | `ok=False, detail="systemctl timed out"` |

`log_path = None` and `pid = None` for systemd-user — journald owns
logs and the unit owns the PID; doctor doesn't echo them.

### Strategy 2: `managed_by = "command"`

**File:** `_actions/command.py`

**Action:**

```python
log_path = _logs.path_for(spec.name)              # $HOME/.local/state/auntiepypi/<name>.log
log_path.parent.mkdir(parents=True, exist_ok=True)
with open(log_path, "ab") as logf:
    logf.write(f"\n=== {datetime.now(UTC).isoformat()}: starting {spec.command} ===\n".encode())
    proc = subprocess.Popen(
        list(spec.command),
        start_new_session=True,                   # detach from doctor's process group
        stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        cwd=Path.cwd(),
    )
```

Doctor returns from `Popen()` immediately (it does NOT wait). The PID
is recorded for the JSON envelope but not tracked beyond this run.

**Success criterion:** post-spawn `_actions/_reprobe.probe(detection)`
returns `up` within 5 s.

**Re-probe loop (`_actions/_reprobe.py`):**

- Total budget: 5 s wall.
- Cadence: try at t=0.5s, 1s, 2s, 3.5s, 5s. Each attempt is a TCP
  connect (1 s timeout) → HTTP GET on `flavor`'s health path
  (1 s timeout). First `up` wins; loop exits early.

**Early-exit check:** before the re-probe loop starts, `Popen.poll()`
— if the child already exited (typical for "command not found" cases
that race past `Popen` itself), record the returncode and abort the
re-probe.

**Error mapping:**

| Outcome | `ActionResult` |
|---|---|
| Popen succeeds, child still alive, re-probe `up` | `ok=True, detail="started", log_path=…, pid=…` |
| Popen succeeds, child already exited before re-probe | `ok=False, detail=f"command exited immediately (rc={rc}); see {log_path}", log_path=…, pid=None` |
| Popen succeeds, child still alive, re-probe still `down`/`absent` | `ok=False, detail=f"spawned but not responding after 5s (pid={pid}, log: {log_path})", log_path=…, pid=…` |
| `FileNotFoundError` from `Popen` | `ok=False, detail=f"command not found: {argv0}"` |
| `PermissionError` | `ok=False, detail=f"permission denied: {argv0}"` |
| any other `OSError` | `ok=False, detail=f"{type}: {msg}"` |

### XDG state directory (`_actions/_logs.py`)

```python
def state_root() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".local" / "state") / "auntiepypi"
```

`path_for(name)` returns `state_root() / f"{slugify(name)}.log"`.
`slugify` lowercases and replaces non-`[a-z0-9._-]` with `_` —
defends against weird `name` values in declarations.

### Stop / restart

Out of scope. v0.5.0 ships `auntie down` paired with `auntie up` and
owns process-tracking properly (PID file in `state_root()`,
signal-graceful-then-kill). v0.4.0's `command` strategy is "spawn and
forget"; doctor's text output reminds the user:
`(once started, supervise externally; \`auntie down\` lands in v0.5.0)`.

## Output & JSON envelope

### JSON envelope

Same outer shape v0.3.0 established (`{"subject", "sections": [...]}`).
Doctor emits **one section per detection**, plus an aggregate
`summary` trailer. Each section's `category` is `"servers"`
(consistent with overview); section-level `light` is `up→green`,
`down→red`, `absent→unknown`, `not-implemented→yellow`.

```json
{
  "subject": "auntie doctor",
  "sections": [
    {
      "category": "servers",
      "title": "main",
      "light": "red",
      "fields": [
        {"name": "flavor",       "value": "pypiserver"},
        {"name": "host",         "value": "127.0.0.1"},
        {"name": "port",         "value": "8080"},
        {"name": "url",          "value": "http://127.0.0.1:8080/"},
        {"name": "status",       "value": "down"},
        {"name": "source",       "value": "declared"},
        {"name": "managed_by",   "value": "command"},
        {"name": "diagnosis",    "value": "down; would Popen command and re-probe"},
        {"name": "remediation",  "value": "auntie doctor --apply"}
      ]
    },
    {
      "category": "servers",
      "title": "stale",
      "light": "yellow",
      "fields": [
        {"name": "flavor",       "value": "devpi"},
        {"name": "managed_by",   "value": "systemd-user"},
        {"name": "status",       "value": "down"},
        {"name": "config_gap",   "value": "managed_by=systemd-user requires `unit`"},
        {"name": "diagnosis",    "value": "half-supervised; --apply would delete this entry"},
        {"name": "remediation",  "value": "add `unit = \"…\"` to keep supervision, or run `auntie doctor --apply` to demote to manual by deletion"}
      ]
    },
    {
      "category": "servers",
      "title": "pypiserver:8080",
      "light": "green",
      "fields": [
        {"name": "flavor",       "value": "pypiserver"},
        {"name": "status",       "value": "up"},
        {"name": "source",       "value": "port"},
        {"name": "diagnosis",    "value": "observed; not declared"},
        {"name": "remediation",  "value": "to manage with auntie, add to pyproject.toml:\n[[tool.auntiepypi.servers]]\nname = \"…\"\nflavor = \"pypiserver\"\nport = 8080\nmanaged_by = \"manual\""}
      ]
    }
  ],
  "summary": {
    "total": 3,
    "by_status": {"up": 1, "down": 2},
    "by_action_class": {"actionable": 1, "half_supervised": 1, "skip": 1, "ambiguous": 0},
    "applied": false
  }
}
```

**Post-`--apply` envelope additions:** when `--apply` ran, each section
that doctor acted on gains:

```json
{"name": "fix_attempted", "value": "true"},
{"name": "fix_ok",        "value": "true|false"},
{"name": "fix_detail",    "value": "…"},
{"name": "log_path",      "value": "/home/.../<name>.log"},
{"name": "pid",           "value": "12345"}
```

`summary.applied` flips to `true`. Half-supervised deletions add a
section-level field `{"name": "deleted", "value": "true"}`.

### Field-shape choice

All field values are strings (numbers stringified, booleans as
`"true"`/`"false"`). This matches v0.3.0's shape exactly and keeps
`jq` queries uniform across `overview` and `doctor`.

`config_gap` is a new field, populated only when present. Same
elision rule as v0.3.0: missing → field omitted, not `null`.

### Text output (no `--json`)

Mirrors v0.3.0 doctor's text shape; keeps the same column layout. New
columns: `diagnosis` (always) and `remediation` (when status ≠ up).
For undeclared scan-found, the TOML stub is rendered as an indented
block under `remediation:`.

```text
# auntie doctor
summary: 1 actionable, 1 half-supervised, 1 skip, 0 ambiguous (3 total)

  main          down     declared    managed_by=command
      diagnosis: down; would Popen command and re-probe
      remediation: auntie doctor --apply

  stale         down     declared    managed_by=systemd-user
      config_gap: managed_by=systemd-user requires `unit`
      diagnosis: half-supervised; --apply would delete this entry
      remediation: add `unit = "…"` to keep supervision, or run `auntie doctor --apply`

  pypiserver:8080  up    port        observed; not declared
      remediation:
          [[tool.auntiepypi.servers]]
          name = "…"
          flavor = "pypiserver"
          port = 8080
          managed_by = "manual"

(dry-run; pass --apply to act on 2 remediations)
```

### Stderr discipline (unchanged from v0.3.0)

- **Stdout:** structured payload (text or JSON). Never warnings, never
  audit lines.
- **Stderr:** human-readable warnings, audit lines on writes
  (`wrote pyproject.toml.3.bak …`,
  `wrote pyproject.toml: removed entry 'main' …`), `--decide` rerun
  instructions.

An agent piping `auntie doctor --json` into `jq` never sees the stderr
noise.

### `--decide`-required state

When doctor encounters an ambiguous case and the matching `--decide`
value wasn't passed, `--apply` does **not** run that ambiguous case's
mutation but **does** continue with everything else (other unrelated
half-supervised deletions, server starts that aren't blocked on the
duplicate). The ambiguous section's payload includes:

```json
{"name": "diagnosis",    "value": "ambiguous: duplicate name 'main' (lines 42, 67)"},
{"name": "remediation",  "value": "auntie doctor --apply --decide=duplicate:main=1   # or =2"}
```

Stderr also gets a one-line summary:
`--decide required for: duplicate:main (run with --decide=duplicate:main=1 or =2)`.
Exit code stays `0` (the user just needs to run again — nothing
failed).

## Exit codes & error model

| Code | Meaning | Triggers |
|---|---|---|
| `0` | success | dry-run completed; `--apply` brought every actionable server up; ambiguous cases deferred via `--decide` (no failure — user just needs to re-run); unknown `TARGET` (stderr warning) |
| `1` | configuration / usage error | strict-mode `load_servers()` violation in non-doctor verbs; unknown `--decide` key; bad arg shape; `_actions/_config_edit` refused to delete (unparseable block); `.bak` slot exhaustion |
| `2` | environment / action failure | `--apply` ran but at least one **actionable** entry is still not `up` after the strategy + re-probe |

**What does NOT escalate:**

- Half-supervised entries with no `--apply` — exit `0`. Doctor's job
  is to surface.
- Unimplemented-strategy entries (docker/compose) — exit `0`, even on
  `--apply`. Skipping a not-implemented strategy isn't an environment
  failure.
- Undeclared scan-found servers — exit `0`. They aren't `--apply`'s
  concern.
- Ambiguous entries without `--decide` — exit `0`. The user needs to
  re-run; nothing went wrong.

The `2`-vs-`0` line: `2` means "you asked me to fix something I should
have been able to fix, and it stayed broken." Everything else is `0`.

### Error class

Use the existing `AfiError(code, message, remediation)` from
`auntiepypi/cli/_errors.py` (v0.0.1) for all `1` / `2` exits —
preserves the unified diagnostic shape across verbs. Doctor catches
its own internal raises and converts them; only the top-level
`cli/__init__.main()` exits the process.

`_actions/dispatch()` never raises — always returns an `ActionResult`.
Doctor's exit-2 logic is purely on the count of `actionable` entries
with `fix_ok == False`.

## Testing

### Layer 1 — Hermetic (PR-blocking, default)

| Test file | Covers |
|---|---|
| `tests/test_detect_config_strict.py` (new) | Cross-field validation matrix: each `managed_by` × required-companion combination; multi-violation single-pass output; closed-set rejections still work; `manual` and unset accept no companions |
| `tests/test_detect_config_lenient.py` (new) | `load_servers(strict=False)` returns `(specs, gaps)` tuple; gaps preserve line numbers; duplicate-name detection produces `ConfigGap(kind="duplicate", lines=[…])` |
| `tests/test_actions_command.py` (new) | Detached spawn happy path (FakeServer in subprocess); `Popen` failure (FileNotFoundError); child exits immediately (write a script that returns 1); spawned but never binds (script that sleeps without listening); log file written to `XDG_STATE_HOME` (override env var) |
| `tests/test_actions_systemd_user.py` (new) | Monkey-patch `subprocess.run` for `systemctl`; happy path; non-zero rc maps to `ok=False`; not-on-PATH; timeout. **No** real systemd interaction. |
| `tests/test_actions_reprobe.py` (new) | Re-probe loop: succeeds on attempt 1, succeeds on attempt 3, never succeeds (5s budget exhausted); flavor-fingerprint mismatch → `down` |
| `tests/test_actions_config_edit.py` (new) | Delete-whole-entry on a clean entry; refuse to delete on inline-table form; refuse on multi-line strings; numbered `.bak` selection (1 → 2 → 3); `.bak` race retry (mock `open(..., "x")` to raise once, then succeed); `.bak` exhaustion → `AfiError` |
| `tests/test_cli_doctor.py` (rewritten from v0.3.0) | Dry-run output for declared/half-supervised/scan-found/ambiguous mixes; `--apply` end-to-end with FakeRunner; `--decide` resolves duplicates; exit codes; JSON envelope shape; `TARGET` drill-down; unknown `TARGET` exit 0 |
| `tests/test_cli_overview_strict.py` (new) | Strict-mode validation surfaces in overview (exit 1); unaffected when config is clean |
| (deleted) `tests/test_probes_*.py` | gone with `_probes/` |
| (deleted) `tests/test_cli_packages.py` | gone with the `packages` noun |

### Test fakes

- `FakeRunner` (already exists in v0.3.0 doctor tests): preserved for
  `_actions/systemd_user.py`'s `subprocess.run` indirection.
- New `FakePopen` for `command.py`'s `Popen` indirection — same
  monkey-patch pattern. Lets us simulate "child still alive" vs
  "child exited" without spawning real processes for unit tests.
- For the `command.py` *integration* test, spawn a real Python script
  (`tests/fixtures/fake_pypiserver.py`) on an ephemeral port — same
  pattern v0.3.0's `_probes/` tests already used.

### Coverage

Stays at the project's existing **95 %** floor on `auntiepypi/`. New
`_actions/` code is structured for hermetic coverage.

### Layer 2 — live network

Not applicable. Lifecycle is purely local; no third-party hosts
contacted.

### Linters / CI

Unchanged from v0.3.0. The hermetic suite blocks PRs; no new
live-suite obligations. `flake8`, `pylint --errors-only`,
`bandit -r auntiepypi`, `markdownlint-cli2`, the portability lint, and
`steward doctor --scope self ../auntiepypi` all run as today.

## Catalog, learn, docs (mechanical)

- `auntiepypi/explain/catalog.py` — update `("doctor",)` for new flags
  and behavior; remove `("packages",)` and `("packages", "overview")`;
  update `("overview",)` to drop the noun-form mention.
- `auntiepypi/cli/_commands/learn.py` — update `_M_DOCTOR`; remove
  `_M_PACKAGES` if present; refresh examples; `planned[]` stays `[]`.
- `pyproject.toml` — version bumped to `0.4.0` by the `version-bump`
  skill at PR time; `requires-python = ">=3.12"` unchanged; zero
  runtime deps unchanged.
- `CLAUDE.md` — Status line moves to v0.4.0 doctor lifecycle; Roadmap
  entry for v0.4.0 marked shipped; v0.5.0 entry promoted to "own
  server + `auntie up`".
- `README.md` — example block shows `auntie doctor` with mixed entry
  classes; `auntie doctor --apply --decide=duplicate:main=1` example.
- `CHANGELOG.md` — `[0.4.0]` block: `### Added` — `_actions/`,
  `--apply`, `--decide`, numbered `.bak`, cross-field validation;
  `### Removed` — `--fix` flag, `packages` noun, `_probes/` module.
- `docs/about.md` — paragraph on doctor's new role (diagnose →
  remediate → act).
- `docs/deploy/` — README adds a "use with auntie doctor" subsection
  showing the `[[tool.auntiepypi.servers]]` declaration paired with
  the systemd unit.
- `.gitignore` — add `*.toml.*.bak`.
- `culture.yaml` — unchanged.

## Roadmap follow-ons (out of scope here)

- **v0.4.x** — additional strategies as needed: `docker`, `compose`,
  launchd on macOS. Each lands as one file under `_actions/` plus one
  entry in `_actions/__init__.ACTIONS`.
- **v0.5.0** — own-server + `auntie up` / `down` / `restart`. Brings in
  PID-file tracking under `state_root()`, signal-graceful-then-kill
  for stop, and a minimal first-party PEP 503 simple-index server we
  can run when no existing flavor is configured.
- **v1.0.0** — mesh-aware. Local index discoverable via Culture-mesh
  service registry; trust boundary documented in
  `docs/threat-model.md`.

## Verification

```bash
uv sync
uv run pytest -n auto --cov=auntiepypi --cov-report=term -v
uv run black --check auntiepypi tests
uv run isort --check-only auntiepypi tests
uv run flake8 auntiepypi tests
uv run pylint --errors-only auntiepypi
uv run bandit -c pyproject.toml -r auntiepypi
markdownlint-cli2 "**/*.md" "#node_modules"
bash .claude/skills/pr-review/scripts/portability-lint.sh

uv run auntie --version                                       # 0.4.0
uv run auntie doctor                                          # dry-run
uv run auntie doctor --json | jq '.summary'
uv run auntie doctor main                                     # drill-down
uv run auntie doctor --apply                                  # commit
uv run auntie doctor --apply --decide=duplicate:main=1
uv run auntie overview --json                                 # unchanged surface
uv run auntie learn --json | jq '.planned'                    # []
ls pyproject.toml.*.bak 2>/dev/null                           # numbered .bak files

(cd ../steward && uv run steward doctor --scope self ../auntiepypi)
```
