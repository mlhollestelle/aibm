import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from aibm.activity import VALID_OUT_OF_HOME_TYPES, Activity
from aibm.agent import Agent, ModeChoice, ModeOption, _fmt_mins, _parse_hhmm
from aibm.day_plan import DayPlan, TimeWindow
from aibm.household import Household
from aibm.poi import POI
from aibm.skim import Skim
from aibm.tour import Tour
from aibm.trip import Trip
from aibm.zone import Zone


def test_parse_hhmm() -> None:
    assert _parse_hhmm("08:00") == 480.0
    assert _parse_hhmm("17:30") == 1050.0
    assert _parse_hhmm("00:00") == 0.0


def test_fmt_mins() -> None:
    assert _fmt_mins(480.0) == "08:00"
    assert _fmt_mins(1050.0) == "17:30"
    assert _fmt_mins(0.0) == "00:00"


def test_agent_has_name() -> None:
    agent = Agent(name="Alice")
    assert agent.name == "Alice"


def test_agent_id_auto_generated() -> None:
    agent = Agent(name="Alice")
    assert isinstance(agent.id, str)
    assert len(agent.id) > 0


def test_agent_ids_are_unique() -> None:
    a, b = Agent(name="Alice"), Agent(name="Bob")
    assert a.id != b.id


def test_agent_custom_id() -> None:
    agent = Agent(name="Alice", id="custom-id")
    assert agent.id == "custom-id"


def test_agent_default_model() -> None:
    agent = Agent(name="Alice")
    assert agent.model == "gemini-2.5-flash-lite"


def test_agent_custom_model() -> None:
    agent = Agent(name="Alice", model="gemini-1.0-flash-8b")
    assert agent.model == "gemini-1.0-flash-8b"


# --- demographic attributes ---


def test_agent_default_demographics() -> None:
    agent = Agent(name="Alice")
    assert agent.age == 0
    assert agent.employment == "unemployed"
    assert agent.has_license is False
    assert agent.home_zone is None
    assert agent.work_zone is None
    assert agent.school_zone is None
    assert agent.persona is None


def test_agent_custom_demographics() -> None:
    agent = Agent(
        name="Bob",
        age=35,
        employment="employed",
        has_license=True,
        home_zone="zone_1",
        work_zone="zone_2",
        school_zone=None,
        persona="Prefers cycling to work on sunny days.",
    )
    assert agent.age == 35
    assert agent.employment == "employed"
    assert agent.has_license is True
    assert agent.home_zone == "zone_1"
    assert agent.work_zone == "zone_2"
    assert agent.school_zone is None
    assert agent.persona == "Prefers cycling to work on sunny days."


def test_agent_student_demographics() -> None:
    agent = Agent(name="Carol", age=16, employment="student", school_zone="zone_3")
    assert agent.employment == "student"
    assert agent.school_zone == "zone_3"
    assert agent.work_zone is None


# --- generate persona ---


def _mock_persona_client(persona: str) -> MagicMock:
    """Build a fake LLMClient that returns a fixed persona JSON."""
    mock = MagicMock()
    mock.generate_json.return_value = f'{{"persona": "{persona}"}}'
    return mock


def test_generate_persona_returns_string() -> None:
    agent = Agent(name="Alice", age=30, employment="employed")
    mock = _mock_persona_client("Drives to work every day.")
    persona, prompt = agent.generate_persona(client=mock)
    assert isinstance(persona, str)
    assert persona == "Drives to work every day."
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_generate_persona_stores_on_agent() -> None:
    agent = Agent(name="Bob", age=25, employment="student")
    assert agent.persona is None
    mock = _mock_persona_client("Takes the bus to campus.")
    agent.generate_persona(client=mock)
    assert agent.persona == "Takes the bus to campus."


def test_generate_persona_prompt_includes_demographics() -> None:
    agent = Agent(name="Carol", age=45, employment="employed", has_license=True)
    mock = _mock_persona_client("Prefers driving.")
    agent.generate_persona(client=mock)

    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Carol" in prompt
    assert "Age: 45" in prompt
    assert "Employment: employed" in prompt
    assert "Has driving licence: yes" in prompt


def test_generate_persona_prompt_includes_household() -> None:
    agent = Agent(name="Dave", age=40, employment="employed", has_license=True)
    hh = Household(
        members=[agent],
        home_zone="zone_1",
        num_vehicles=1,
        income_level="medium",
    )
    mock = _mock_persona_client("Commutes by car.")
    agent.generate_persona(client=mock, household=hh)

    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Household vehicles: 1" in prompt
    assert "Household income: medium" in prompt


def test_generate_persona_raises_on_empty_response() -> None:
    agent = Agent(name="Eve")
    mock = MagicMock()
    mock.generate_json.side_effect = ValueError("LLM returned an empty response")
    with pytest.raises(ValueError, match="empty response"):
        agent.generate_persona(client=mock)


def test_generate_persona_skips_when_already_set() -> None:
    agent = Agent(name="Alice", persona="Existing persona.")
    mock = MagicMock()
    persona, prompt = agent.generate_persona(client=mock)
    assert persona == "Existing persona."
    assert prompt == ""
    mock.generate_json.assert_not_called()


def test_generate_persona_overwrites_when_requested() -> None:
    agent = Agent(name="Alice", persona="Old persona.")
    mock = _mock_persona_client("New persona.")
    persona, prompt = agent.generate_persona(client=mock, overwrite=True)
    assert persona == "New persona."
    assert agent.persona == "New persona."
    assert len(prompt) > 0
    mock.generate_json.assert_called_once()


# --- mode choice ---

OPTIONS = [
    ModeOption(mode="car", travel_time=20.0),
    ModeOption(mode="bike", travel_time=35.0),
    ModeOption(mode="transit", travel_time=25.0),
]


def _mock_client(choice: str, reasoning: str) -> MagicMock:
    """Build a fake LLMClient that returns a fixed JSON."""
    mock = MagicMock()
    mock.generate_json.return_value = (
        f'{{"reasoning": "{reasoning}", "choice": "{choice}"}}'
    )
    return mock


def test_choose_mode_returns_a_mode_choice() -> None:
    agent = Agent(name="Alice")
    mc, prompt = agent.choose_mode(
        OPTIONS, client=_mock_client("car", "Car is fastest.")
    )
    assert isinstance(mc, ModeChoice)
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_choose_mode_option_is_one_of_the_options() -> None:
    agent = Agent(name="Alice")
    mc, _ = agent.choose_mode(OPTIONS, client=_mock_client("bike", "I like cycling."))
    assert mc.option in OPTIONS


def test_choose_mode_returns_correct_option() -> None:
    agent = Agent(name="Alice")
    mc, _ = agent.choose_mode(
        OPTIONS, client=_mock_client("transit", "Bus is relaxing.")
    )
    assert mc.option.mode == "transit"


def test_choose_mode_includes_reasoning() -> None:
    agent = Agent(name="Alice")
    mc, _ = agent.choose_mode(OPTIONS, client=_mock_client("car", "Car is fastest."))
    assert mc.reasoning == "Car is fastest."


def test_choose_mode_raises_on_empty_llm_response() -> None:
    agent = Agent(name="Alice")
    mock = MagicMock()
    mock.generate_json.side_effect = ValueError("LLM returned an empty response")
    with pytest.raises(ValueError, match="empty response"):
        agent.choose_mode(OPTIONS, client=mock)


def test_choose_mode_raises_on_empty_options() -> None:
    agent = Agent(name="Alice")
    with pytest.raises(ValueError, match="at least one"):
        agent.choose_mode([], client=_mock_client("car", ""))


# --- prompt includes background ---


def test_choose_mode_prompt_includes_agent_demographics() -> None:
    agent = Agent(
        name="Bob",
        age=42,
        employment="employed",
        has_license=True,
        home_zone="zone_1",
        work_zone="zone_2",
        persona="Enjoys quiet commutes.",
    )
    mock = _mock_client("car", "Driving is convenient.")
    agent.choose_mode(OPTIONS, client=mock)

    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Age: 42" in prompt
    assert "Employment: employed" in prompt
    assert "Has driving licence: yes" in prompt
    assert "Home zone: zone_1" in prompt
    assert "Work zone: zone_2" in prompt
    assert "Persona: Enjoys quiet commutes." in prompt


def test_choose_mode_prompt_includes_household_context() -> None:
    agent = Agent(name="Carol", age=30, employment="employed", has_license=True)
    hh = Household(
        members=[agent],
        home_zone="zone_3",
        num_vehicles=2,
        income_level="high",
    )
    mock = _mock_client("car", "We have two cars.")
    agent.choose_mode(OPTIONS, client=mock, household=hh)

    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Household vehicles: 2" in prompt
    assert "Household income: high" in prompt


def test_choose_mode_prompt_omits_unset_optional_fields() -> None:
    agent = Agent(name="Dave")
    mock = _mock_client("bike", "Cycling is fun.")
    agent.choose_mode(OPTIONS, client=mock)

    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Age:" not in prompt  # age == 0 is omitted
    assert "Home zone:" not in prompt
    assert "Work zone:" not in prompt
    assert "School zone:" not in prompt
    assert "Persona:" not in prompt
    assert "Household" not in prompt


# --- choose work/school zone ---


def _mock_zone_client(zone_id: str) -> MagicMock:
    """Build a fake LLMClient that returns a fixed zone choice."""
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {"zone_id": zone_id, "reasoning": "Good commute."}
    )
    return mock


TRAVEL_TIMES = {
    "zone_a": {"car": 15, "transit": 30},
    "zone_b": {"car": 25, "transit": 20},
}


def test_choose_work_zone_sets_work_zone() -> None:
    agent = Agent(name="Alice", age=30, employment="employed")
    mock = _mock_zone_client("zone_a")
    zone_id, reasoning, prompt = agent.choose_work_zone(
        ZONES, TRAVEL_TIMES, client=mock
    )
    assert zone_id == "zone_a"
    assert agent.work_zone == "zone_a"
    assert reasoning == "Good commute."
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_choose_work_zone_raises_for_non_employed() -> None:
    agent = Agent(name="Bob", age=16, employment="student")
    with pytest.raises(ValueError, match="employed"):
        agent.choose_work_zone(ZONES, TRAVEL_TIMES, client=MagicMock())


def test_choose_work_zone_raises_on_empty_zones() -> None:
    agent = Agent(name="Carol", age=30, employment="employed")
    with pytest.raises(ValueError, match="at least one"):
        agent.choose_work_zone([], TRAVEL_TIMES, client=MagicMock())


def test_choose_work_zone_prompt_includes_travel_times() -> None:
    agent = Agent(name="Dave", age=35, employment="employed")
    mock = _mock_zone_client("zone_a")
    agent.choose_work_zone(ZONES, TRAVEL_TIMES, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "car 15 min" in prompt
    assert "transit 30 min" in prompt


def test_choose_school_zone_sets_school_zone() -> None:
    agent = Agent(name="Eve", age=16, employment="student")
    mock = _mock_zone_client("zone_b")
    zone_id, reasoning, prompt = agent.choose_school_zone(
        ZONES, TRAVEL_TIMES, client=mock
    )
    assert zone_id == "zone_b"
    assert agent.school_zone == "zone_b"
    assert reasoning == "Good commute."
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_choose_school_zone_raises_for_non_student() -> None:
    agent = Agent(name="Frank", age=30, employment="employed")
    with pytest.raises(ValueError, match="student"):
        agent.choose_school_zone(ZONES, TRAVEL_TIMES, client=MagicMock())


def test_choose_work_zone_skips_when_already_set() -> None:
    agent = Agent(name="Grace", age=30, employment="employed", work_zone="zone_x")
    mock = MagicMock()
    zone_id, reasoning, prompt = agent.choose_work_zone(
        ZONES, TRAVEL_TIMES, client=mock
    )
    assert zone_id == "zone_x"
    assert reasoning == ""
    assert prompt == ""
    mock.generate_json.assert_not_called()


def test_choose_work_zone_overwrites_when_requested() -> None:
    agent = Agent(name="Grace", age=30, employment="employed", work_zone="zone_x")
    mock = _mock_zone_client("zone_a")
    zone_id, reasoning, prompt = agent.choose_work_zone(
        ZONES, TRAVEL_TIMES, client=mock, overwrite=True
    )
    assert zone_id == "zone_a"
    assert agent.work_zone == "zone_a"
    assert len(reasoning) > 0
    assert len(prompt) > 0
    mock.generate_json.assert_called_once()


def test_choose_school_zone_skips_when_already_set() -> None:
    agent = Agent(name="Heidi", age=16, employment="student", school_zone="zone_y")
    mock = MagicMock()
    zone_id, reasoning, prompt = agent.choose_school_zone(
        ZONES, TRAVEL_TIMES, client=mock
    )
    assert zone_id == "zone_y"
    assert reasoning == ""
    assert prompt == ""
    mock.generate_json.assert_not_called()


def test_choose_school_zone_overwrites_when_requested() -> None:
    agent = Agent(name="Heidi", age=16, employment="student", school_zone="zone_y")
    mock = _mock_zone_client("zone_b")
    zone_id, reasoning, prompt = agent.choose_school_zone(
        ZONES, TRAVEL_TIMES, client=mock, overwrite=True
    )
    assert zone_id == "zone_b"
    assert agent.school_zone == "zone_b"
    assert len(reasoning) > 0
    assert len(prompt) > 0
    mock.generate_json.assert_called_once()


# --- generate activities ---


def _mock_activities_client(activity_types: list[dict]) -> MagicMock:
    """Build a fake LLMClient that returns a fixed activities JSON."""
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps({"activities": activity_types})
    return mock


def test_generate_activities_returns_nonempty_list() -> None:
    agent = Agent(name="Alice", age=30, employment="employed", work_zone="zone_2")
    mock = _mock_activities_client([{"type": "work", "is_flexible": False}])
    activities, prompt = agent.generate_activities(client=mock)
    assert isinstance(activities, list)
    assert len(activities) > 0
    assert all(isinstance(a, Activity) for a in activities)
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_generate_activities_employed_has_work_activity() -> None:
    agent = Agent(name="Bob", age=35, employment="employed", work_zone="zone_work")
    mock = _mock_activities_client(
        [
            {"type": "work", "is_flexible": False},
            {"type": "shopping", "is_flexible": True},
        ]
    )
    activities, _ = agent.generate_activities(client=mock)
    work_activities = [a for a in activities if a.type == "work"]
    assert len(work_activities) == 1
    work = work_activities[0]
    assert work.location == "zone_work"
    assert work.is_flexible is False


def test_generate_activities_student_has_school_activity() -> None:
    agent = Agent(name="Carol", age=16, employment="student", school_zone="zone_school")
    mock = _mock_activities_client([{"type": "school", "is_flexible": False}])
    activities, _ = agent.generate_activities(client=mock)
    school_activities = [a for a in activities if a.type == "school"]
    assert len(school_activities) == 1
    school = school_activities[0]
    assert school.location == "zone_school"
    assert school.is_flexible is False


def test_generate_activities_schema_has_enum_constraint() -> None:
    """The JSON schema constrains activity types via an enum."""
    agent = Agent(name="Eve", age=30, employment="employed", work_zone="z1")
    mock = _mock_activities_client([{"type": "work", "is_flexible": False}])
    agent.generate_activities(client=mock)
    schema = mock.generate_json.call_args.kwargs["schema"]
    item_schema = schema["properties"]["activities"]["items"]
    assert "enum" in item_schema["properties"]["type"]
    enum_values = item_schema["properties"]["type"]["enum"]
    assert set(enum_values) == VALID_OUT_OF_HOME_TYPES


def test_valid_out_of_home_types_is_complete() -> None:
    """Smoke-test the valid activity types constant."""
    assert "work" in VALID_OUT_OF_HOME_TYPES
    assert "school" in VALID_OUT_OF_HOME_TYPES
    assert "shopping" in VALID_OUT_OF_HOME_TYPES
    assert "commute" not in VALID_OUT_OF_HOME_TYPES


def test_generate_activities_retired_has_no_work_or_school() -> None:
    agent = Agent(name="Dave", age=67, employment="retired")
    mock = _mock_activities_client([{"type": "leisure", "is_flexible": True}])
    activities, _ = agent.generate_activities(client=mock)
    types_in_result = [a.type for a in activities]
    assert "work" not in types_in_result
    assert "school" not in types_in_result


# --- choose destination ---

ZONES = [
    Zone(
        id="zone_a",
        name="City Centre",
        x=0.0,
        y=0.0,
        land_use={"commercial": True, "residential": False},
    ),
    Zone(
        id="zone_b",
        name="Suburb North",
        x=1.0,
        y=1.0,
        land_use={"commercial": False, "residential": True},
    ),
]


def _mock_destination_client(dest_id: str) -> MagicMock:
    """Build a fake LLMClient that returns a fixed destination."""
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {"destination_id": dest_id, "reasoning": "Good fit."}
    )
    return mock


def test_choose_destination_raises_on_empty_candidates() -> None:
    agent = Agent(name="Alice")
    activity = Activity(type="shopping")
    with pytest.raises(ValueError, match="at least one"):
        agent.choose_destination(activity, candidates=[], client=MagicMock())


def test_choose_destination_sets_location() -> None:
    agent = Agent(name="Bob", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_a")
    result, _ = agent.choose_destination(activity, candidates=ZONES, client=mock)
    assert result.location == "zone_a"


def test_choose_destination_prompt_contains_activity_type() -> None:
    agent = Agent(name="Carol", age=25, employment="student")
    activity = Activity(type="leisure")
    mock = _mock_destination_client("zone:zone_b")
    agent.choose_destination(activity, candidates=ZONES, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "leisure" in prompt


def test_choose_destination_prompt_contains_zone_names() -> None:
    agent = Agent(name="Dave", age=40, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_a")
    agent.choose_destination(activity, candidates=ZONES, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "City Centre" in prompt
    assert "Suburb North" in prompt


# --- choose destination with POIs ---

POIS = [
    POI(
        id="101",
        name="Albert Heijn",
        x=25000.0,
        y=390000.0,
        activity_type="shopping",
        zone_id="zone_a",
    ),
    POI(
        id="102",
        name="Jumbo",
        x=26000.0,
        y=391000.0,
        activity_type="shopping",
        zone_id="zone_b",
    ),
]


def test_choose_destination_with_pois_sets_location() -> None:
    agent = Agent(name="Eve", age=28, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("poi:101")
    result, _ = agent.choose_destination(activity, pois=POIS, client=mock)
    assert result.location == "zone_a"
    assert result.poi_id == "101"


def test_choose_destination_poi_prompt_contains_names() -> None:
    agent = Agent(name="Frank", age=35, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("poi:101")
    agent.choose_destination(activity, pois=POIS, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Albert Heijn" in prompt
    assert "Jumbo" in prompt


def test_choose_destination_with_both_zones_and_pois() -> None:
    agent = Agent(name="Grace", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("poi:101")
    result, _ = agent.choose_destination(
        activity, candidates=ZONES, pois=POIS, client=mock
    )
    assert result.location == "zone_a"
    assert result.poi_id == "101"
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    # Both zones and POIs appear in the prompt
    assert "City Centre" in prompt
    assert "Albert Heijn" in prompt


def test_choose_destination_strips_prefix_from_raw_id() -> None:
    agent = Agent(name="Helen", age=40, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_b")
    result, _ = agent.choose_destination(activity, candidates=ZONES, client=mock)
    assert result.location == "zone_b"
    assert result.poi_id is None


def test_choose_destination_handles_bare_id() -> None:
    agent = Agent(name="Ivan", age=50, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone_a")
    result, _ = agent.choose_destination(activity, candidates=ZONES, client=mock)
    assert result.location == "zone_a"


def test_choose_destination_raises_when_no_candidates() -> None:
    agent = Agent(name="Jill")
    activity = Activity(type="shopping")
    with pytest.raises(ValueError, match="at least one"):
        agent.choose_destination(activity, client=MagicMock())


# --- choose destination with travel times ---


def _make_skims() -> list[Skim]:
    """Build small car + bike skims for zone_a and zone_b."""
    car = np.array([[0.0, 12.0], [12.0, 0.0]])
    bike = np.array([[0.0, 25.0], [25.0, 0.0]])
    return [
        Skim(mode="car", matrix=car, zone_ids=["zone_a", "zone_b"]),
        Skim(mode="bike", matrix=bike, zone_ids=["zone_a", "zone_b"]),
    ]


def test_choose_destination_travel_times_in_prompt() -> None:
    agent = Agent(name="Kim", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_a")
    skims = _make_skims()
    agent.choose_destination(
        activity,
        candidates=ZONES,
        client=mock,
        skims=skims,
        current_zone="zone_a",
    )
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times from your current location" in prompt
    assert "car 0 min" in prompt  # zone_a -> zone_a
    assert "car 12 min" in prompt  # zone_a -> zone_b


def test_choose_destination_no_travel_times_without_skims() -> None:
    agent = Agent(name="Leo", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_a")
    agent.choose_destination(activity, candidates=ZONES, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times" not in prompt


def test_choose_destination_falls_back_to_home_zone() -> None:
    agent = Agent(
        name="Mia",
        age=30,
        employment="employed",
        home_zone="zone_a",
    )
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:zone_b")
    skims = _make_skims()
    agent.choose_destination(
        activity,
        candidates=ZONES,
        client=mock,
        skims=skims,
        # current_zone not set — should use home_zone
    )
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times from your current location" in prompt
    assert "car 12 min" in prompt  # zone_a -> zone_b


def test_choose_destination_sampling_limits_candidates() -> None:
    many_zones = [Zone(id=f"z{i}", name=f"Zone {i}", x=0.0, y=0.0) for i in range(20)]
    agent = Agent(name="Ned", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone:z0")
    import random as rmod

    agent.choose_destination(
        activity,
        candidates=many_zones,
        client=mock,
        n_candidates=5,
        rng=rmod.Random(42),
    )
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    # Count zone: lines — should be at most 5
    zone_lines = [ln for ln in prompt.splitlines() if ln.strip().startswith("- zone:")]
    assert len(zone_lines) == 5


def test_choose_destination_poi_travel_times_use_zone_id() -> None:
    agent = Agent(name="Pia", age=30, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("poi:101")
    skims = _make_skims()
    agent.choose_destination(
        activity,
        pois=POIS,
        client=mock,
        skims=skims,
        current_zone="zone_a",
    )
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times" in prompt
    # POI 101 has zone_id="zone_a", so car=0, bike=0
    assert "poi:101: car 0 min" in prompt
    # POI 102 has zone_id="zone_b", so car=12, bike=25
    assert "poi:102: car 12 min" in prompt


# --- schedule activities ---


def _mock_schedule_client(schedule: list[dict]) -> MagicMock:
    """Build a fake LLMClient that returns a fixed schedule JSON."""
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps({"schedule": schedule})
    return mock


def test_schedule_activities_returns_day_plan() -> None:
    agent = Agent(name="Alice", age=30, employment="employed")
    activities = [Activity(type="work", is_flexible=False)]
    mock = _mock_schedule_client(
        [{"type": "work", "start_time": "08:00", "end_time": "17:00"}]
    )
    plan, prompt = agent.schedule_activities(activities, client=mock)
    assert isinstance(plan, DayPlan)
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_schedule_activities_sorted_by_start_time() -> None:
    agent = Agent(name="Bob", age=35, employment="employed")
    activities = [
        Activity(type="shopping", is_flexible=True),
        Activity(type="work", is_flexible=False),
    ]
    mock = _mock_schedule_client(
        [
            {"type": "work", "start_time": "08:00", "end_time": "17:00"},
            {"type": "shopping", "start_time": "18:00", "end_time": "19:00"},
        ]
    )
    plan, _ = agent.schedule_activities(activities, client=mock)
    start_times = [a.start_time for a in plan.activities]
    assert start_times == sorted(start_times)


def test_schedule_activities_sets_times_on_activities() -> None:
    agent = Agent(name="Carol", age=25, employment="student")
    activities = [Activity(type="school", is_flexible=False)]
    mock = _mock_schedule_client(
        [{"type": "school", "start_time": "08:00", "end_time": "15:00"}]
    )
    plan, _ = agent.schedule_activities(activities, client=mock)
    scheduled = plan.activities[0]
    assert scheduled.start_time == 480
    assert scheduled.end_time == 900


def test_schedule_activities_same_type_gets_different_times() -> None:
    """Two activities of the same type get their own time slots."""
    agent = Agent(name="Eve", age=30, employment="employed")
    activities = [
        Activity(type="shopping", is_flexible=True),
        Activity(type="shopping", is_flexible=True),
    ]
    mock = _mock_schedule_client(
        [
            {"type": "shopping", "start_time": "10:00", "end_time": "11:00"},
            {"type": "shopping", "start_time": "13:00", "end_time": "14:00"},
        ]
    )
    plan, _ = agent.schedule_activities(activities, client=mock)
    assert plan.activities[0].start_time == 600
    assert plan.activities[1].start_time == 780


def test_schedule_activities_empty_input_returns_empty_plan() -> None:
    agent = Agent(name="Dave", age=67, employment="retired")
    mock = MagicMock()
    plan, prompt = agent.schedule_activities([], client=mock)
    assert isinstance(plan, DayPlan)
    assert plan.activities == []
    assert prompt == ""
    mock.generate_json.assert_not_called()


# --- build tours ---


def test_build_tours_home_work_home() -> None:
    agent = Agent(name="Alice", age=30, employment="employed", home_zone="h")
    plan = DayPlan(
        activities=[
            Activity(
                type="work",
                location="w",
                start_time=480,
                end_time=1020,
            ),
        ]
    )
    result = agent.build_tours(plan)
    assert len(result.tours) == 1
    tour = result.tours[0]
    assert len(tour.trips) == 2
    assert tour.trips[0].origin == "h"
    assert tour.trips[0].destination == "w"
    assert tour.trips[1].origin == "w"
    assert tour.trips[1].destination == "h"
    assert tour.is_closed


def test_build_tours_multi_stop() -> None:
    agent = Agent(name="Bob", age=35, employment="employed", home_zone="h")
    plan = DayPlan(
        activities=[
            Activity(
                type="work",
                location="w",
                start_time=480,
                end_time=1020,
            ),
            Activity(
                type="shopping",
                location="s",
                start_time=1080,
                end_time=1140,
            ),
        ]
    )
    result = agent.build_tours(plan)
    trips = result.trips
    assert len(trips) == 3
    assert trips[0].origin == "h"
    assert trips[0].destination == "w"
    assert trips[1].origin == "w"
    assert trips[1].destination == "s"
    assert trips[2].origin == "s"
    assert trips[2].destination == "h"


def test_build_tours_empty_activities() -> None:
    agent = Agent(name="Carol", age=67, employment="retired", home_zone="h")
    plan = DayPlan(activities=[])
    result = agent.build_tours(plan)
    assert result.tours == []


def test_build_tours_raises_without_home_zone() -> None:
    agent = Agent(name="Dave", age=30, employment="employed")
    plan = DayPlan(
        activities=[
            Activity(
                type="work",
                location="w",
                start_time=480,
                end_time=1020,
            ),
        ]
    )
    with pytest.raises(ValueError, match="home_zone"):
        agent.build_tours(plan)


def test_build_tours_raises_on_missing_location() -> None:
    agent = Agent(name="Eve", age=30, employment="employed", home_zone="h")
    plan = DayPlan(
        activities=[
            Activity(type="work", start_time=480, end_time=1020),
        ]
    )
    with pytest.raises(ValueError, match="no location"):
        agent.build_tours(plan)


# --- choose tour mode ---


def test_choose_tour_mode_sets_mode_on_all_trips() -> None:
    agent = Agent(name="Alice", age=30, employment="employed")
    t1 = Trip(origin="h", destination="w")
    t2 = Trip(origin="w", destination="h")
    tour = Tour(trips=[t1, t2], home_zone="h")
    mock = _mock_client("car", "Driving today.")
    mc, prompt = agent.choose_tour_mode(tour, OPTIONS, client=mock)
    assert mc.option.mode == "car"
    assert t1.mode == "car"
    assert t2.mode == "car"
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_choose_tour_mode_raises_on_empty_tour() -> None:
    agent = Agent(name="Bob")
    tour = Tour(trips=[], home_zone="h")
    with pytest.raises(ValueError, match="at least one trip"):
        agent.choose_tour_mode(tour, OPTIONS, client=MagicMock())


def test_build_tours_tour_is_closed() -> None:
    agent = Agent(name="Frank", age=25, employment="student", home_zone="h")
    plan = DayPlan(
        activities=[
            Activity(
                type="school",
                location="sc",
                start_time=480,
                end_time=900,
            ),
        ]
    )
    result = agent.build_tours(plan)
    assert all(t.is_closed for t in result.tours)


def test_schedule_activities_travel_times_in_prompt() -> None:
    """Travel times appear in the prompt when skims and locations are set."""
    agent = Agent(name="Alice", age=30, employment="employed")
    activities = [
        Activity(type="work", is_flexible=False, location="zone_a"),
        Activity(type="shopping", is_flexible=True, location="zone_b"),
    ]
    mock = _mock_schedule_client(
        [
            {"type": "work", "start_time": "08:00", "end_time": "17:00"},
            {"type": "shopping", "start_time": "17:20", "end_time": "18:20"},
        ]
    )
    skims = _make_skims()  # car 12 min zone_a → zone_b
    agent.schedule_activities(activities, client=mock, skims=skims)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times between consecutive activities" in prompt
    assert "work → shopping" in prompt
    assert "car 12 min" in prompt


def test_schedule_activities_min_durations_in_prompt() -> None:
    """Minimum duration hints appear in the prompt."""
    agent = Agent(name="Bob", age=35, employment="employed")
    activities = [
        Activity(type="work", is_flexible=False, location="zone_a"),
        Activity(type="shopping", is_flexible=True, location="zone_b"),
    ]
    mock = _mock_schedule_client(
        [
            {"type": "work", "start_time": "08:00", "end_time": "17:00"},
            {"type": "shopping", "start_time": "17:20", "end_time": "18:20"},
        ]
    )
    agent.schedule_activities(activities, client=mock)
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Suggested minimum durations" in prompt
    assert "work" in prompt
    assert "shopping" in prompt


def test_schedule_activities_no_travel_times_without_skims() -> None:
    """Without skims the travel-time block is omitted from the prompt."""
    agent = Agent(name="Carol", age=25, employment="student")
    activities = [Activity(type="school", is_flexible=False, location="zone_a")]
    mock = _mock_schedule_client(
        [{"type": "school", "start_time": "08:00", "end_time": "15:00"}]
    )
    agent.schedule_activities(activities, client=mock)  # no skims kwarg
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    assert "Travel times between consecutive activities" not in prompt


# --- plan discretionary activities ---


def _make_3zone_skims() -> list[Skim]:
    """3-zone car skim: home(0), work(1), shop(2)."""
    mat = np.array(
        [
            [0.0, 15.0, 5.0],
            [15.0, 0.0, 3.0],
            [5.0, 3.0, 0.0],
        ]
    )
    zones = ["zone_home", "zone_work", "zone_shop"]
    return [Skim(mode="car", matrix=mat, zone_ids=zones)]


def test_plan_discretionary_activities_sets_fields() -> None:
    """The method mutates each discretionary Activity with location and times."""
    agent = Agent(
        name="Alice",
        age=30,
        employment="employed",
        home_zone="zone_home",
        work_zone="zone_work",
    )
    work = Activity(
        type="work",
        is_flexible=False,
        location="zone_work",
        start_time=480,
        end_time=1020,
    )
    shopping = Activity(type="shopping", is_flexible=True)
    poi = POI(
        id="p1",
        name="Albert Heijn",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="zone_shop",
    )
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {
            "planned_activities": [
                {
                    "type": "shopping",
                    "destination_id": "poi:p1",
                    "start_time": "17:30",
                    "end_time": "18:30",
                    "reasoning": "Convenient after work.",
                }
            ]
        }
    )
    result, prompt = agent.plan_discretionary_activities(
        mandatory=[work],
        discretionary=[shopping],
        pois_by_type={"shopping": [poi]},
        skims=_make_3zone_skims(),
        client=mock,
    )
    assert len(result) == 1
    act = result[0]
    assert act.poi_id == "p1"
    assert act.location == "zone_shop"
    assert act.start_time == 1050
    assert act.end_time == 1110
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_plan_discretionary_activities_prompt_content() -> None:
    """Prompt contains mandatory activity times and POI name."""
    agent = Agent(
        name="Bob",
        age=35,
        employment="employed",
        home_zone="zone_home",
        work_zone="zone_work",
    )
    work = Activity(
        type="work",
        is_flexible=False,
        location="zone_work",
        start_time=480,
        end_time=1050,
    )
    shopping = Activity(type="shopping", is_flexible=True)
    poi = POI(
        id="p1",
        name="Albert Heijn",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="zone_shop",
    )
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {
            "planned_activities": [
                {
                    "type": "shopping",
                    "destination_id": "poi:p1",
                    "start_time": "18:00",
                    "end_time": "19:00",
                    "reasoning": "Close to work.",
                }
            ]
        }
    )
    agent.plan_discretionary_activities(
        mandatory=[work],
        discretionary=[shopping],
        pois_by_type={"shopping": [poi]},
        skims=_make_3zone_skims(),
        client=mock,
    )
    prompt = mock.generate_json.call_args.kwargs["prompt"]
    # Mandatory work times appear formatted as HH:MM
    assert "08:00" in prompt
    assert "17:30" in prompt
    # POI name appears
    assert "Albert Heijn" in prompt
    # Travel times from both home and work appear
    assert "from home" in prompt
    assert "from work" in prompt


def test_plan_discretionary_activities_empty_returns_unchanged() -> None:
    """An empty discretionary list is returned without calling the LLM."""
    agent = Agent(name="Carol", age=25, employment="student")
    mock = MagicMock()
    result, prompt = agent.plan_discretionary_activities(
        mandatory=[],
        discretionary=[],
        pois_by_type={},
        skims=[],
        client=mock,
    )
    assert result == []
    assert prompt == ""
    mock.generate_json.assert_not_called()


def test_plan_discretionary_activities_bare_zone_id() -> None:
    """A bare zone id (no poi: prefix) is stored as location directly."""
    agent = Agent(
        name="Dave",
        age=40,
        employment="employed",
        home_zone="zone_home",
    )
    leisure = Activity(type="leisure", is_flexible=True)
    poi = POI(
        id="px",
        name="Park",
        x=0.0,
        y=0.0,
        activity_type="leisure",
        zone_id="zone_shop",
    )
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {
            "planned_activities": [
                {
                    "type": "leisure",
                    "destination_id": "zone:zone_shop",
                    "start_time": "15:00",
                    "end_time": "17:00",
                    "reasoning": "Nice park.",
                }
            ]
        }
    )
    result, _ = agent.plan_discretionary_activities(
        mandatory=[],
        discretionary=[leisure],
        pois_by_type={"leisure": [poi]},
        skims=_make_3zone_skims(),
        client=mock,
    )
    assert result[0].location == "zone_shop"
    assert result[0].poi_id is None


_WINDOWS_AB = [
    TimeWindow(
        start=360,
        end=465,
        preceding_location="zone_home",
        following_location="zone_work",
    ),
    TimeWindow(
        start=1035,
        end=1380,
        preceding_location="zone_work",
        following_location="zone_home",
    ),
]


def _mock_disc_with_gap(gap: str) -> MagicMock:
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {
            "planned_activities": [
                {
                    "type": "shopping",
                    "gap": gap,
                    "destination_id": "poi:p1",
                    "start_time": "17:30",
                    "end_time": "18:30",
                    "reasoning": "After work.",
                }
            ]
        }
    )
    return mock


def test_plan_discretionary_activities_gap_labels_in_prompt() -> None:
    """Gap labels (A, B) and the few-shot example appear when windows given."""
    agent = Agent(
        name="Alice",
        age=30,
        employment="employed",
        home_zone="zone_home",
        work_zone="zone_work",
    )
    work = Activity(
        type="work",
        is_flexible=False,
        location="zone_work",
        start_time=480,
        end_time=1020,
    )
    shopping = Activity(type="shopping", is_flexible=True)
    poi = POI(
        id="p1",
        name="Albert Heijn",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="zone_shop",
    )
    _, prompt = agent.plan_discretionary_activities(
        mandatory=[work],
        discretionary=[shopping],
        pois_by_type={"shopping": [poi]},
        skims=_make_3zone_skims(),
        client=_mock_disc_with_gap("B"),
        time_windows=_WINDOWS_AB,
    )
    assert "Gap A" in prompt
    assert "Gap B" in prompt
    assert "Emma" in prompt  # static example agent name


def test_plan_discretionary_activities_gap_enum_in_schema() -> None:
    """Schema includes a gap enum field when time windows are provided."""
    agent = Agent(
        name="Bob",
        age=35,
        employment="employed",
        home_zone="zone_home",
        work_zone="zone_work",
    )
    work = Activity(
        type="work",
        is_flexible=False,
        location="zone_work",
        start_time=480,
        end_time=1020,
    )
    shopping = Activity(type="shopping", is_flexible=True)
    poi = POI(
        id="p1",
        name="Albert Heijn",
        x=0.0,
        y=0.0,
        activity_type="shopping",
        zone_id="zone_shop",
    )
    mock = _mock_disc_with_gap("B")
    agent.plan_discretionary_activities(
        mandatory=[work],
        discretionary=[shopping],
        pois_by_type={"shopping": [poi]},
        skims=_make_3zone_skims(),
        client=mock,
        time_windows=_WINDOWS_AB,
    )
    schema = mock.generate_json.call_args.kwargs["schema"]
    item = schema["properties"]["planned_activities"]["items"]
    assert "gap" in item["properties"]
    assert item["properties"]["gap"]["enum"] == ["A", "B"]
    assert "gap" in item["required"]


def test_plan_discretionary_activities_no_gap_without_windows() -> None:
    """Schema has no gap field when no time windows are provided."""
    agent = Agent(
        name="Carol",
        age=25,
        employment="student",
        home_zone="zone_home",
    )
    leisure = Activity(type="leisure", is_flexible=True)
    poi = POI(
        id="px",
        name="Park",
        x=0.0,
        y=0.0,
        activity_type="leisure",
        zone_id="zone_shop",
    )
    mock = MagicMock()
    mock.generate_json.return_value = json.dumps(
        {
            "planned_activities": [
                {
                    "type": "leisure",
                    "destination_id": "poi:px",
                    "start_time": "15:00",
                    "end_time": "17:00",
                    "reasoning": "Nice park.",
                }
            ]
        }
    )
    agent.plan_discretionary_activities(
        mandatory=[],
        discretionary=[leisure],
        pois_by_type={"leisure": [poi]},
        skims=_make_3zone_skims(),
        client=mock,
    )
    schema = mock.generate_json.call_args.kwargs["schema"]
    item = schema["properties"]["planned_activities"]["items"]
    assert "gap" not in item["properties"]
