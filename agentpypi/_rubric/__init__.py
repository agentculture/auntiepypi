"""Rubric for ``agentpypi packages overview`` — per-dimension plugin point.

Each module under this package exposes one ``DIMENSION``. The tuple
:data:`DIMENSIONS` is the canonical iteration order; agents see results
in this order.
"""

from __future__ import annotations

from agentpypi._rubric._dimension import Dimension, DimensionResult, Score
from agentpypi._rubric.cadence import DIMENSION as cadence
from agentpypi._rubric.distribution import DIMENSION as distribution
from agentpypi._rubric.downloads import DIMENSION as downloads
from agentpypi._rubric.lifecycle import DIMENSION as lifecycle
from agentpypi._rubric.metadata import DIMENSION as metadata
from agentpypi._rubric.recency import DIMENSION as recency
from agentpypi._rubric.versioning import DIMENSION as versioning

DIMENSIONS: tuple[Dimension, ...] = (
    recency,
    cadence,
    downloads,
    lifecycle,
    distribution,
    metadata,
    versioning,
)

__all__ = ["DIMENSIONS", "Dimension", "DimensionResult", "Score"]
