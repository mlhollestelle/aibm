import pytest

from aibm.agent import Agent
from aibm.household import Household


def test_household_starts_empty() -> None:
    hh = Household()
    assert hh.size == 0
    assert hh.members == []


def test_add_member() -> None:
    hh = Household()
    agent = Agent(name="Alice")
    hh.add_member(agent)
    assert hh.size == 1
    assert agent in hh.members


def test_remove_member() -> None:
    agent = Agent(name="Alice")
    hh = Household(members=[agent])
    hh.remove_member(agent)
    assert hh.size == 0


def test_remove_non_member_raises() -> None:
    hh = Household()
    agent = Agent(name="Alice")
    with pytest.raises(ValueError):
        hh.remove_member(agent)


def test_household_id_auto_generated() -> None:
    hh = Household()
    assert isinstance(hh.id, str)
    assert len(hh.id) > 0


def test_household_ids_are_unique() -> None:
    assert Household().id != Household().id
