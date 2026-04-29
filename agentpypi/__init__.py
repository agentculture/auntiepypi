"""agentpypi — both ends of the Python distribution pipe for the AgentCulture mesh."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("agentpypi")
except PackageNotFoundError:  # pragma: no cover - only hit in source checkout w/o install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
