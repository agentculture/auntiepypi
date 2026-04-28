"""PyPI server probes — one flavor per submodule.

Each flavor exposes a ``PROBE`` (a :class:`Probe` instance). Add new
flavors by importing them here and extending :data:`PROBES`.
"""

from __future__ import annotations

from agentpypi._probes._probe import Probe
from agentpypi._probes._runtime import ProbeResult, probe_status
from agentpypi._probes.devpi import PROBE as devpi
from agentpypi._probes.pypiserver import PROBE as pypiserver

PROBES: tuple[Probe, ...] = (devpi, pypiserver)

__all__ = ["PROBES", "Probe", "ProbeResult", "devpi", "probe_status", "pypiserver"]
