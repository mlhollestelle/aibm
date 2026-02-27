"""Trip — a single journey between two consecutive activities."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Trip:
    """A single journey connecting two consecutive activities.

    Attributes:
        origin: Zone id of the trip's starting point.
        destination: Zone id of the trip's end point.
        mode: Travel mode, e.g. ``"car"``, ``"bike"``, ``"transit"``.
            ``None`` until filled in by ``choose_mode``.
        departure_time: Departure time in minutes from midnight.  ``None``
            until filled in by ``schedule_activities``.
        arrival_time: Arrival time in minutes from midnight.  ``None`` until
            filled in by ``schedule_activities``.
        distance: Trip distance in kilometres.  Optional — may stay ``None``
            when distance data is unavailable.
    """

    origin: str
    destination: str
    mode: str | None = None
    departure_time: float | None = None
    arrival_time: float | None = None
    distance: float | None = None
    escort_agent_id: str | None = None
