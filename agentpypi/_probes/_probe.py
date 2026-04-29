"""Uniform interface for one flavor of PyPI server.

Each `agentpypi/_probes/<flavor>.py` module instantiates one ``Probe`` and
exposes it as ``PROBE``. The runtime checker in :mod:`._runtime` consumes
``Probe`` instances; ``overview`` and ``doctor`` iterate
:data:`agentpypi._probes.PROBES`.

Adding a new flavor is one file: define another ``Probe`` and append to
``PROBES`` in :mod:`agentpypi._probes`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Probe:
    """One PyPI server flavor.

    :param name: Stable identifier (``devpi``, ``pypiserver``, ...).
    :param default_port: Conventional port for this flavor.
    :param health_path: Path appended to the host:port for the health check
        (e.g. ``/+api`` for devpi).
    :param start_command: Argv tuple ``doctor --fix`` runs to bring the
        server up. Empty tuple = no auto-start; ``doctor`` reports the
        flavor as needing manual remediation.
    """

    name: str
    default_port: int
    health_path: str
    start_command: tuple[str, ...]

    def health_url(self, host: str = "127.0.0.1", port: int | None = None) -> str:
        return f"http://{host}:{port if port is not None else self.default_port}{self.health_path}"
