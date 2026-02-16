"""Tour — a sequence of trips that starts and ends at the home zone."""

from __future__ import annotations

from dataclasses import dataclass, field

from aibm.trip import Trip


@dataclass
class Tour:
    """An ordered sequence of trips forming one home-based tour.

    In transport modelling a *tour* is a chain of trips that leaves home,
    visits one or more destinations, and returns home.  Think of it as a
    single day-trip in a travel diary: it has a clear start (leave home)
    and a clear end (arrive back home).

    Attributes:
        trips: Ordered list of :class:`Trip` objects in this tour.
        home_zone: Zone id of the agent's home.  Used by :attr:`is_closed`
            to check whether the final trip returns home.
    """

    trips: list[Trip] = field(default_factory=list)
    home_zone: str | None = None

    @property
    def origin(self) -> str | None:
        """Zone id where the tour begins (origin of the first trip)."""
        if not self.trips:
            return None
        return self.trips[0].origin

    @property
    def is_closed(self) -> bool:
        """``True`` when the last trip ends back at :attr:`home_zone`.

        Returns ``False`` when there are no trips or ``home_zone`` is not set.
        """
        if not self.trips or self.home_zone is None:
            return False
        return self.trips[-1].destination == self.home_zone
