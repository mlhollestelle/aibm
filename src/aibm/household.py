"""Household — a group of agents living together."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from aibm.agent import Agent


@dataclass
class Household:
    """A household containing one or more agents.

    Attributes:
        id: Unique identifier (auto-generated if not supplied).
        members: Agents belonging to this household.
        home_zone: Zone id shared by all household members.  Setting this
            propagates the value to every current member; new members added
            via :meth:`add_member` inherit it automatically.
        num_vehicles: Number of vehicles available to the household.
        income_level: One of ``"low"``, ``"medium"``, or ``"high"``.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    members: list[Agent] = field(default_factory=list)
    home_zone: str | None = None
    num_vehicles: int = 0
    income_level: str = "medium"

    def __post_init__(self) -> None:
        if self.home_zone is not None:
            self._propagate_home_zone()

    def _propagate_home_zone(self) -> None:
        """Copy the household's home_zone to every member."""
        for member in self.members:
            member.home_zone = self.home_zone

    def add_member(self, agent: Agent) -> None:
        """Add an agent to the household.

        If the household has a ``home_zone``, the agent inherits it.
        """
        self.members.append(agent)
        if self.home_zone is not None:
            agent.home_zone = self.home_zone

    def remove_member(self, agent: Agent) -> None:
        """Remove an agent from the household.

        Raises:
            ValueError: If the agent is not a member.
        """
        self.members.remove(agent)

    @property
    def size(self) -> int:
        """Number of members in the household."""
        return len(self.members)

    def __repr__(self) -> str:
        return f"Household(id={self.id!r}, size={self.size})"
