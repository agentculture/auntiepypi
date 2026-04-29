"""Frozen :class:`Detection` dataclass + JSON-section renderer.

Each detector produces a list of these. The CLI renders them via
:meth:`Detection.to_section`.
"""

from __future__ import annotations

from dataclasses import dataclass

_LIGHT_MAP: dict[str, str] = {"up": "green", "down": "red", "absent": "unknown"}


@dataclass(frozen=True)
class Detection:
    """One PyPI server visible to the local box.

    ``status``: ``"up"`` (TCP+HTTP healthy), ``"down"`` (TCP open, HTTP
    unhealthy), ``"absent"`` (nothing listening).

    ``source``: ``"declared"`` (came from ``[[tool.auntiepypi.servers]]``),
    ``"port"`` (default port scan), ``"proc"`` (``--proc`` ``/proc`` scan).
    """

    name: str
    flavor: str  # "pypiserver" | "devpi" | "unknown"
    host: str
    port: int
    url: str
    status: str  # "up" | "down" | "absent"
    source: str  # "declared" | "port" | "proc"
    pid: int | None = None
    cmdline: str | None = None
    detail: str | None = None
    # Reserved declaration metadata (echoed verbatim; v0.2.0 does not act on it).
    managed_by: str | None = None
    unit: str | None = None
    dockerfile: str | None = None
    compose: str | None = None
    service: str | None = None
    command: tuple[str, ...] | None = None

    def to_section(self) -> dict:
        """Render as ``{category, title, light, fields}`` for the JSON envelope."""
        light = _LIGHT_MAP.get(self.status, "unknown")
        fields: list[dict] = [
            {"name": "flavor", "value": self.flavor},
            {"name": "host", "value": self.host},
            {"name": "port", "value": str(self.port)},
            {"name": "url", "value": self.url},
            {"name": "status", "value": self.status},
            {"name": "source", "value": self.source},
        ]
        optional: list[tuple[str, object]] = [
            ("pid", self.pid),
            ("cmdline", self.cmdline),
            ("detail", self.detail),
            ("managed_by", self.managed_by),
            ("unit", self.unit),
            ("dockerfile", self.dockerfile),
            ("compose", self.compose),
            ("service", self.service),
            ("command", self.command),
        ]
        for opt_name, opt_val in optional:
            if opt_val is None:
                continue
            value = " ".join(opt_val) if isinstance(opt_val, tuple) else str(opt_val)
            fields.append({"name": opt_name, "value": value})
        return {
            "category": "servers",
            "title": self.name,
            "light": light,
            "fields": fields,
        }
