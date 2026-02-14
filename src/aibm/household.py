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
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    members: list[Agent] = field(default_factory=list)

    def add_member(self, agent: Agent) -> None:
        """Add an agent to the household."""
        self.members.append(agent)

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
