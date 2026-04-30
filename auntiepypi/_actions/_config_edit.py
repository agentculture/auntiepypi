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

from auntiepypi.cli._errors import EXIT_USER_ERROR, AfiError

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


def delete_entry(pyproject: Path, name: str) -> DeleteResult:
    """Remove the whole [[tool.auntiepypi.servers]] block whose entry has the given `name`.

    Refuses to delete inline-table forms or blocks containing multi-line
    strings (triple-quoted). On success, writes the file in place.
    """
    text = pyproject.read_text()
    lines = text.splitlines(keepends=True)

    if _INLINE_TABLE_RE.search(text):
        return DeleteResult(
            ok=False,
            reason="could not parse: inline-table form for [[tool.auntiepypi.servers]]",
        )

    blocks = list(_iter_blocks(lines))
    matched: tuple[int, int] | None = None
    for start, end in blocks:
        block_text = "".join(lines[start:end])
        if _TRIPLE_DOUBLE in block_text or _TRIPLE_SINGLE in block_text:
            block_name = _block_name(lines[start:end])
            if block_name == name:
                return DeleteResult(
                    ok=False,
                    reason="could not parse: multi-line string in target block",
                )
            continue
        if _block_name(lines[start:end]) == name:
            matched = (start, end)
            break

    if matched is None:
        return DeleteResult(ok=False, reason=f"entry not found: {name!r}")

    start, end = matched
    if end < len(lines) and lines[end].strip() == "":
        end += 1

    new_lines = lines[:start] + lines[end:]
    pyproject.write_text("".join(new_lines))
    return DeleteResult(ok=True, lines_removed=(start + 1, end))


def _iter_blocks(lines: list[str]):
    """Yield (start, end) for each `[[tool.auntiepypi.servers]]` block.

    `end` is exclusive (next-table-header line, or len(lines)).
    """
    n = len(lines)
    i = 0
    while i < n:
        stripped = lines[i].strip()
        if stripped == _SERVERS_HEADER:
            start = i
            j = i + 1
            while j < n:
                s = lines[j].strip()
                if s.startswith("[") and not s.startswith("[["):
                    break
                if s.startswith("[[") and s != _SERVERS_HEADER:
                    break
                if s == _SERVERS_HEADER:
                    break
                j += 1
            yield start, j
            i = j
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
