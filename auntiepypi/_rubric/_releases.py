"""Shared parsing helpers for PyPI ``releases[].files`` entries."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_upload(file_dict: dict) -> datetime | None:
    """Return the file's upload datetime, or ``None`` if unusable / yanked.

    Tries ``upload_time_iso_8601`` first (always present in modern Warehouse
    payloads, RFC 3339), falls back to ``upload_time``. Returns ``None`` when
    the file is yanked or carries no parseable timestamp.
    """
    if file_dict.get("yanked"):
        return None
    ts = file_dict.get("upload_time_iso_8601") or file_dict.get("upload_time")
    if not ts:
        return None
    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def max_nonyanked_upload(files: list[dict] | None) -> datetime | None:
    """Latest upload datetime across non-yanked files for one version."""
    times = [t for t in (parse_upload(f) for f in files or []) if t is not None]
    return max(times) if times else None
