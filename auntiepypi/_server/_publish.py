"""Atomic upload writer for the v0.8.0 publish endpoint.

One function: :func:`write_upload`. Writes the distribution bytes to a
hidden temp file in ``cfg.root``, fsyncs, then atomically commits to
the final filename via :func:`os.link` — which **fails with
FileExistsError** if the target already exists. The pre-check
``target.exists()`` was a TOCTOU: on POSIX, ``os.rename`` would
silently overwrite if a competing writer materialised the file in the
window between the check and the rename. ``os.link`` is the no-clobber
primitive for "create only if absent" on POSIX.

Existing-file collisions return :class:`WriteResult` with status 409,
not 500: a name collision is a client error (pick a new version), not
a server problem. No overwrite, ever — yank/delete is out of scope for
v0.8.0 (operators delete the file from ``cfg.root`` directly to
retract).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

__all__ = ["WriteResult", "write_upload"]


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a single upload write.

    ``status`` mirrors the HTTP status the handler will return:
    201 (created), 409 (existing file), or 500 (write failure).
    ``written`` is the byte count on success, 0 otherwise.
    """

    status: int
    detail: str = ""
    written: int = 0


def _open_temp(root: Path) -> IO[bytes]:
    """``NamedTemporaryFile`` in the wheelhouse, hidden prefix.

    Hidden ``.upload-*`` keeps partial uploads invisible to the
    PEP 503 listing scanner. ``dir=root`` keeps the link/rename on the
    same filesystem (link is atomic only same-FS).
    """
    # `dir` is operator-controlled cfg.root, not /tmp; Sonar S5443
    # warning is spurious. Pre-check for `root` existence + writability
    # is implicit — a bad `root` raises OSError here, which the caller
    # catches and reports as 500.
    return tempfile.NamedTemporaryFile(  # noqa: S108  # NOSONAR python:S5443
        dir=root, delete=False, prefix=".upload-", suffix=".part"
    )


def write_upload(root: Path, filename: str, content: bytes) -> WriteResult:
    """Atomically write ``content`` to ``root/filename``.

    :returns: :class:`WriteResult` with status 201 on success, 409 if
        the target already exists, 500 on any filesystem error. The
        temp file is unlinked on every exit path so partial uploads
        never litter ``root``.

    Concurrency: ``os.link(tmp, target)`` is atomic and
    no-clobber on POSIX — concurrent writers of the same filename
    cannot race past the existence check, the way ``rename`` would.
    """
    target = root / filename
    tmp_path: Path | None = None
    try:
        tmp = _open_temp(root)
        tmp_path = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        finally:
            tmp.close()
        # No-clobber atomic commit: link the temp into the final name.
        # ``os.link`` raises FileExistsError if `target` already
        # exists — the contracted 409 path with no TOCTOU window.
        try:
            os.link(tmp_path, target)
        except FileExistsError:
            return WriteResult(status=409, detail="file already exists")
        return WriteResult(status=201, written=len(content))
    except OSError as err:
        # ENOSPC / EROFS / EACCES / temp-create failure on bad root.
        return WriteResult(status=500, detail=str(err))
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
