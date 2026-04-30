"""Narrow `pyproject.toml` mutations: delete-whole-entry + numbered `.bak` snapshot.

Stdlib-only. We do NOT round-trip TOML (no tomlkit). We do line-scoped
edits inside a known table and refuse anything we can't unambiguously
parse.

Recovery: numbered `pyproject.toml.<N>.bak` files (never overwritten).
``snapshot`` is called once at the start of any mutating ``--apply``
session, before any edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from auntiepypi._errors import EXIT_USER_ERROR, AfiError

_SERVERS_HEADER = "[[tool.auntiepypi.servers]]"
_INLINE_TABLE_RE = re.compile(r"\[\[tool\.auntiepypi\.servers\]\]\s*\{")
_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]*)"\s*(?:#.*)?$')
# Multi-line string sentinels — defined as constants to avoid parser confusion
# with triple-quote sequences embedded in source literals.
_TRIPLE_DOUBLE = '"' * 3
_TRIPLE_SINGLE = "'" * 3


@dataclass(frozen=True)
class DeleteResult:
    """Outcome of a `delete_entry` call.

    :param lines_removed: ``(first_line, last_line)`` 1-indexed, **inclusive** —
        the same form the doctor audit log prints (e.g. ``"removed lines
        42-49"``). ``None`` when ``ok`` is ``False``.
    """

    ok: bool
    reason: str = ""
    lines_removed: tuple[int, int] | None = None


def _validate_pyproject_path(pyproject: Path) -> Path:
    """Defensive: ensure the path is a regular file named ``pyproject.toml``.

    Returns the resolved path. Raises ``AfiError(code=1)`` otherwise.

    ``find_pyproject()`` already returns only legitimate pyproject.toml paths
    via a CWD walk-up, so this is defense-in-depth: it makes the contract
    explicit and prevents accidental writes to arbitrary files if a future
    caller invokes these functions with an unvetted Path.
    """
    target = pyproject.resolve()
    if target.name != "pyproject.toml":
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"refusing to operate on non-pyproject.toml file: {pyproject!r}",
            remediation="this is a defensive guard; report a bug if seen in normal use",
        )
    if not target.is_file():
        raise AfiError(
            code=EXIT_USER_ERROR,
            message=f"refusing to operate on non-regular file: {pyproject!r}",
            remediation="this is a defensive guard; report a bug if seen in normal use",
        )
    return target


def delete_entry(pyproject: Path, name: str, *, which: int = 0) -> DeleteResult:
    """Remove the [[tool.auntiepypi.servers]] block whose entry has the given `name`.

    :param which: 0-indexed occurrence to delete when multiple blocks share the
        same `name` (used by ``--decide=duplicate:NAME=N`` resolution). Default
        0 = delete the first matching block.

    Refuses to delete inline-table forms or blocks containing multi-line
    strings. On success, writes the file in place.
    """
    pyproject = _validate_pyproject_path(pyproject)
    text = pyproject.read_text()
    lines = text.splitlines(keepends=True)

    if _INLINE_TABLE_RE.search(text):
        return DeleteResult(
            ok=False,
            reason="could not parse: inline-table form for [[tool.auntiepypi.servers]]",
        )

    # Collect all blocks matching `name`.  Bail out early if any matching
    # block contains triple-quoted strings (unparseable).
    blocks = list(_iter_blocks(lines))
    matching: list[tuple[int, int]] = []
    for start, end in blocks:
        block_lines = lines[start:end]
        block_text = "".join(block_lines)
        if _block_name(block_lines) != name:
            continue
        if _TRIPLE_DOUBLE in block_text or _TRIPLE_SINGLE in block_text:
            return DeleteResult(
                ok=False,
                reason="could not parse: multi-line string in target block",
            )
        matching.append((start, end))

    if not matching:
        return DeleteResult(ok=False, reason=f"entry not found: {name!r}")

    if which >= len(matching):
        return DeleteResult(
            ok=False,
            reason=f"no occurrence at index {which} for {name!r} ({len(matching)} found)",
        )

    start, end = matching[which]
    if end < len(lines) and lines[end].strip() == "":
        end += 1

    new_lines = lines[:start] + lines[end:]
    # `pyproject` is validated by _validate_pyproject_path() at function entry:
    # the resolved path to a real file named "pyproject.toml". Not user-controlled
    # in the data-flow sense S2083 targets — comes from find_pyproject()'s CWD walk.
    pyproject.write_text("".join(new_lines))  # NOSONAR pythonsecurity:S2083
    return DeleteResult(ok=True, lines_removed=(start + 1, end))


def _find_block_end(lines: list[str], start: int, n: int) -> int:
    """Return the exclusive end index of the ``[[tool.auntiepypi.servers]]`` block at ``start``."""
    j = start + 1
    while j < n:
        s = lines[j].strip()
        if s.startswith("[[") and s != _SERVERS_HEADER:
            break
        if s.startswith("[") and not s.startswith("[["):
            break
        if s == _SERVERS_HEADER:
            break
        j += 1
    return j


def _iter_blocks(lines: list[str]):
    """Yield (start, end) for each `[[tool.auntiepypi.servers]]` block.

    `end` is exclusive (next-table-header line, or len(lines)).
    """
    n = len(lines)
    i = 0
    while i < n:
        if lines[i].strip() == _SERVERS_HEADER:
            end = _find_block_end(lines, i, n)
            yield i, end
            i = end
        else:
            i += 1


def _block_name(block_lines: list[str]) -> str | None:
    for line in block_lines:
        m = _NAME_RE.match(line)
        if m:
            return m.group(1)
    return None


_MAX_BAK_RETRIES = 5


def snapshot(pyproject: Path) -> Path:
    """Write `<name>.<N>.bak` with the next free `N` (>= existing max + 1).

    Raises ``AfiError`` (code 1) on exhaustion after retries.
    """
    pyproject = _validate_pyproject_path(pyproject)
    parent = pyproject.parent
    stem = pyproject.name
    pattern = re.compile(rf"^{re.escape(stem)}\.(\d+)\.bak$")
    existing = [int(m.group(1)) for p in parent.iterdir() if (m := pattern.match(p.name))]
    n = (max(existing) + 1) if existing else 1
    src = pyproject.read_bytes()
    for _ in range(_MAX_BAK_RETRIES):
        bak = parent / f"{stem}.{n}.bak"
        try:
            with open(bak, "xb") as f:
                f.write(src)
            return bak
        except FileExistsError:
            n += 1
            continue
    raise AfiError(
        code=EXIT_USER_ERROR,
        message=f"could not find a free `.bak` slot after {_MAX_BAK_RETRIES} tries",
        remediation=f"clean up old `.bak` files in {parent}",
    )
