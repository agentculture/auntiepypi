"""Read ``[[tool.auntiepypi.servers]]`` from the nearest ``pyproject.toml``.

Re-uses :func:`auntiepypi._packages_config.find_pyproject` to locate the
config file (same walk-up-to-$HOME semantics as ``packages overview``).

Soft cases:

* No ``pyproject.toml`` found → :class:`ServersConfig` with no specs and
  ``scan_processes=False``. *Not an error* — the default-port scan still
  runs.
* ``pyproject.toml`` exists but no ``[tool.auntiepypi].servers`` array
  and no ``[tool.auntiepypi].scan_processes`` key → same.

Hard cases (raise :class:`ServerConfigError`):

* Missing ``name`` / ``flavor`` / ``port``.
* ``port`` outside ``1..65535``.
* ``flavor`` not in the closed set.
* ``managed_by`` not in the closed set (when present).
* Duplicate ``name`` within the array.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from auntiepypi._packages_config import find_pyproject

_VALID_FLAVORS = frozenset({"pypiserver", "devpi", "unknown"})
_VALID_MANAGED_BY = frozenset({"systemd-user", "docker", "compose", "command", "manual"})

_REQUIRED_COMPANIONS: dict[str, tuple[str, ...]] = {
    "systemd-user": ("unit",),
    "command": ("command",),
    "docker": ("dockerfile",),
    "compose": ("compose",),
}


class ServerConfigError(Exception):
    """Malformed ``[[tool.auntiepypi.servers]]`` table."""


@dataclass(frozen=True)
class ServerSpec:
    """One declared server. Minimal fields required; rest reserved for v0.3.0."""

    name: str
    flavor: str
    host: str
    port: int
    managed_by: str | None = None
    unit: str | None = None
    dockerfile: str | None = None
    compose: str | None = None
    service: str | None = None
    command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ServersConfig:
    """Full detection-related configuration."""

    specs: tuple[ServerSpec, ...] = ()
    scan_processes: bool = False


@dataclass(frozen=True)
class ConfigGap:
    """One cross-field validation issue, surfaced as remediation by doctor."""

    kind: str  # "missing-companion" | "duplicate"
    name: str  # entry name
    detail: str  # human-readable detail
    occurrences: tuple[int, ...] = ()
    """0-indexed occurrence positions within this duplicate group (e.g.
    ``(0, 1, 2)`` for a 3-way duplicate). Empty for kinds other than
    "duplicate". NOT array indices in the original
    ``[[tool.auntiepypi.servers]]`` list — those would diverge from
    `delete_entry`'s `which` parameter when duplicates are non-adjacent."""


def _spec_gaps(spec: ServerSpec) -> list[ConfigGap]:
    """Cross-field gaps for one spec; never raises."""
    gaps: list[ConfigGap] = []
    mode = spec.managed_by
    if mode is None or mode == "manual":
        return gaps
    for required in _REQUIRED_COMPANIONS.get(mode, ()):
        val = getattr(spec, required)
        if val is None or (isinstance(val, tuple) and not val):
            gaps.append(
                ConfigGap(
                    kind="missing-companion",
                    name=spec.name,
                    detail=f'managed_by="{mode}" requires `{required}`',
                )
            )
    return gaps


def _duplicate_gaps(parsed: list[ServerSpec]) -> list[ConfigGap]:
    """File-level duplicate-name detection. Returns one ConfigGap per duplicated name."""
    by_name: dict[str, list[int]] = {}
    for idx, spec in enumerate(parsed):
        by_name.setdefault(spec.name, []).append(idx)
    gaps: list[ConfigGap] = []
    for name, indices in by_name.items():
        if len(indices) >= 2:
            gaps.append(
                ConfigGap(
                    kind="duplicate",
                    name=name,
                    detail=f"duplicate name {name!r} appears {len(indices)} times",
                    occurrences=tuple(range(len(indices))),
                )
            )
    return gaps


def _str_or_none(entry: dict, key: str, name: str, idx: int) -> str | None:
    val = entry.get(key)
    if val is None:
        return None
    if not isinstance(val, str):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: {key!r} must be a string"
        )
    return val


def _parse_command(entry: dict, name: str, idx: int) -> tuple[str, ...] | None:
    command = entry.get("command")
    if command is None:
        return None
    if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'command' must be a list of strings"
        )
    return tuple(command)


def _validate_required_strings(entry: dict, idx: int) -> tuple[str, str]:
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}]: missing 'name' (must be a non-empty string)"
        )
    flavor = entry.get("flavor")
    if not isinstance(flavor, str):
        raise ServerConfigError(f"[[tool.auntiepypi.servers]][{idx}] {name!r}: missing 'flavor'")
    if flavor not in _VALID_FLAVORS:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: invalid 'flavor': "
            f"{flavor!r} (valid: {sorted(_VALID_FLAVORS)})"
        )
    return name, flavor


def _validate_port(entry: dict, name: str, idx: int) -> int:
    if "port" not in entry:
        raise ServerConfigError(f"[[tool.auntiepypi.servers]][{idx}] {name!r}: missing 'port'")
    port = entry["port"]
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'port' out of range "
            f"(got {port!r}; expected int 1..65535)"
        )
    return port


def _validate_managed_by(entry: dict, name: str, idx: int) -> str | None:
    managed_by = entry.get("managed_by")
    if managed_by is None:
        return None
    if managed_by not in _VALID_MANAGED_BY:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: invalid 'managed_by': "
            f"{managed_by!r} (valid: {sorted(_VALID_MANAGED_BY)})"
        )
    return managed_by


def _parse_spec(entry: object, idx: int) -> ServerSpec:
    if not isinstance(entry, dict):
        raise ServerConfigError(f"[[tool.auntiepypi.servers]][{idx}] is not a table")
    name, flavor = _validate_required_strings(entry, idx)
    port = _validate_port(entry, name, idx)
    host = entry.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host:
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]][{idx}] {name!r}: 'host' must be a non-empty string"
        )
    return ServerSpec(
        name=name,
        flavor=flavor,
        host=host,
        port=port,
        managed_by=_validate_managed_by(entry, name, idx),
        unit=_str_or_none(entry, "unit", name, idx),
        dockerfile=_str_or_none(entry, "dockerfile", name, idx),
        compose=_str_or_none(entry, "compose", name, idx),
        service=_str_or_none(entry, "service", name, idx),
        command=_parse_command(entry, name, idx),
    )


def load_servers(start: Path | None = None) -> ServersConfig:
    """Strict-mode loader. Raises ``ServerConfigError`` on any violation."""
    found = find_pyproject(start)
    if found is None:
        return ServersConfig()
    try:
        with found.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ServerConfigError(f"cannot parse {found}: {err}") from err

    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        return ServersConfig()
    auntie_table = tool.get("auntiepypi", {})
    if not isinstance(auntie_table, dict):
        return ServersConfig()
    raw_specs = auntie_table.get("servers", [])
    scan_processes = bool(auntie_table.get("scan_processes", False))
    if not isinstance(raw_specs, list):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]] must be an array of tables, got "
            f"{type(raw_specs).__name__}"
        )

    parsed: list[ServerSpec] = [_parse_spec(entry, idx) for idx, entry in enumerate(raw_specs)]

    violations: list[str] = []
    for spec in parsed:
        for gap in _spec_gaps(spec):
            violations.append(f"{gap.name}: {gap.detail}")
    for gap in _duplicate_gaps(parsed):
        violations.append(gap.detail)

    if violations:
        bullets = "\n  - ".join(violations)
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]] cross-field validation failed:\n  - {bullets}\n"
            f"hint: run `auntie doctor` for guided remediation."
        )

    return ServersConfig(specs=tuple(parsed), scan_processes=scan_processes)


def load_servers_lenient(start: Path | None = None) -> tuple[ServersConfig, list[ConfigGap]]:
    """Lenient counterpart to `load_servers` — used only by `doctor`.

    Never raises on cross-field violations or duplicate names; surfaces
    them as ``ConfigGap`` entries. Structural errors (bad types, port
    out of range, unknown closed-set values) DO still raise, because
    those are parser-level, not cross-field.
    """
    found = find_pyproject(start)
    if found is None:
        return ServersConfig(), []

    try:
        with found.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as err:
        raise ServerConfigError(f"cannot parse {found}: {err}") from err

    tool = data.get("tool", {})
    if not isinstance(tool, dict):
        return ServersConfig(), []
    auntie_table = tool.get("auntiepypi", {})
    if not isinstance(auntie_table, dict):
        return ServersConfig(), []
    raw_specs = auntie_table.get("servers", [])
    scan_processes = bool(auntie_table.get("scan_processes", False))
    if not isinstance(raw_specs, list):
        raise ServerConfigError(
            f"[[tool.auntiepypi.servers]] must be an array of tables, got "
            f"{type(raw_specs).__name__}"
        )

    parsed: list[ServerSpec] = [_parse_spec(entry, idx) for idx, entry in enumerate(raw_specs)]

    gaps: list[ConfigGap] = []
    for spec in parsed:
        gaps.extend(_spec_gaps(spec))
    gaps.extend(_duplicate_gaps(parsed))

    return ServersConfig(specs=tuple(parsed), scan_processes=scan_processes), gaps
