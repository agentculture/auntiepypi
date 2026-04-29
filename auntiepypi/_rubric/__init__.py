"""Rubric for ``auntiepypi packages overview`` — per-dimension plugin point.

Each module under this package exposes one ``DIMENSION``. The tuple
:data:`DIMENSIONS` is the canonical iteration order; agents see results
in this order.
"""

from __future__ import annotations

from auntiepypi._rubric import (
    cadence,
    distribution,
    downloads,
    lifecycle,
    metadata,
    recency,
    versioning,
)
from auntiepypi._rubric._dimension import Dimension, DimensionResult, Score

DIMENSIONS: tuple[Dimension, ...] = (
    recency.DIMENSION,
    cadence.DIMENSION,
    downloads.DIMENSION,
    lifecycle.DIMENSION,
    distribution.DIMENSION,
    metadata.DIMENSION,
    versioning.DIMENSION,
)

__all__ = ["DIMENSIONS", "Dimension", "DimensionResult", "Score"]
