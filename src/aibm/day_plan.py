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
        activities: Ordered list of Activity objects for the day.
            Populated by ``schedule_activities``.
        tours: List of Tour objects built from the activities.
            Populated by ``build_tours``.
    """

    activities: list[Activity] = field(default_factory=list)
    tours: list[Tour] = field(default_factory=list)

    @property
    def trips(self) -> list[Trip]:
        """All trips across every tour, flattened into a single ordered list."""
        return [trip for tour in self.tours for trip in tour.trips]

    def validate(self) -> list[str]:
        """Check the day plan for feasibility issues.

        Returns a list of warning strings. An empty list means
        the plan looks valid.
        """
        warnings: list[str] = []

        for act in self.activities:
            if act.start_time is not None and (
                act.start_time < 0 or act.start_time > 1440
            ):
                warnings.append(
                    f"Activity '{act.type}' has invalid start_time {act.start_time}"
                )
            if act.end_time is not None and (act.end_time < 0 or act.end_time > 1440):
                warnings.append(
                    f"Activity '{act.type}' has invalid end_time {act.end_time}"
                )

        # Check for overlapping activities
        scheduled = [
            a
            for a in self.activities
            if a.start_time is not None and a.end_time is not None
        ]
        scheduled.sort(key=lambda a: a.start_time if a.start_time is not None else 0)
        for i in range(len(scheduled) - 1):
            cur = scheduled[i]
            nxt = scheduled[i + 1]
            assert cur.end_time is not None
            assert nxt.start_time is not None
            if cur.end_time > nxt.start_time:
                warnings.append(f"Activities '{cur.type}' and '{nxt.type}' overlap")

        # Check work duration (4–10 hours = 240–600 minutes)
        for act in self.activities:
            if (
                act.type == "work"
                and act.start_time is not None
                and act.end_time is not None
            ):
                duration = act.end_time - act.start_time
                if duration < 240 or duration > 600:
                    warnings.append(
                        f"Work duration {duration:.0f} min is outside 4–10 hour range"
                    )

        return warnings
