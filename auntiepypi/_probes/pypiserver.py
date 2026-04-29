"""pypiserver probe — `pypi-server` on port 8080, health endpoint `/`.

`pypiserver` doesn't ship a JSON health endpoint; the simple-index root
returns HTML 200 when the server is up.
"""

from __future__ import annotations

from auntiepypi._probes._probe import Probe

PROBE = Probe(
    name="pypiserver",
    default_port=8080,
    health_path="/",
    start_command=("pypi-server", "run"),
)
