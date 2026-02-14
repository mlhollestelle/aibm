import pytest

from aibm.agent import Agent, ModeOption


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


# --- mode choice ---

OPTIONS = [
    ModeOption(mode="car", travel_time=20.0),
    ModeOption(mode="bike", travel_time=35.0),
    ModeOption(mode="transit", travel_time=25.0),
]


def test_choose_mode_returns_a_mode_option() -> None:
    agent = Agent(name="Alice")
    chosen = agent.choose_mode(OPTIONS)
    assert isinstance(chosen, ModeOption)


def test_choose_mode_is_one_of_the_options() -> None:
    agent = Agent(name="Alice")
    chosen = agent.choose_mode(OPTIONS)
    assert chosen in OPTIONS


def test_choose_mode_raises_on_empty_options() -> None:
    agent = Agent(name="Alice")
    with pytest.raises(ValueError, match="at least one"):
        agent.choose_mode([])
