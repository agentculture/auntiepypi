"""Filesystem-walk wheelhouse: directory of dists → project index.

Pure-function module. No I/O beyond ``Path.iterdir`` / ``Path.is_file``.
The HTTP layer (``_app``) calls into here on every request — there is
no cache. Adding wheels is "drop them in the directory."

Distribution filename parsing:

- Wheels: PEP 427 — ``{name}-{version}(-{build tag})?-{python}-{abi}-{platform}.whl``
- Sdists: PEP 625 — ``{name}-{version}.tar.gz`` (also ``.zip`` for legacy)

Project bucketing: PEP 503 normalization
(``re.sub(r"[-_.]+", "-", name).lower()``) so ``Foo_Bar`` and
``foo-bar`` collapse to the same project.
"""

from __future__ import annotations

import re
from pathlib import Path

_NORMALIZE_RE = re.compile(r"[-_.]+")

# PEP 427: <distribution>-<version>(-<build_tag>)?-<py>-<abi>-<platform>.whl
# build_tag is digit-prefixed when present, but we don't enforce that here —
# the first two hyphen-segments are always (name, version).
_WHEEL_RE = re.compile(r"^(?P<name>[^-]+)-(?P<version>[^-]+)(-.*)?\.whl$")

# PEP 625 sdists: <name>-<version>.tar.gz (or .zip).
_SDIST_RE = re.compile(r"^(?P<name>.+)-(?P<version>[^-]+)\.(tar\.gz|zip)$")


def normalize(name: str) -> str:
    """PEP 503 canonical name: lowercase + collapse runs of [-_.] to '-'."""
    return _NORMALIZE_RE.sub("-", name).lower()


def parse_filename(filename: str) -> tuple[str, str] | None:
    """Return ``(project_name, version)`` for a PEP 427/625 dist file, else None.

    The name is returned **un-normalized** — call :func:`normalize` to
    get the PEP 503 canonical form for bucketing.
    """
    m = _WHEEL_RE.match(filename)
    if m:
        return m.group("name"), m.group("version")
    m = _SDIST_RE.match(filename)
    if m:
        return m.group("name"), m.group("version")
    return None


def list_projects(root: Path) -> dict[str, list[Path]]:
    """Walk ``root`` (one level), bucket dist files by normalized name.

    Missing or non-directory ``root`` → empty dict (server stays up so
    the user can populate the wheelhouse without restarting).
    """
    if not root.is_dir():
        return {}

    out: dict[str, list[Path]] = {}
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        parsed = parse_filename(entry.name)
        if parsed is None:
            continue
        project = normalize(parsed[0])
        out.setdefault(project, []).append(entry)
    return out
