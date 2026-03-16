"""Skim — travel-time matrix wrapper with O-D lookups."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

UNREACHABLE_SENTINEL = 999.0


@dataclass
class Skim:
    """A travel-time skim matrix for one transport mode.

    Wraps a NumPy array and provides convenient origin-destination
    lookups by zone id string.

    Attributes:
        mode: Transport mode name (e.g. ``"car"``, ``"bike"``).
        matrix: 2-D NumPy array of shape ``(n_zones, n_zones)``
            holding travel times in minutes.
        zone_ids: Ordered list of zone id strings matching the
            matrix rows/columns.
    """

    mode: str
    matrix: object  # np.ndarray — typed as object to avoid top-level import
    zone_ids: list[str]
    _index: dict[str, int] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._index = {zid: i for i, zid in enumerate(self.zone_ids)}

    def travel_time(self, origin: str, destination: str) -> float:
        """Look up the travel time between two zones.

        Args:
            origin: Origin zone id.
            destination: Destination zone id.

        Returns:
            Travel time in minutes, or ``math.inf`` if the
            zone is unknown or the pair is unreachable.
        """
        oi = self._index.get(origin)
        di = self._index.get(destination)
        if oi is None or di is None:
            return math.inf
        val = float(self.matrix[oi, di])  # type: ignore[index]
        if val >= UNREACHABLE_SENTINEL:
            return math.inf
        return val

    def travel_times_from(
        self,
        origin: str,
        destinations: list[str],
    ) -> dict[str, float]:
        """Batch lookup from one origin to many destinations.

        Args:
            origin: Origin zone id.
            destinations: List of destination zone ids.

        Returns:
            Dict mapping reachable destination ids to travel
            times in minutes. Unreachable or unknown zones
            are omitted.
        """
        result: dict[str, float] = {}
        for dest in destinations:
            tt = self.travel_time(origin, dest)
            if tt < math.inf:
                result[dest] = tt
        return result


def load_skim(path: str | Path, mode: str) -> Skim:
    """Read an OMX skim matrix produced by ``build_skim.py``.

    The OMX file is expected to contain a matrix named
    ``travel_time_min`` and a lookup array at
    ``root.lookup.zone_id``.

    Args:
        path: Path to the ``.omx`` file.
        mode: Transport mode label (stored on the Skim).

    Returns:
        A :class:`Skim` instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    import numpy as np
    import openmatrix as omx  # type: ignore[import-not-found]

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Skim file not found: {path}")

    with omx.open_file(str(path), "r") as f:
        matrix: np.ndarray = np.array(f["travel_time_min"])
        raw_ids = f.root.lookup.zone_id[:]
        zone_ids = [b.decode() for b in raw_ids]

    return Skim(mode=mode, matrix=matrix, zone_ids=zone_ids)
