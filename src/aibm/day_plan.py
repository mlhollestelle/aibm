"""DayPlan — the full scheduled day for one agent."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from aibm.activity import Activity
from aibm.tour import Tour
from aibm.trip import Trip

if TYPE_CHECKING:
    from aibm.skim import Skim

DEFAULT_DAY_START: float = 360.0  # 06:00
DEFAULT_DAY_END: float = 1380.0  # 23:00
WORK_DURATION_MIN: float = 240.0  # 4 hours
WORK_DURATION_MAX: float = 600.0  # 10 hours
SCHOOL_DURATION_MIN: float = 240.0  # 4 hours
SCHOOL_DURATION_MAX: float = 480.0  # 8 hours
EARLIEST_ACTIVITY: float = 240.0  # 04:00


@dataclass
class TimeWindow:
    """A contiguous free-time gap in an agent's day.

    Attributes:
        start: Window open (minutes from midnight). Already accounts for
            minimum travel time from the preceding location.
        end: Window close (minutes from midnight). Already accounts for
            minimum travel time to the following location.
        preceding_location: Zone id of where the agent is at ``start``
            (home zone before the first mandatory activity, or the
            previous mandatory activity's location).
        following_location: Zone id where the agent must be at ``end``
            (home zone after the last mandatory activity, or the next
            mandatory activity's location).
    """

    start: float
    end: float
    preceding_location: str | None
    following_location: str | None

    @property
    def duration(self) -> float:
        """Available duration in minutes."""
        return self.end - self.start


def _min_travel(
    skims: list[Skim], origin: str | None, destination: str | None
) -> float:
    """Return the minimum travel time across all skims for an OD pair.

    Returns 0.0 if either zone is None or no skim can route the pair.
    """
    if origin is None or destination is None:
        return 0.0
    best = math.inf
    for sk in skims:
        tt = sk.travel_time(origin, destination)
        if tt < best:
            best = tt
    return best if best < math.inf else 0.0


def compute_time_windows(
    mandatory_plan: DayPlan,
    skims: list[Skim],
    home_zone: str | None = None,
    day_start: float = DEFAULT_DAY_START,
    day_end: float = DEFAULT_DAY_END,
) -> list[TimeWindow]:
    """Compute free time windows in an agent's day around mandatory activities.

    After mandatory scheduling, deterministically identifies contiguous gaps
    where discretionary activities can be placed. Travel time buffers are
    subtracted so that windows already account for the minimum time needed
    to reach/leave a mandatory location.

    Args:
        mandatory_plan: DayPlan containing already-scheduled mandatory
            activities (with start_time and end_time set).
        skims: List of Skim objects used to estimate minimum travel times.
        home_zone: Agent's home zone id (used as the bounding location
            before the first and after the last activity).
        day_start: Earliest possible activity start in minutes from midnight
            (default 06:00 = 360).
        day_end: Latest possible activity end in minutes from midnight
            (default 23:00 = 1380).

    Returns:
        List of TimeWindow objects representing free gaps. Empty if no
        gaps remain after mandatory scheduling.
    """
    scheduled = [
        a
        for a in mandatory_plan.activities
        if a.start_time is not None and a.end_time is not None
    ]
    scheduled.sort(key=lambda a: cast(float, a.start_time))

    if not scheduled:
        return [
            TimeWindow(
                start=day_start,
                end=day_end,
                preceding_location=home_zone,
                following_location=home_zone,
            )
        ]

    windows: list[TimeWindow] = []

    # Window before the first mandatory activity
    first = scheduled[0]
    travel_in = _min_travel(skims, home_zone, first.location)
    win_end = (first.start_time or 0.0) - travel_in
    if win_end > day_start:
        windows.append(
            TimeWindow(
                start=day_start,
                end=win_end,
                preceding_location=home_zone,
                following_location=first.location,
            )
        )

    # Windows between consecutive mandatory activities
    for prev_act, next_act in zip(scheduled, scheduled[1:]):
        prev_end = prev_act.end_time or 0.0
        next_start = next_act.start_time or 0.0
        travel_between = _min_travel(skims, prev_act.location, next_act.location)
        win_start = prev_end
        win_end = next_start - travel_between
        if win_end > win_start:
            windows.append(
                TimeWindow(
                    start=win_start,
                    end=win_end,
                    preceding_location=prev_act.location,
                    following_location=next_act.location,
                )
            )

    # Window after the last mandatory activity
    last = scheduled[-1]
    travel_out = _min_travel(skims, last.location, home_zone)
    win_start = (last.end_time or 0.0) + travel_out
    if win_start < day_end:
        windows.append(
            TimeWindow(
                start=win_start,
                end=day_end,
                preceding_location=last.location,
                following_location=home_zone,
            )
        )

    return windows


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

        # Check start before end
        for act in self.activities:
            if (
                act.start_time is not None
                and act.end_time is not None
                and act.start_time > act.end_time
            ):
                warnings.append(
                    f"Activity '{act.type}' ends before it starts "
                    f"({act.start_time:.0f} > {act.end_time:.0f})"
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
            if cur.end_time is None:
                raise ValueError(
                    f"Activity '{cur.type}' has no end_time; cannot check overlap"
                )
            if nxt.start_time is None:
                raise ValueError(
                    f"Activity '{nxt.type}' has no start_time; cannot check overlap"
                )
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
                if duration < WORK_DURATION_MIN or duration > WORK_DURATION_MAX:
                    warnings.append(
                        f"Work duration {duration:.0f} min is outside 4–10 hour range"
                    )

        # Check school duration (4–8 hours)
        for act in self.activities:
            if (
                act.type == "school"
                and act.start_time is not None
                and act.end_time is not None
            ):
                duration = act.end_time - act.start_time
                if duration < SCHOOL_DURATION_MIN or duration > SCHOOL_DURATION_MAX:
                    warnings.append(
                        f"School duration {duration:.0f} min is outside 4–8 hour range"
                    )

        # Check first/last activity time bounds
        if scheduled:
            first_start = scheduled[0].start_time
            last_end = scheduled[-1].end_time
            if first_start is not None and first_start < EARLIEST_ACTIVITY:
                warnings.append(
                    f"First activity starts at {first_start:.0f} min (before 04:00)"
                )
            if last_end is not None and last_end > 1440:
                warnings.append(
                    f"Last activity ends at {last_end:.0f} min (after midnight)"
                )

        return warnings

    def inject_joint(self, activity: Activity) -> None:
        """Replace any individual flexible activity of the same type with a joint one.

        Removes all activities where ``is_flexible=True`` and
        ``type == activity.type``, then appends *activity* and re-sorts by
        start time. Call this instead of a plain ``append`` when injecting a
        joint household activity so that the individual discretionary version
        is superseded rather than duplicated.
        """
        self.activities = [
            a
            for a in self.activities
            if not (a.is_flexible and a.type == activity.type)
        ]
        self.activities.append(activity)
        self.activities.sort(
            key=lambda a: a.start_time if a.start_time is not None else 0
        )
