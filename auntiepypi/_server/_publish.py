"""Atomic upload writer for the v0.8.0 publish endpoint.

One function: :func:`write_upload`. Writes the distribution bytes to a
hidden temp file in ``cfg.root``, fsyncs, then ``os.rename`` to the
final filename. Same-filesystem rename is atomic on POSIX, so the
final file either exists fully or doesn't exist — no half-uploaded
wheels left lying around when the server crashes mid-write.

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


def write_upload(root: Path, filename: str, content: bytes) -> WriteResult:
    """Atomically write ``content`` to ``root/filename``.

    :returns: :class:`WriteResult` with status 201 on success, 409 if
        the target already exists, 500 on filesystem error. The temp
        file is unlinked on every error path so partial uploads never
        litter ``root``.
    """
    target = root / filename
    if target.exists():
        return WriteResult(status=409, detail="file already exists")

    # NamedTemporaryFile in `dir=root` keeps the rename on the same
    # filesystem (atomic). Sonar S5443 fires on /tmp use; here `dir`
    # is operator-controlled cfg.root, not /tmp, so the warning is
    # spurious — see _publish docstring above.
    tmp = tempfile.NamedTemporaryFile(  # noqa: S108  # NOSONAR python:S5443
        dir=root, delete=False, prefix=".upload-", suffix=".part"
    )
    tmp_path = Path(tmp.name)
    try:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.rename(tmp_path, target)
        return WriteResult(status=201, written=len(content))
    except OSError as err:
        # Filesystem failure (ENOSPC, EROFS, EACCES). Always clean up
        # the temp before returning so we don't leave .upload-*.part
        # files behind.
        return WriteResult(status=500, detail=str(err))
    finally:
        # Best-effort cleanup. After a successful rename the temp
        # path no longer exists, so unlink with missing_ok=True is
        # cheap and safe.
        try:
            tmp.close()
        except OSError:
            pass
        tmp_path.unlink(missing_ok=True)
