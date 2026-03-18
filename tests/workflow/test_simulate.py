"""Tests for _simulate_agent and _simulate_household in simulate.py."""

import json
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("pandas")

from simulate import _simulate_agent, _simulate_household

from aibm import Agent, Household, Skim, Zone


def _make_skim(zone_ids: list[str], tt: float = 10.0) -> Skim:
    """Create a Skim with uniform travel times between all zone pairs."""
    n = len(zone_ids)
    matrix = np.full((n, n), tt)
    np.fill_diagonal(matrix, 0.0)
    return Skim(mode="car", matrix=matrix, zone_ids=zone_ids)


def _mock_client(*responses: str) -> MagicMock:
    """Return a mock LLM client whose generate_json cycles through *responses*."""
    client = MagicMock()
    client.generate_json.side_effect = list(responses)
    return client


HOME = "E1500N3850"
WORK = "E1501N3851"


def _make_employed_setup() -> tuple:
    """Return (agent, hh, zones, skims, client) for an employed agent."""
    hh = Household(id="42", home_zone=HOME, num_vehicles=1, income_level="medium")
    agent = Agent(name="Jan", age=35, employment="employed", model="gpt-4o-mini")
    hh.add_member(agent)

    zones = [
        Zone(id=HOME, name=HOME, x=150050.0, y=385050.0),
        Zone(id=WORK, name=WORK, x=150150.0, y=385150.0),
    ]
    skims = [_make_skim([HOME, WORK])]

    # LLM call order for an employed agent with one work activity:
    # 1. generate_persona
    # 2. choose_work_zone
    # 3. generate_activities
    # 4. schedule_activities
    # 5. choose_tour_mode
    client = _mock_client(
        json.dumps({"persona": "Commutes daily by car."}),
        json.dumps({"zone_id": WORK, "reasoning": "Closest workplace."}),
        json.dumps({"activities": [{"type": "work", "is_flexible": False}]}),
        json.dumps(
            {"schedule": [{"type": "work", "start_time": "08:00", "end_time": "16:00"}]}
        ),
        json.dumps({"reasoning": "I have a car.", "choice": "car"}),
    )
    return agent, hh, zones, skims, client


def test_simulate_agent_produces_trips():
    agent, hh, zones, skims, client = _make_employed_setup()

    trip_rows, day_plan_row, _ = _simulate_agent(
        agent, hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert len(trip_rows) == 2  # home→work and work→home
    assert trip_rows[0]["origin"] == HOME
    assert trip_rows[0]["destination"] == WORK
    assert trip_rows[1]["origin"] == WORK
    assert trip_rows[1]["destination"] == HOME


def test_simulate_agent_day_plan_row():
    agent, hh, zones, skims, client = _make_employed_setup()

    _, day_plan_row, _ = _simulate_agent(
        agent, hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert day_plan_row["agent_id"] == agent.id
    assert day_plan_row["household_id"] == "42"
    assert day_plan_row["persona"] == "Commutes daily by car."
    assert day_plan_row["n_activities"] == 1
    assert day_plan_row["n_tours"] == 1


def test_simulate_agent_mode_assigned():
    agent, hh, zones, skims, client = _make_employed_setup()

    trip_rows, _, _ = _simulate_agent(
        agent, hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert all(row["mode"] == "car" for row in trip_rows)


def test_simulate_agent_no_vehicles_excludes_car():
    """Household with 0 vehicles should not be offered car mode."""
    hh = Household(id="7", home_zone=HOME, num_vehicles=0, income_level="low")
    agent = Agent(name="Piet", age=22, employment="employed", model="gpt-4o-mini")
    hh.add_member(agent)

    zones = [
        Zone(id=HOME, name=HOME, x=150050.0, y=385050.0),
        Zone(id=WORK, name=WORK, x=150150.0, y=385150.0),
    ]
    bike_skim = Skim(
        mode="bike",
        matrix=np.array([[0.0, 10.0], [10.0, 0.0]]),
        zone_ids=[HOME, WORK],
    )

    # Choose mode will only see "bike"; mock returns bike.
    client = _mock_client(
        json.dumps({"persona": "Cyclist."}),
        json.dumps({"zone_id": WORK, "reasoning": "Near."}),
        json.dumps({"activities": [{"type": "work", "is_flexible": False}]}),
        json.dumps(
            {"schedule": [{"type": "work", "start_time": "08:00", "end_time": "16:00"}]}
        ),
        json.dumps({"reasoning": "Only bike available.", "choice": "bike"}),
    )

    trip_rows, _, _ = _simulate_agent(
        agent, hh, zones, [], [bike_skim], client, n_zone_candidates=5
    )

    assert all(row["mode"] == "bike" for row in trip_rows)


def test_simulate_agent_error_propagates():
    """_simulate_agent raises when the LLM client fails."""
    hh = Household(id="99", home_zone=HOME, num_vehicles=1, income_level="medium")
    agent = Agent(name="Fails", age=30, employment="employed", model="gpt-4o-mini")
    hh.add_member(agent)

    zones = [Zone(id=HOME, name=HOME, x=150050.0, y=385050.0)]
    skims = [_make_skim([HOME])]

    client = MagicMock()
    client.generate_json.side_effect = RuntimeError("API timeout")

    with pytest.raises(RuntimeError, match="API timeout"):
        _simulate_agent(agent, hh, zones, [], skims, client, n_zone_candidates=5)


# --- _simulate_household integration tests ---

SCHOOL = "E1502N3852"


def test_simulate_household_full_flow():
    """Full household simulation with employed adult + student child."""
    hh = Household(id="hh1", home_zone=HOME, num_vehicles=1, income_level="medium")
    adult = Agent(name="Parent", age=35, employment="employed", model="gpt-4o-mini")
    child = Agent(name="Child", age=10, employment="student", model="gpt-4o-mini")
    hh.add_member(adult)
    hh.add_member(child)

    zones = [
        Zone(id=HOME, name=HOME, x=150050.0, y=385050.0),
        Zone(id=WORK, name=WORK, x=150150.0, y=385150.0),
        Zone(id=SCHOOL, name=SCHOOL, x=150250.0, y=385250.0),
    ]
    skims = [_make_skim([HOME, WORK, SCHOOL])]

    # LLM call sequence for a 2-member household:
    # Adult: persona, choose_work_zone, activities, schedule
    # Child: persona, choose_school_zone, activities, schedule
    # Joint activities (2 members), escort, vehicle_allocation
    # Adult mode_choice, Child mode_choice
    client = _mock_client(
        # Adult persona
        json.dumps({"persona": "Drives to work daily."}),
        # Adult choose_work_zone
        json.dumps({"zone_id": WORK, "reasoning": "Close."}),
        # Adult activities
        json.dumps({"activities": [{"type": "work", "is_flexible": False}]}),
        # Adult schedule
        json.dumps(
            {
                "schedule": [
                    {
                        "type": "work",
                        "start_time": "08:00",
                        "end_time": "16:00",
                    }
                ]
            }
        ),
        # Child persona
        json.dumps({"persona": "Goes to school."}),
        # Child choose_school_zone
        json.dumps({"zone_id": SCHOOL, "reasoning": "Nearby school."}),
        # Child activities
        json.dumps({"activities": [{"type": "school", "is_flexible": False}]}),
        # Child schedule
        json.dumps(
            {
                "schedule": [
                    {
                        "type": "school",
                        "start_time": "08:30",
                        "end_time": "15:00",
                    }
                ]
            }
        ),
        # Joint activities (multi-person household)
        json.dumps({"joint_activities": []}),
        # Escort trips
        json.dumps(
            {
                "escort_assignments": [
                    {
                        "child_id": child.id,
                        "escort_id": adult.id,
                        "trip_type": "dropoff",
                        "reasoning": "Parent drops off.",
                    }
                ]
            }
        ),
        # Vehicle allocation
        json.dumps(
            {
                "allocations": [
                    {
                        "agent_id": adult.id,
                        "tour_idx": 0,
                        "has_vehicle": True,
                        "reasoning": "Commuter.",
                    },
                    {
                        "agent_id": child.id,
                        "tour_idx": 0,
                        "has_vehicle": False,
                        "reasoning": "Child.",
                    },
                ]
            }
        ),
        # Adult mode choice
        json.dumps({"reasoning": "Have car.", "choice": "car"}),
        # Child mode choice
        json.dumps({"reasoning": "Walk.", "choice": "car"}),
    )

    trip_rows, day_plan_rows, activity_rows = _simulate_household(
        hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert len(trip_rows) > 0
    assert len(day_plan_rows) == 2
    assert len(activity_rows) > 0


def test_simulate_agent_retired():
    """Retired agent: no work/school zone choice, still produces trips."""
    hh = Household(id="hh-ret", home_zone=HOME, num_vehicles=0, income_level="low")
    agent = Agent(
        name="Oma",
        age=70,
        employment="retired",
        model="gpt-4o-mini",
    )
    hh.add_member(agent)

    zones = [
        Zone(id=HOME, name=HOME, x=150050.0, y=385050.0),
        Zone(id=WORK, name=WORK, x=150150.0, y=385150.0),
    ]
    skims = [_make_skim([HOME, WORK])]

    # Retired: persona → activities (shopping) → schedule → mode
    client = _mock_client(
        json.dumps({"persona": "Retired, shops daily."}),
        json.dumps({"activities": [{"type": "shopping", "is_flexible": True}]}),
        json.dumps(
            {
                "schedule": [
                    {
                        "type": "shopping",
                        "start_time": "10:00",
                        "end_time": "11:00",
                    }
                ]
            }
        ),
        # no mode options since no car and no skim modes match —
        # but we provide a response in case it's called
        json.dumps({"reasoning": "Walk.", "choice": "car"}),
    )

    trip_rows, day_plan_row, _ = _simulate_agent(
        agent, hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert day_plan_row["work_zone"] is None
    assert day_plan_row["school_zone"] is None


def test_simulate_agent_student():
    """Student agent: school zone chosen (not work zone)."""
    hh = Household(id="hh-stu", home_zone=HOME, num_vehicles=0, income_level="low")
    agent = Agent(
        name="Student",
        age=20,
        employment="student",
        model="gpt-4o-mini",
    )
    hh.add_member(agent)

    zones = [
        Zone(id=HOME, name=HOME, x=150050.0, y=385050.0),
        Zone(id=SCHOOL, name=SCHOOL, x=150250.0, y=385250.0),
    ]
    skims = [_make_skim([HOME, SCHOOL])]

    # Student: persona → choose_school_zone → activities → schedule → mode
    client = _mock_client(
        json.dumps({"persona": "Full-time student."}),
        json.dumps({"zone_id": SCHOOL, "reasoning": "Nearby."}),
        json.dumps({"activities": [{"type": "school", "is_flexible": False}]}),
        json.dumps(
            {
                "schedule": [
                    {
                        "type": "school",
                        "start_time": "09:00",
                        "end_time": "15:00",
                    }
                ]
            }
        ),
        json.dumps({"reasoning": "Bike.", "choice": "car"}),
    )

    trip_rows, day_plan_row, _ = _simulate_agent(
        agent, hh, zones, [], skims, client, n_zone_candidates=5
    )

    assert day_plan_row["school_zone"] == SCHOOL
    assert day_plan_row["work_zone"] is None
