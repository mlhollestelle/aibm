"""Agent — the basic unit of the simulation."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field


@dataclass
class ModeOption:
    """One row of mode-choice input data.

    Think of a list[ModeOption] as an R data.frame with columns
    ``mode`` and ``travel_time``.

    Attributes:
        mode: Name of the travel mode (e.g. "car", "bike", "transit").
        travel_time: Travel time in minutes for this mode.
    """

    mode: str
    travel_time: float


@dataclass
class Agent:
    """A single agent in the simulation.

    Attributes:
        id: Unique identifier (auto-generated if not supplied).
        name: Human-readable label.
    """

    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __repr__(self) -> str:
        return f"Agent(id={self.id!r}, name={self.name!r})"

    def choose_mode(self, options: list[ModeOption]) -> ModeOption:
        """Pick a travel mode at random from the available options.

        Args:
            options: Available modes with their travel times.

        Returns:
            The chosen ModeOption.

        Raises:
            ValueError: If options is empty.
        """
        if not options:
            raise ValueError("options must contain at least one ModeOption")
        return random.choice(options)
