import json
from unittest.mock import MagicMock

import pytest

from aibm.activity import Activity
from aibm.agent import Agent, ModeChoice, ModeOption
from aibm.household import Household
from aibm.zone import Zone


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
    """Build a fake genai.Client that returns a fixed persona JSON response."""
    mock = MagicMock()
    mock.models.generate_content.return_value.text = f'{{"persona": "{persona}"}}'
    return mock


def test_generate_persona_returns_string() -> None:
    agent = Agent(name="Alice", age=30, employment="employed")
    mock = _mock_persona_client("Drives to work every day.")
    result = agent.generate_persona(client=mock)
    assert isinstance(result, str)
    assert result == "Drives to work every day."


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

    prompt = mock.models.generate_content.call_args.kwargs["contents"]
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

    prompt = mock.models.generate_content.call_args.kwargs["contents"]
    assert "Household vehicles: 1" in prompt
    assert "Household income: medium" in prompt


def test_generate_persona_raises_on_empty_response() -> None:
    agent = Agent(name="Eve")
    mock = MagicMock()
    mock.models.generate_content.return_value.text = None
    with pytest.raises(ValueError, match="empty response"):
        agent.generate_persona(client=mock)


# --- mode choice ---

OPTIONS = [
    ModeOption(mode="car", travel_time=20.0),
    ModeOption(mode="bike", travel_time=35.0),
    ModeOption(mode="transit", travel_time=25.0),
]


def _mock_client(choice: str, reasoning: str) -> MagicMock:
    """Build a fake genai.Client that returns a fixed JSON response."""
    mock = MagicMock()
    mock.models.generate_content.return_value.text = (
        f'{{"reasoning": "{reasoning}", "choice": "{choice}"}}'
    )
    return mock


def test_choose_mode_returns_a_mode_choice() -> None:
    agent = Agent(name="Alice")
    result = agent.choose_mode(OPTIONS, client=_mock_client("car", "Car is fastest."))
    assert isinstance(result, ModeChoice)


def test_choose_mode_option_is_one_of_the_options() -> None:
    agent = Agent(name="Alice")
    result = agent.choose_mode(OPTIONS, client=_mock_client("bike", "I like cycling."))
    assert result.option in OPTIONS


def test_choose_mode_returns_correct_option() -> None:
    agent = Agent(name="Alice")
    result = agent.choose_mode(
        OPTIONS, client=_mock_client("transit", "Bus is relaxing.")
    )
    assert result.option.mode == "transit"


def test_choose_mode_includes_reasoning() -> None:
    agent = Agent(name="Alice")
    result = agent.choose_mode(OPTIONS, client=_mock_client("car", "Car is fastest."))
    assert result.reasoning == "Car is fastest."


def test_choose_mode_raises_on_empty_llm_response() -> None:
    agent = Agent(name="Alice")
    mock = MagicMock()
    mock.models.generate_content.return_value.text = None
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

    prompt = mock.models.generate_content.call_args.kwargs["contents"]
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

    prompt = mock.models.generate_content.call_args.kwargs["contents"]
    assert "Household vehicles: 2" in prompt
    assert "Household income: high" in prompt


def test_choose_mode_prompt_omits_unset_optional_fields() -> None:
    agent = Agent(name="Dave")
    mock = _mock_client("bike", "Cycling is fun.")
    agent.choose_mode(OPTIONS, client=mock)

    prompt = mock.models.generate_content.call_args.kwargs["contents"]
    assert "Age:" not in prompt  # age == 0 is omitted
    assert "Home zone:" not in prompt
    assert "Work zone:" not in prompt
    assert "School zone:" not in prompt
    assert "Persona:" not in prompt
    assert "Household" not in prompt


# --- generate activities ---


def _mock_activities_client(activity_types: list[dict]) -> MagicMock:
    """Build a fake genai.Client that returns a fixed activities JSON response."""
    mock = MagicMock()
    mock.models.generate_content.return_value.text = json.dumps(
        {"activities": activity_types}
    )
    return mock


def test_generate_activities_returns_nonempty_list() -> None:
    agent = Agent(name="Alice", age=30, employment="employed", work_zone="zone_2")
    mock = _mock_activities_client([{"type": "work", "is_flexible": False}])
    result = agent.generate_activities(client=mock)
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(a, Activity) for a in result)


def test_generate_activities_employed_has_work_activity() -> None:
    agent = Agent(name="Bob", age=35, employment="employed", work_zone="zone_work")
    mock = _mock_activities_client(
        [
            {"type": "work", "is_flexible": False},
            {"type": "shopping", "is_flexible": True},
        ]
    )
    result = agent.generate_activities(client=mock)
    work_activities = [a for a in result if a.type == "work"]
    assert len(work_activities) == 1
    work = work_activities[0]
    assert work.location == "zone_work"
    assert work.is_flexible is False


def test_generate_activities_student_has_school_activity() -> None:
    agent = Agent(name="Carol", age=16, employment="student", school_zone="zone_school")
    mock = _mock_activities_client([{"type": "school", "is_flexible": False}])
    result = agent.generate_activities(client=mock)
    school_activities = [a for a in result if a.type == "school"]
    assert len(school_activities) == 1
    school = school_activities[0]
    assert school.location == "zone_school"
    assert school.is_flexible is False


def test_generate_activities_retired_has_no_work_or_school() -> None:
    agent = Agent(name="Dave", age=67, employment="retired")
    mock = _mock_activities_client([{"type": "leisure", "is_flexible": True}])
    result = agent.generate_activities(client=mock)
    types_in_result = [a.type for a in result]
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


def _mock_destination_client(zone_id: str) -> MagicMock:
    """Build a fake genai.Client that returns a fixed destination JSON response."""
    mock = MagicMock()
    mock.models.generate_content.return_value.text = json.dumps(
        {"zone_id": zone_id, "reasoning": "Good fit."}
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
    mock = _mock_destination_client("zone_a")
    result = agent.choose_destination(activity, candidates=ZONES, client=mock)
    candidate_ids = [z.id for z in ZONES]
    assert result.location in candidate_ids


def test_choose_destination_prompt_contains_activity_type() -> None:
    agent = Agent(name="Carol", age=25, employment="student")
    activity = Activity(type="leisure")
    mock = _mock_destination_client("zone_b")
    agent.choose_destination(activity, candidates=ZONES, client=mock)
    prompt = mock.models.generate_content.call_args.kwargs["contents"]
    assert "leisure" in prompt


def test_choose_destination_prompt_contains_zone_names() -> None:
    agent = Agent(name="Dave", age=40, employment="employed")
    activity = Activity(type="shopping")
    mock = _mock_destination_client("zone_a")
    agent.choose_destination(activity, candidates=ZONES, client=mock)
    prompt = mock.models.generate_content.call_args.kwargs["contents"]
    assert "City Centre" in prompt
    assert "Suburb North" in prompt
