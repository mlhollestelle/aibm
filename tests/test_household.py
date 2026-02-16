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


# --- demographic attributes ---


def test_household_default_demographics() -> None:
    hh = Household()
    assert hh.home_zone is None
    assert hh.num_vehicles == 0
    assert hh.income_level == "medium"


def test_household_custom_demographics() -> None:
    hh = Household(home_zone="zone_1", num_vehicles=2, income_level="high")
    assert hh.home_zone == "zone_1"
    assert hh.num_vehicles == 2
    assert hh.income_level == "high"


# --- home_zone propagation ---


def test_home_zone_propagates_to_initial_members() -> None:
    alice = Agent(name="Alice")
    bob = Agent(name="Bob")
    hh = Household(members=[alice, bob], home_zone="zone_1")
    assert alice.home_zone == "zone_1"
    assert bob.home_zone == "zone_1"


def test_home_zone_propagates_on_add_member() -> None:
    hh = Household(home_zone="zone_2")
    carol = Agent(name="Carol")
    hh.add_member(carol)
    assert carol.home_zone == "zone_2"


def test_no_propagation_when_home_zone_is_none() -> None:
    agent = Agent(name="Dave", home_zone="original")
    hh = Household(members=[agent])
    assert agent.home_zone == "original"
