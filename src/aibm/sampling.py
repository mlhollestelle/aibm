"""Destination sampling utilities."""

from __future__ import annotations

import random

from aibm.poi import POI
from aibm.zone import Zone


def sample_destinations[T: (Zone, POI)](
    candidates: list[T],
    n: int = 10,
    rng: random.Random | None = None,
) -> list[T]:
    """Sample up to *n* candidates uniformly at random.

    If *candidates* has *n* or fewer items the full list is
    returned unchanged (no shuffling).

    Args:
        candidates: Zones or POIs to sample from.
        n: Maximum number of candidates to return.
        rng: Optional seeded :class:`random.Random` for
            reproducibility.

    Returns:
        A list of at most *n* candidates.
    """
    if len(candidates) <= n:
        return candidates
    if rng is None:
        rng = random.Random()
    return rng.sample(candidates, n)
