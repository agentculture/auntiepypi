"""devpi probe — `devpi-server` on port 3141, health endpoint `/+api`."""

from __future__ import annotations

from agentpypi._probes._probe import Probe

PROBE = Probe(
    name="devpi",
    default_port=3141,
    health_path="/+api",
    start_command=("devpi-server", "--start"),
)
