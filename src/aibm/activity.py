"""Activity — a single activity in an agent's day."""

from __future__ import annotations

from dataclasses import dataclass

VALID_OUT_OF_HOME_TYPES: frozenset[str] = frozenset(
    {
        "work",
        "school",
        "shopping",
        "leisure",
        "personal_business",
        "escort",
        "eating_out",
    }
)


@dataclass
class Activity:
    """A single activity performed by an agent.

    Attributes:
        type: Activity type, e.g. ``"work"``, ``"school"``, ``"shopping"``,
            ``"leisure"``.
        location: Zone id where the activity takes place.  ``None`` until
            filled in by ``choose_destination`` (work/school are the
            exception — their location comes from the long-term zone choice).
        start_time: Start time in minutes from midnight.  ``None`` until
            filled in by ``schedule_activities``.
        end_time: End time in minutes from midnight.  ``None`` until filled in
            by ``schedule_activities``.
        is_flexible: ``True`` when timing is flexible (the default).
            Set to ``False`` for fixed activities such as work or school.
    """

    type: str
    location: str | None = None
    poi_id: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    is_flexible: bool = True
