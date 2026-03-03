"""Tests for the configurable prompt system."""

from aibm.prompts import (
    DEFAULT_PERSONA_FRAMING,
    DEFAULT_PERSONA_INSTRUCTIONS,
    DEFAULT_PERSONA_ROLE,
    PromptConfig,
    StepPrompt,
    build_prompt,
    load_prompt_config,
)


class TestBuildPrompt:
    """Tests for build_prompt assembly."""

    def test_basic_assembly(self) -> None:
        step = StepPrompt(
            role="Hello {agent_name}.",
            context_framing="Data follows:",
            instructions="Do the thing.",
        )
        result = build_prompt(step, {"agent_name": "Alice"}, "x=1")
        assert result == ("Hello Alice.\nData follows:\nx=1\n\nDo the thing.")

    def test_missing_placeholder_preserved(self) -> None:
        step = StepPrompt(
            role="Hello {agent_name} in {city}.",
            context_framing="",
            instructions="Go.",
        )
        result = build_prompt(step, {"agent_name": "Bob"}, "")
        assert "{city}" in result
        assert "Bob" in result

    def test_empty_data_block(self) -> None:
        step = StepPrompt(role="R", context_framing="F", instructions="I")
        result = build_prompt(step, {}, "")
        assert result == "R\nF\n\n\nI"

    def test_multiline_data_block(self) -> None:
        step = StepPrompt(role="R", context_framing="F", instructions="I")
        data = "line1\nline2\nline3"
        result = build_prompt(step, {}, data)
        assert "line1\nline2\nline3" in result

    def test_purpose_placeholder(self) -> None:
        step = StepPrompt(
            role="Choose a {purpose} zone.",
            context_framing="",
            instructions="Pick one {purpose}.",
        )
        result = build_prompt(step, {"purpose": "work"}, "zones here")
        assert "Choose a work zone." in result
        assert "Pick one work." in result


class TestLoadPromptConfig:
    """Tests for load_prompt_config partial overrides."""

    def test_empty_config_returns_defaults(self) -> None:
        pc = load_prompt_config({})
        assert pc.persona.role == DEFAULT_PERSONA_ROLE
        assert pc.persona.context_framing == DEFAULT_PERSONA_FRAMING
        assert pc.persona.instructions == DEFAULT_PERSONA_INSTRUCTIONS

    def test_override_single_section(self) -> None:
        pc = load_prompt_config(
            {
                "persona": {"role": "Custom role for {agent_name}."},
            }
        )
        assert pc.persona.role == "Custom role for {agent_name}."
        # Other sections keep defaults.
        assert pc.persona.context_framing == DEFAULT_PERSONA_FRAMING
        assert pc.persona.instructions == DEFAULT_PERSONA_INSTRUCTIONS

    def test_override_multiple_sections(self) -> None:
        pc = load_prompt_config(
            {
                "mode_choice": {
                    "role": "You are eco-{agent_name}.",
                    "instructions": "Always pick bike.",
                },
            }
        )
        assert pc.mode_choice.role == "You are eco-{agent_name}."
        assert pc.mode_choice.instructions == "Always pick bike."

    def test_override_multiple_steps(self) -> None:
        pc = load_prompt_config(
            {
                "persona": {"role": "Custom persona."},
                "scheduling": {"instructions": "Be early."},
            }
        )
        assert pc.persona.role == "Custom persona."
        assert pc.scheduling.instructions == "Be early."

    def test_unknown_step_ignored(self) -> None:
        pc = load_prompt_config({"nonexistent_step": {"role": "X"}})
        # Should not raise; defaults intact.
        assert pc.persona.role == DEFAULT_PERSONA_ROLE

    def test_all_ten_steps_have_defaults(self) -> None:
        pc = PromptConfig()
        step_names = [
            "persona",
            "mode_choice",
            "zone_choice",
            "activities",
            "destination",
            "scheduling",
            "discretionary",
            "vehicle_allocation",
            "escort",
            "joint_activities",
        ]
        for name in step_names:
            step = getattr(pc, name)
            assert isinstance(step, StepPrompt)
            assert step.role
            assert step.instructions


class TestDefaultRendering:
    """Verify defaults render without errors."""

    def test_persona_defaults_render(self) -> None:
        pc = PromptConfig()
        result = build_prompt(
            pc.persona,
            {"agent_name": "Jan"},
            "Age: 35\nEmployment: employed",
        )
        assert "Jan" in result
        assert "Age: 35" in result
        assert "persona" in result.lower()

    def test_zone_choice_defaults_render(self) -> None:
        pc = PromptConfig()
        result = build_prompt(
            pc.zone_choice,
            {"agent_name": "Piet", "purpose": "work"},
            "Zone list here",
        )
        assert "Piet" in result
        assert "work" in result
