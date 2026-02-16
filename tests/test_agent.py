from unittest.mock import MagicMock

import pytest

from aibm.agent import Agent, ModeChoice, ModeOption
from aibm.household import Household


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
