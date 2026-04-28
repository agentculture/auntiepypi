"""Entry point for ``python -m agentpypi``."""

from __future__ import annotations

import sys

from agentpypi.cli import main

if __name__ == "__main__":
    sys.exit(main())
