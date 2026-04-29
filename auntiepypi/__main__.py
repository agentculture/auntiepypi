"""Entry point for ``python -m auntiepypi``."""

from __future__ import annotations

import sys

from auntiepypi.cli import main

if __name__ == "__main__":
    sys.exit(main())
