# auntiepypi v0.5.0 — lifecycle verbs (`up` / `down` / `restart`)

**Status:** approved (brainstorm 2026-04-30; plan
`$CLAUDE_HOME/plans/dazzling-snacking-kay.md`).

**Predecessor:** `2026-04-30-auntiepypi-v0.4.0-doctor-lifecycle-design.md`.

## Why this milestone

v0.4.0 shipped `auntie doctor --apply` as a *starter*: it can dispatch
`_actions/<strategy>.apply()` to start a half-supervised server and
mutate `pyproject.toml` to delete broken declarations. It cannot
**stop** anything. The asymmetry is structural:

- `command`-managed servers are detached `Popen(start_new_session=True)`
  children whose PIDs `command.apply()` returns and forgets. Auntie
  has no way to terminate them later.
- `systemd-user` strategy starts units but never invokes
  `systemctl --user stop`.
- `doctor --apply` cannot offer a "stop and reconfigure" workflow
  because there is no stop primitive to call.

`auntiepypi/_actions/command.py` already announces the gap:

```python
# Doctor does NOT track the child past spawn. ``auntie down`` (v0.5.0)
# will own process-tracking.
```

v0.5.0 closes the gap with three lifecycle verbs and a widened
strategy contract. Crucially, **the bare invocation `auntie up` is
reserved for v0.6.0**, where it will start auntie's own first-party
PEP 503 simple-index server. v0.5.0 only delivers the
`<name>` / `--all` paths so that the bare form remains free.

## Decisions (locked)

### D1. Immediate-action verbs (no `--apply` gate)

`auntie up <name>` starts the server now. `auntie down <name>` stops
it now. `auntie restart <name>` does both now. There is no dry-run
gate.

**Rationale.** The dry-run-first rule in this repo exists to protect
*persistent state* — `pyproject.toml`, mainly. Lifecycle verbs operate
on *volatile* process state, which is recoverable by re-running the
verb. The mental model is `systemctl start`, which has no `--really`
flag for the same reason. Idempotency (D5) makes accidents harmless.

**Cost.** One verb in this repo doesn't follow the dry-run-first
convention. Documented in CLAUDE.md and in the verbs' `--help` text.

### D2. Eager PID file + argv-matched port-walk fallback

`command.start()` writes a PID record on success.
`command.stop()` reads the PID and signals it. Two-tier discovery:

1. **Primary: PID file.** `$XDG_STATE_HOME/auntiepypi/<slug>.pid`
   (raw integer) plus `<slug>.json` sidecar (pid, argv, started_at,
   port). Written atomically by `command.start()` after a successful
   re-probe.
2. **Fallback: port-walk + argv match.** If no PID file exists,
   `command.stop()` walks `/proc/net/tcp` + `/proc/<pid>/fd/*` to find
   the listener bound to `declaration.port`. If found, compare the
   discovered process's argv against the declared `command`. If they
   agree (basename-of-argv0 + presence of declared tokens), kill.
   If they disagree, refuse with a footgun-guard error.

Liveness is checked at read time: `os.kill(pid, 0)` against the file's
PID; ESRCH means the process is gone, so the file is stale and gets
cleaned up silently.

`systemd-user` is unaffected. systemd owns the unit's process state;
auntie shells out to `systemctl --user {start,stop,restart} <unit>`
and doesn't track PIDs.

**Rationale.** The PID file is portable, simple, race-free at the
auntie boundary. The port-walk fallback covers the case where someone
started the server outside `auntie up` (a previous shell, a manual
test) and now wants `auntie down` to clean it up. The argv match
prevents accidentally killing an unrelated process bound to the same
port.

**Cost.** Linux-only fallback. Non-Linux platforms get
`find_by_port → None` and a graceful "already stopped" no-op when
no PID file exists. The argv-match heuristic may reject legitimate
processes spawned with subtly different argv; a `--force` opt-out
will land in v0.5.x if it bites.

### D3. Three sibling strategy functions

Today each strategy module exposes a single `apply(detection,
declaration) -> ActionResult`. v0.5.0 widens this to:

```python
# auntiepypi/_actions/<strategy>.py
def start(detection, declaration) -> ActionResult: ...
def stop(detection, declaration) -> ActionResult: ...
def restart(detection, declaration) -> ActionResult: ...
```

`_actions/__init__.py:ACTIONS` becomes `dict[str, dict[str, Strategy]]`:

```python
ACTIONS = {
    "systemd-user": {"start": ..., "stop": ..., "restart": ...},
    "command":      {"start": ..., "stop": ..., "restart": ...},
}

def dispatch(
    action: Literal["start", "stop", "restart"],
    detection: Detection,
    declaration: ServerSpec,
) -> ActionResult: ...
```

The internal rename `apply` → `start` honestly reflects what doctor
has been calling all along.

**Rationale.** Strategy boundary matches lifecycle boundary. Each
function gets type-safe inputs/outputs without internal switch
statements. `restart` is free to be smarter than naive stop+start
(D5). Doctor's `--apply` rewires to `dispatch("start", ...)`.

**Cost.** One mechanical rename + interface widening. The change is
internal; no public API is affected.

### D4. Bare verb reserved for v0.6.0

```text
auntie up                  → exit 1; "first-party auntie server lands in
                                       v0.6.0; for now use `auntie up <name>`
                                       or `auntie up --all`"
auntie up <name>           → resolve and dispatch("start", ...)
auntie up --all            → bulk-act on every supervised declaration
auntie up --all --json     → JSON envelope
auntie up --decide=duplicate:NAME=N <name>   → ambiguity resolution
```

Symmetric for `down` and `restart`. `--all` skips
`managed_by ∈ {manual, docker, compose, unset}` with a per-line note;
the explicit single-name form refuses with exit 1 for those modes.

Resolution priority for `<name>`: detection name first, configured
server name second (mirrors `auntie overview <TARGET>` and `auntie
doctor [TARGET]`).

**Exit codes.** Same contract as doctor:

- `0` — every targeted server reached the desired state
- `1` — user error or config error before any action attempted
- `2` — at least one targeted server did not reach the desired state

**Rationale.** Reserving the bare form lets v0.6.0 introduce
`auntie up` as "start the first-party simple-index server" without
breaking v0.5.0's `auntie up <name>` ergonomics. Explicit `--all` is
a footgun guard ("did I really mean every dev server?"). Reusing
`--decide=duplicate:NAME=N` keeps the ambiguity-resolution UX uniform
across doctor and the lifecycle verbs.

### D5. Strategy-native restart; sidecar advisory; idempotency

**`systemd-user.restart`** uses `systemctl --user restart <unit>`
directly. It's atomic, faster than stop+start, and lets systemd
preserve invariants the unit file declares.

**`command.restart`** does `stop()` then `start()`. The new spawn
re-uses the **current** `[[tool.auntiepypi.servers]].command` from
`pyproject.toml` — never the sidecar argv. If the sidecar argv
disagrees with the current spec, a single drift line is written to
the existing log file (no failure):

```text
=== 2026-04-30T18:42:00Z: argv changed since last start ===
prev: ['pypi-server', 'run', '-p', '18080', '.']
cur:  ['pypi-server', 'run', '-p', '18081', '.']
```

**Idempotency.**

- `up` already-up → `ok=True, detail="already running"` (re-probe
  confirms; no re-spawn).
- `down` already-down → `ok=True, detail="already stopped"` (no PID
  to kill; any stale PID file is cleaned up).
- `restart` always tears down and brings up (even if already up;
  user intent is "make it match current config now").

**Stale state.**

- `up` with stale PID file: log `"stale PID for <name>; cleaning up"`,
  delete file, fresh spawn.
- `down` with stale PID: success no-op + cleanup.

**Rationale.** Source of truth is always current `pyproject.toml`.
Users edit config to change behavior; if `restart` ignored the edit
they'd be debugging "why didn't it pick up my change." The sidecar
exists only to remember "what was last spawned" so `down` knows what
argv to verify.

## Architecture

### File layout (after v0.5.0)

```text
auntiepypi/_actions/
├── __init__.py          # ACTIONS dict-of-dicts; dispatch(action, ...)
├── _action.py           # ActionResult (unchanged)
├── _logs.py             # slugify, state_root, path_for (unchanged)
├── _pid.py              # NEW: PidRecord, write/read/clear/find_by_port
├── _reprobe.py          # widened: probe(detection, *, desired="up")
├── _config_edit.py      # unchanged
├── command.py           # start (writes PID), stop, restart
└── systemd_user.py      # start, stop, restart

auntiepypi/cli/_commands/
├── up.py                # NEW
├── down.py              # NEW
├── restart.py           # NEW
├── doctor.py            # one call site: dispatch("start", ...)
└── ...
```

### Strategy contract (post-task-2)

```python
# auntiepypi/_actions/__init__.py
from typing import Callable, Literal

Strategy = Callable[[Detection, ServerSpec], ActionResult]
StrategyMap = dict[str, Strategy]

ACTIONS: dict[str, StrategyMap] = {
    "systemd-user": {
        "start":   _systemd_user.start,
        "stop":    _systemd_user.stop,
        "restart": _systemd_user.restart,
    },
    "command": {
        "start":   _command.start,
        "stop":    _command.stop,
        "restart": _command.restart,
    },
}

_NOT_IMPLEMENTED: frozenset[str] = frozenset({"docker", "compose"})

def dispatch(
    action: Literal["start", "stop", "restart"],
    detection: Detection,
    declaration: ServerSpec,
) -> ActionResult:
    """Route to the strategy/action; never raises."""
```

`dispatch()` returns a uniform `ActionResult(ok=False, detail=...)`
for `managed_by ∈ {manual, docker, compose, unset}`, mirroring the
v0.4.0 behavior.

### PID + sidecar contract

```python
# auntiepypi/_actions/_pid.py
@dataclass(frozen=True)
class PidRecord:
    pid: int
    argv: tuple[str, ...]
    started_at: str   # ISO 8601 UTC
    port: int

def write(name: str, *, pid: int, argv: Sequence[str], port: int) -> None:
    """Write <name>.pid (text int) and <name>.json (sidecar) atomically."""

def read(name: str) -> PidRecord | None:
    """Return parsed record, or None if absent / stale (with cleanup).

    Liveness check: os.kill(record.pid, 0). ESRCH → stale → clear and
    return None. EPERM → live but not ours → return record (the caller
    will likely fail the kill, but that's their concern)."""

def clear(name: str) -> None:
    """Delete <name>.pid and <name>.json. Idempotent."""

def find_by_port(port: int, *, expected_argv: Sequence[str]) -> int | None:
    """Linux-only: walk /proc/net/tcp + /proc/<pid>/fd/* for the listener
    on `port`. Return its PID iff its argv matches `expected_argv`
    (basename-of-argv0 equality + every non-flag token in expected_argv
    appears in discovered argv). Return None on non-Linux or no match."""
```

Files cluster with the v0.4.0 log file:
`$XDG_STATE_HOME/auntiepypi/<slug>.{log,pid,json}`. Slug derivation
reuses `auntiepypi._actions._logs.slugify`.

**Atomic write.** `<slug>.pid.tmp` is created via
`tempfile.mkstemp(dir=state_root, prefix=f"{slug}.pid.", suffix=".tmp")`,
written, fsynced, then `os.replace`d onto `<slug>.pid`. Same pattern
for the sidecar. This mirrors the v0.4.0 `_config_edit._atomic_write_pyproject`
pattern that cleared the SonarCloud S2083 BLOCKER.

### Re-probe widening

```python
# auntiepypi/_actions/_reprobe.py
def probe(
    detection: Detection,
    *,
    budget_seconds: float = 5.0,
    desired: Literal["up", "down"] = "up",
    _sleep=time.sleep, _now=time.monotonic,
) -> ReprobeResult:
    """Poll until status matches `desired` or budget exhausted.

    `desired="up"` (default): existing v0.4.0 behavior, exit early on
    "up". `desired="down"` (new in v0.5.0): exit early on "down" or
    "absent", continue while status is "up"."""
```

All v0.4.0 callers pass `desired="up"` implicitly via the default.

### CLI verb shape

```python
# auntiepypi/cli/_commands/up.py (down.py, restart.py mirror this)

def add_parser(subparsers):
    p = subparsers.add_parser("up", help="start a declared server")
    p.add_argument("target", nargs="?", default=None,
                   help="server name; omit to require --all")
    p.add_argument("--all", action="store_true", dest="all_servers",
                   help="act on every supervised declaration")
    p.add_argument("--decide", action="append", default=[],
                   help="resolve ambiguity, e.g. duplicate:NAME=N")
    p.add_argument("--json", action="store_true",
                   help="JSON envelope instead of text")
    p.set_defaults(func=cmd_up)


def cmd_up(args) -> int:
    if args.target is None and not args.all_servers:
        # Bare form is reserved for v0.6.0
        sys.stderr.write(_BARE_UP_RESERVED + "\n")
        return EXIT_USER_ERROR
    ...
```

JSON envelope (uniform across the three verbs):

```json
{
  "verb": "up",
  "results": [
    {"name": "main",       "ok": true,  "detail": "started", "pid": 12345},
    {"name": "secondary",  "ok": true,  "detail": "already running"},
    {"name": "broken-one", "ok": false, "detail": "command not found: ..."}
  ]
}
```

Exit code derived from results: `0` iff all `ok=true`; `2` otherwise.

## Testing strategy

Inherits the v0.4.0 patterns:

- `tests/test_actions_pid.py` — round-trip; stale detection;
  `find_by_port` argv match (positive + negative); non-Linux platform
  shim returning None.
- `tests/test_actions_command_lifecycle.py` — `command.stop` clean
  path; SIGKILL escalation; stale PID cleanup; missing PID +
  port-walk match; missing PID + port-walk argv-mismatch refusal.
  `command.restart` clean path; argv drift logged; restart-when-down.
- `tests/test_actions_systemd_user_lifecycle.py` — `stop`, `restart`
  via `RUN` indirection (already used by `start`).
- `tests/test_cli_{up,down,restart}.py` — bare exit 1
  (`EXIT_USER_ERROR`); `<name>` happy path; refused `managed_by=manual`;
  `--all` aggregate exit codes; `--decide` resolution; `--json` shape.
- Existing v0.4.0 tests must continue passing with the renamed
  `apply` → `start` and the widened `dispatch(action, ...)`.

Coverage floor stays at 94% (v0.4.0 baseline). Lifecycle stop/restart
paths are heavily mockable, so 95% is plausible — defer to what
actually lands.

## Out of scope (deferred to v0.6.0)

- First-party PEP 503 simple-index server (`auntie up` bare form).
- `[tool.auntiepypi.local]` config block for the first-party server
  (port, wheelhouse path, auth model).
- HTTPS termination.
- `auntie publish` upload path.
- Cross-machine state sharing for the PID file (state stays per-host
  under XDG; mesh-aware service registry is also v0.6.0+).

## Risks / open issues

- **argv-match heuristic.** Basename(argv[0]) + every non-flag token
  from declared command must appear in discovered argv. False
  negatives possible (e.g. user ran `pypi-server -p 18080` but
  declared `["pypi-server", "run", "-p", "18080", "."]`). v0.5.x
  may add `--force` to bypass.
- **Sidecar drift detection.** `command.restart` only logs; doesn't
  surface drift to the CLI summary. Consider promoting to a JSON
  field (`drift_detected: bool`) if it becomes useful.
- **PID file race on shared state dir.** Two `auntie up <name>`
  invocations against the same name in parallel could clobber.
  Auntie is single-user per host; this is acceptable for v0.5.0.
- **`find_by_port` on macOS / BSD.** Returns None; the documented
  behavior is "no fallback, declare your servers." Future work could
  add a `lsof`-based shim.

## Tasks

See plan: `$CLAUDE_HOME/plans/dazzling-snacking-kay.md`. Fourteen
tasks; task 1 is this spec, tasks 2–14 deliver the implementation.
