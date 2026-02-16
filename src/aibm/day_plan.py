"""DayPlan — the full scheduled day for one agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from aibm.activity import Activity
from aibm.tour import Tour
from aibm.trip import Trip


@dataclass
class DayPlan:
    """The complete day for a single agent: activities and the tours they form.

    Attributes:
        activities: Ordered list of :class:`Activity` objects for the day.
            Populated by ``schedule_activities``.
        tours: List of :class:`Tour` objects built from the activities.
            Populated by ``build_tours``.
    """

    activities: list[Activity] = field(default_factory=list)
    tours: list[Tour] = field(default_factory=list)

    @property
    def trips(self) -> list[Trip]:
        """All trips across every tour, flattened into a single ordered list."""
        return [trip for tour in self.tours for trip in tour.trips]
