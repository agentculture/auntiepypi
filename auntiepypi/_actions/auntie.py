"""Strategy for `managed_by = "auntie"`: the first-party PEP 503 server.

Builds the argv at call time from ``[tool.auntiepypi.local]`` (or
defaults when the table is absent) and delegates to the ``command``
strategy. The bare-form CLI (``auntie up`` / ``down`` / ``restart``)
synthesizes a ``ServerSpec(name="auntie", managed_by="auntie", ...)``
that lacks a literal ``command`` field; this module fills it in by
shelling out to ``sys.executable -m auntiepypi._server …``.

Why delegate rather than duplicate command.py: the v0.5.0 lifecycle
contract (PID file + sidecar + reprobe + SIGTERM/SIGKILL escalation +
port-walk fallback + argv-match guard) is already covered by
``command``; reproducing it here would be ~150 lines of drift-prone
copy. The ``auntie`` strategy is "command with a derived argv."
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

from auntiepypi._actions import _pid
from auntiepypi._actions import command as _command
from auntiepypi._actions._action import ActionResult
from auntiepypi._actions._reprobe import probe
from auntiepypi._detect._config import ServerSpec, load_local_config
from auntiepypi._detect._detection import Detection
from auntiepypi._server._config import _DEFAULT_MAX_UPLOAD_BYTES, LocalConfig


def _argv(cfg: LocalConfig) -> tuple[str, ...]:
    args: list[str] = [
        sys.executable,
        "-m",
        "auntiepypi._server",
        "--host",
        cfg.host,
        "--port",
        str(cfg.port),
        "--root",
        str(cfg.root),
    ]
    if cfg.tls_enabled:
        # tls_enabled is True only when both cert and key are set, so
        # the asserts below are documentation, not runtime checks.
        args += ["--cert", str(cfg.cert), "--key", str(cfg.key)]
    if cfg.auth_enabled:
        args += ["--htpasswd", str(cfg.htpasswd)]
    for user in cfg.publish_users:
        args += ["--publish-user", user]
    if cfg.max_upload_bytes != _DEFAULT_MAX_UPLOAD_BYTES:
        args += ["--max-upload-bytes", str(cfg.max_upload_bytes)]
    return tuple(args)


def _check_readable(path: Path, label: str) -> str | None:
    """Return None when readable; else a short error detail."""
    if not path.exists():
        return f"{label} path not found: {path}"
    try:
        # Open + immediately close — verifies the spawned subprocess
        # would succeed at the same operation, without holding state.
        # ``os.access`` would be cheaper but is TOCTOU-prone and lies
        # about ACL-based denials on some platforms.
        path.open("rb").close()
    except OSError as err:
        return f"{label} not readable ({path}): {err}"
    return None


def _verify_tls_auth_paths(cfg: LocalConfig) -> ActionResult | None:
    """Pre-flight readability check on configured cert/key/htpasswd.

    Returns None when all configured paths are readable; otherwise
    an ActionResult(ok=False) with a clear detail. Surfacing the miss
    as a strategy-level failure (instead of a raise) preserves
    `--all`'s independent-dispatch semantics — a broken local server
    config doesn't strand the operator's declared mirrors.
    """
    if cfg.tls_enabled:
        # tls_enabled is True only when both cert and key are set.
        assert cfg.cert is not None and cfg.key is not None  # noqa: S101
        for path, label in ((cfg.cert, "cert"), (cfg.key, "key")):
            err = _check_readable(path, label)
            if err is not None:
                return ActionResult(ok=False, detail=err)
    if cfg.auth_enabled:
        assert cfg.htpasswd is not None  # noqa: S101 - invariant tripwire
        err = _check_readable(cfg.htpasswd, "htpasswd")
        if err is not None:
            return ActionResult(ok=False, detail=err)
    return None


def _materialize(declaration: ServerSpec) -> ServerSpec:
    """Fill in ``command`` from current ``[tool.auntiepypi.local]`` and
    flip ``managed_by`` so command.py recognizes it.

    The detection's ``host``/``port`` already came from the same
    config in the bare-form path, so they should agree — but the
    config is the source of truth on each call (handles the user
    editing pyproject between start and restart).
    """
    cfg = load_local_config()
    # ``dataclasses.replace`` is annotated as returning ``DataclassInstance``
    # in the typeshed stubs; cast back to ServerSpec for the call site.
    return cast(
        ServerSpec,
        replace(
            declaration,
            host=cfg.host,
            port=cfg.port,
            managed_by="command",
            command=_argv(cfg),
        ),
    )


def start(detection: Detection, declaration: ServerSpec) -> ActionResult:
    materialized = _materialize(declaration)
    cfg = load_local_config()

    # Idempotency: if the configured port is already serving 200 AND we
    # have a live PID file pointing at it, return success without
    # spawning a duplicate. Without this, repeated `auntie up` calls
    # either fail with a bind error or quietly orphan the previous
    # process by overwriting the PID file.
    if probe(detection, budget_seconds=0.5).status == "up":
        record = _pid.read(declaration.name, materialized.port)
        if record is not None:
            return ActionResult(
                ok=True,
                detail="already started",
                pid=record.pid,
            )

    # Pre-flight TLS / auth path checks. A missing cert or htpasswd at
    # spawn time would surface as a noisy traceback in the spawned
    # subprocess (visible only in the log file); catching it here turns
    # it into a clear ActionResult(ok=False) and, importantly, doesn't
    # strand declared servers under `auntie up --all`.
    tls_auth_err = _verify_tls_auth_paths(cfg)
    if tls_auth_err is not None:
        return tls_auth_err

    # Ensure the wheelhouse exists; the server itself tolerates missing
    # roots (returns empty index), but the operator probably wants the
    # directory created on first ``auntie up``.
    try:
        cfg.root.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        return ActionResult(
            ok=False,
            detail=f"could not create wheelhouse {cfg.root}: {err}",
        )
    return _command.start(detection, materialized)


def stop(detection: Detection, declaration: ServerSpec) -> ActionResult:
    return _command.stop(detection, _materialize(declaration))


def restart(detection: Detection, declaration: ServerSpec) -> ActionResult:
    return _command.restart(detection, _materialize(declaration))
