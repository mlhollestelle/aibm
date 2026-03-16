import json
from unittest.mock import MagicMock

import pytest

from aibm.activity import Activity, JointActivity
from aibm.agent import Agent
from aibm.day_plan import DayPlan
from aibm.household import Household
from aibm.poi import POI
from aibm.tour import Tour
from aibm.trip import Trip


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
    Household(members=[alice, bob], home_zone="zone_1")
    assert alice.home_zone == "zone_1"
    assert bob.home_zone == "zone_1"


def test_home_zone_propagates_on_add_member() -> None:
    hh = Household(home_zone="zone_2")
    carol = Agent(name="Carol")
    hh.add_member(carol)
    assert carol.home_zone == "zone_2"


def test_no_propagation_when_home_zone_is_none() -> None:
    agent = Agent(name="Dave", home_zone="original")
    Household(members=[agent])
    assert agent.home_zone == "original"


# --- vehicle allocation ---


def _make_tour(origin: str, destination: str) -> Tour:
    """Create a simple round-trip tour."""
    return Tour(
        trips=[
            Trip(origin=origin, destination=destination),
            Trip(origin=destination, destination=origin),
        ],
        home_zone=origin,
    )


def test_allocate_vehicles_zero_vehicles() -> None:
    """All members get False when household has no vehicles."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice],
        home_zone="z1",
        num_vehicles=0,
    )
    tours = {alice.id: [_make_tour("z1", "z2")]}
    alloc, prompt = hh.allocate_vehicles(tours, skims=[])
    assert alloc[alice.id] == [False]
    assert prompt == ""


def test_allocate_vehicles_enough() -> None:
    """All licensed adults get True when enough vehicles."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    bob = Agent(
        name="Bob",
        age=37,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice, bob],
        home_zone="z1",
        num_vehicles=2,
    )
    tours = {
        alice.id: [_make_tour("z1", "z2")],
        bob.id: [_make_tour("z1", "z3")],
    }
    alloc, prompt = hh.allocate_vehicles(tours, skims=[])
    assert alloc[alice.id] == [True]
    assert alloc[bob.id] == [True]
    assert prompt == ""


def test_allocate_vehicles_scarce() -> None:
    """LLM is called when vehicles are scarce."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    bob = Agent(
        name="Bob",
        age=37,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice, bob],
        home_zone="z1",
        num_vehicles=1,
    )
    tours = {
        alice.id: [_make_tour("z1", "z2")],
        bob.id: [_make_tour("z1", "z3")],
    }

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "allocations": [
                {
                    "agent_id": alice.id,
                    "tour_idx": 0,
                    "has_vehicle": True,
                    "reasoning": "Alice commutes far.",
                },
                {
                    "agent_id": bob.id,
                    "tour_idx": 0,
                    "has_vehicle": False,
                    "reasoning": "Bob can bike.",
                },
            ]
        }
    )

    alloc, prompt = hh.allocate_vehicles(
        tours,
        skims=[],
        client=mock_client,
    )
    assert alloc[alice.id] == [True]
    assert alloc[bob.id] == [False]
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    mock_client.generate_json.assert_called_once()


def test_allocate_vehicles_prompt_content() -> None:
    """Prompt contains member names and tour info."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
        persona="Drives to work.",
    )
    bob = Agent(
        name="Bob",
        age=37,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice, bob],
        home_zone="z1",
        num_vehicles=1,
    )
    tours = {
        alice.id: [_make_tour("z1", "z2")],
        bob.id: [_make_tour("z1", "z3")],
    }

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "allocations": [
                {
                    "agent_id": alice.id,
                    "tour_idx": 0,
                    "has_vehicle": True,
                    "reasoning": "ok",
                },
                {
                    "agent_id": bob.id,
                    "tour_idx": 0,
                    "has_vehicle": False,
                    "reasoning": "ok",
                },
            ]
        }
    )

    hh.allocate_vehicles(
        tours,
        skims=[],
        client=mock_client,
    )

    prompt = mock_client.generate_json.call_args[1]["prompt"]
    assert "Alice" in prompt
    assert "Bob" in prompt
    assert "1 vehicle" in prompt


def test_allocate_vehicles_unlicensed_excluded() -> None:
    """Unlicensed members never get vehicle access."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    teen = Agent(
        name="Teen",
        age=16,
        has_license=False,
        employment="student",
    )
    hh = Household(
        members=[alice, teen],
        home_zone="z1",
        num_vehicles=1,
    )
    tours = {
        alice.id: [_make_tour("z1", "z2")],
        teen.id: [_make_tour("z1", "z3")],
    }
    # Only 1 licensed adult with tours → enough vehicles.
    alloc, _ = hh.allocate_vehicles(tours, skims=[])
    assert alloc[alice.id] == [True]
    assert alloc[teen.id] == [False]


# --- escort trips ---


def test_members_needing_escort() -> None:
    """Age filtering returns only children below threshold."""
    child = Agent(name="Kid", age=8, employment="student")
    teen = Agent(name="Teen", age=14, employment="student")
    adult = Agent(name="Dad", age=40, has_license=True)
    hh = Household(members=[child, teen, adult], home_zone="z1")

    need_escort = hh.members_needing_escort(age_threshold=12)
    assert child in need_escort
    assert teen not in need_escort
    assert adult not in need_escort


def test_potential_escorts() -> None:
    """Only licensed adults are potential escorts."""
    dad = Agent(
        name="Dad",
        age=40,
        has_license=True,
        employment="employed",
    )
    mom = Agent(
        name="Mom",
        age=38,
        has_license=False,
        employment="employed",
    )
    teen = Agent(
        name="Teen",
        age=17,
        has_license=True,
        employment="student",
    )
    hh = Household(members=[dad, mom, teen], home_zone="z1")

    escorts = hh.potential_escorts
    assert dad in escorts
    assert mom not in escorts  # no licence
    assert teen not in escorts  # under 18


def test_plan_escort_trips_dropoff() -> None:
    """Parent gains a school stop for drop-off."""
    dad = Agent(
        name="Dad",
        age=40,
        has_license=True,
        employment="employed",
        home_zone="z1",
    )
    kid = Agent(
        name="Kid",
        age=8,
        employment="student",
        home_zone="z1",
    )
    hh = Household(
        members=[dad, kid],
        home_zone="z1",
        num_vehicles=1,
    )

    school_act = Activity(
        type="school",
        location="z_school",
        start_time=480,
        end_time=900,
        is_flexible=False,
    )

    work_act = Activity(
        type="work",
        location="z_work",
        start_time=510,
        end_time=1020,
        is_flexible=False,
    )
    dad_plan = DayPlan(activities=[work_act])
    dad.build_tours(dad_plan)

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "escort_assignments": [
                {
                    "child_id": kid.id,
                    "escort_id": dad.id,
                    "trip_type": "dropoff",
                    "reasoning": "Dad drops off en route.",
                },
            ]
        }
    )

    result, prompt = hh.plan_escort_trips(
        child_activities={kid.id: [school_act]},
        parent_plans={dad.id: dad_plan},
        skims=[],
        client=mock_client,
    )

    updated_plan = result[dad.id]
    escort_acts = [a for a in updated_plan.activities if a.type == "escort"]
    assert len(escort_acts) == 1
    assert escort_acts[0].location == "z_school"
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_plan_escort_trips_pickup() -> None:
    """Parent gains a school stop for pick-up."""
    mom = Agent(
        name="Mom",
        age=38,
        has_license=True,
        employment="employed",
        home_zone="z1",
    )
    kid = Agent(
        name="Kid",
        age=8,
        employment="student",
        home_zone="z1",
    )
    hh = Household(
        members=[mom, kid],
        home_zone="z1",
        num_vehicles=1,
    )

    school_act = Activity(
        type="school",
        location="z_school",
        start_time=480,
        end_time=900,
        is_flexible=False,
    )
    work_act = Activity(
        type="work",
        location="z_work",
        start_time=510,
        end_time=1020,
        is_flexible=False,
    )
    mom_plan = DayPlan(activities=[work_act])
    mom.build_tours(mom_plan)

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "escort_assignments": [
                {
                    "child_id": kid.id,
                    "escort_id": mom.id,
                    "trip_type": "pickup",
                    "reasoning": "Mom picks up after work.",
                },
            ]
        }
    )

    result, _ = hh.plan_escort_trips(
        child_activities={kid.id: [school_act]},
        parent_plans={mom.id: mom_plan},
        skims=[],
        client=mock_client,
    )

    updated_plan = result[mom.id]
    escort_acts = [a for a in updated_plan.activities if a.type == "escort"]
    assert len(escort_acts) == 1
    assert escort_acts[0].location == "z_school"


def test_child_trip_mode() -> None:
    """Child's escort trip should have escort_agent_id set on Trip."""
    # escort_agent_id is a field on Trip, verified here.
    trip = Trip(
        origin="z1",
        destination="z_school",
        mode="car_passenger",
        escort_agent_id="dad-123",
    )
    assert trip.escort_agent_id == "dad-123"
    assert trip.mode == "car_passenger"


# --- joint activities ---


def test_plan_joint_single_person() -> None:
    """Single-person household returns empty, no LLM call."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    hh = Household(members=[alice], home_zone="z1")

    result, prompt = hh.plan_joint_activities(
        member_schedules={alice.id: []},
        pois_by_type={},
        skims=[],
    )
    assert result == []
    assert prompt == ""


def test_plan_joint_activities_result() -> None:
    """Multi-person household gets JointActivity list from LLM."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    bob = Agent(
        name="Bob",
        age=37,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice, bob],
        home_zone="z1",
        num_vehicles=1,
    )

    poi = POI(
        id="shop1",
        name="Grocery Store",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="z_shop",
    )

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "joint_activities": [
                {
                    "activity_type": "shopping",
                    "destination_id": "poi:shop1",
                    "start_time": "18:00",
                    "end_time": "19:00",
                    "participant_ids": [
                        alice.id,
                        bob.id,
                    ],
                    "reasoning": "Family grocery run.",
                },
            ]
        }
    )

    result, prompt = hh.plan_joint_activities(
        member_schedules={
            alice.id: [],
            bob.id: [],
        },
        pois_by_type={"shopping": [poi]},
        skims=[],
        client=mock_client,
    )

    assert len(result) == 1
    assert isinstance(result[0], JointActivity)
    assert result[0].activity.type == "shopping"
    assert result[0].activity.location == "z_shop"
    assert alice.id in result[0].participant_ids
    assert bob.id in result[0].participant_ids
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    mock_client.generate_json.assert_called_once()


def test_joint_injected_as_fixed() -> None:
    """Joint activities should have is_flexible=False."""
    alice = Agent(
        name="Alice",
        age=35,
        has_license=True,
        employment="employed",
    )
    bob = Agent(
        name="Bob",
        age=37,
        has_license=True,
        employment="employed",
    )
    hh = Household(
        members=[alice, bob],
        home_zone="z1",
        num_vehicles=1,
    )

    poi = POI(
        id="shop1",
        name="Grocery Store",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="z_shop",
    )

    mock_client = MagicMock()
    mock_client.generate_json.return_value = json.dumps(
        {
            "joint_activities": [
                {
                    "activity_type": "shopping",
                    "destination_id": "poi:shop1",
                    "start_time": "18:00",
                    "end_time": "19:00",
                    "participant_ids": [
                        alice.id,
                        bob.id,
                    ],
                    "reasoning": "Family grocery run.",
                },
            ]
        }
    )

    result, _ = hh.plan_joint_activities(
        member_schedules={
            alice.id: [],
            bob.id: [],
        },
        pois_by_type={"shopping": [poi]},
        skims=[],
        client=mock_client,
    )

    assert len(result) == 1
    assert result[0].activity.is_flexible is False
    assert result[0].activity.is_joint is True


# --- json.loads error handling (Phase 2a) ---


def _bad_json_client() -> MagicMock:
    """Return a mock LLM client that always responds with invalid JSON."""
    mock = MagicMock()
    mock.generate_json.return_value = "not-valid-json"
    return mock


def test_allocate_vehicles_bad_json_raises_value_error() -> None:
    alice = Agent(name="Alice", age=35, employment="employed", has_license=True)
    bob = Agent(name="Bob", age=33, employment="employed", has_license=True)
    hh = Household(members=[alice, bob], home_zone="z1", num_vehicles=1)

    from aibm.tour import Tour
    from aibm.trip import Trip

    trip = Trip(origin="z1", destination="z2")
    tour = Tour(trips=[trip], home_zone="z1")

    with pytest.raises(ValueError, match="allocate_vehicles"):
        hh.allocate_vehicles(
            member_tours={alice.id: [tour], bob.id: [tour]},
            skims=[],
            client=_bad_json_client(),
        )


def test_plan_escort_trips_bad_json_raises_value_error() -> None:
    parent = Agent(name="Parent", age=40, has_license=True)
    child = Agent(name="Child", age=8)
    hh = Household(members=[parent, child], home_zone="z1")

    child_act = Activity(
        type="school", location="school-zone", start_time=480, end_time=900
    )
    parent_plan = DayPlan(activities=[])

    with pytest.raises(ValueError, match="plan_escort_trips"):
        hh.plan_escort_trips(
            child_activities={child.id: [child_act]},
            parent_plans={parent.id: parent_plan},
            skims=[],
            client=_bad_json_client(),
        )


def test_plan_joint_activities_bad_json_raises_value_error() -> None:
    alice = Agent(name="Alice", age=35)
    bob = Agent(name="Bob", age=33)
    hh = Household(members=[alice, bob], home_zone="z1")

    poi = POI(
        id="shop1",
        name="Shop",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="z2",
    )

    with pytest.raises(ValueError, match="plan_joint_activities"):
        hh.plan_joint_activities(
            member_schedules={alice.id: [], bob.id: []},
            pois_by_type={"shopping": [poi]},
            skims=[],
            client=_bad_json_client(),
        )
