"""Configurable prompt templates for every LLM step.

Each simulation step has a :class:`StepPrompt` with three
configurable text sections — *role*, *context_framing*, and
*instructions* — plus an auto-injected *data* block assembled
at runtime.  Users override individual sections via the
``simulation.prompts`` key in ``config.yaml``; anything omitted
falls back to the built-in default.

Sections may contain ``{placeholder}`` variables (e.g.
``{agent_name}``, ``{purpose}``) which are expanded at runtime
with :meth:`str.format_map`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── persona ──────────────────────────────────────────────────

DEFAULT_PERSONA_ROLE = "You are creating a behavioural profile for {agent_name}."
DEFAULT_PERSONA_FRAMING = "Demographics:"
DEFAULT_PERSONA_INSTRUCTIONS = (
    "Write a 1-2 sentence persona describing this "
    "person's travel habits, preferences, and daily "
    "routine. Be specific and grounded in the "
    "demographics above."
)

# ── mode_choice ──────────────────────────────────────────────

DEFAULT_MODE_CHOICE_ROLE = "You are {agent_name}, deciding how to travel today."
DEFAULT_MODE_CHOICE_FRAMING = "Background:"
DEFAULT_MODE_CHOICE_INSTRUCTIONS = (
    "Pick exactly one mode. Respond with:\n"
    '- "reasoning": a short personal story '
    "(2-3 sentences) explaining your choice.\n"
    '- "choice": the mode name exactly as listed above.'
)

# ── zone_choice ──────────────────────────────────────────────

DEFAULT_ZONE_CHOICE_ROLE = "You are {agent_name}, choosing a {purpose} location."
DEFAULT_ZONE_CHOICE_FRAMING = "Background:"
DEFAULT_ZONE_CHOICE_INSTRUCTIONS = (
    "Pick exactly one zone id for your {purpose}. "
    "Respond with the zone id and your reasoning."
)

# ── activities ───────────────────────────────────────────────

DEFAULT_ACTIVITIES_ROLE = "You are {agent_name}, planning your day."
DEFAULT_ACTIVITIES_FRAMING = "Background:"
DEFAULT_ACTIVITIES_INSTRUCTIONS = (
    "Only include out-of-home activities. "
    "Include mandatory activities: work if you are "
    "employed, school if you are a student. "
    "Also include any discretionary activities. "
    "For each activity specify whether it has a "
    "flexible time (is_flexible true) or is fixed "
    "(is_flexible false). Work and school are always "
    "fixed (is_flexible false).\n"
    "Allowed activity types: {types_list}."
)

# ── destination ──────────────────────────────────────────────

DEFAULT_DESTINATION_ROLE = "You are {agent_name}, choosing where to do an activity."
DEFAULT_DESTINATION_FRAMING = "Background:"
DEFAULT_DESTINATION_INSTRUCTIONS = (
    "Pick exactly one id (including the zone: or "
    "poi: prefix) from the list above that best fits "
    "this activity. Respond with the id and your "
    "reasoning."
)

# ── scheduling ───────────────────────────────────────────────

DEFAULT_SCHEDULING_ROLE = "You are {agent_name}, scheduling your day."
DEFAULT_SCHEDULING_FRAMING = "Background:"
DEFAULT_SCHEDULING_INSTRUCTIONS = (
    "Assign a start_time and end_time (as HH:MM strings, "
    'e.g. "08:00") to each activity. '
    "Ensure each activity starts at least as late as the "
    "previous activity's end_time plus the travel time to "
    "reach it. "
    "Fixed activities have realistic fixed hours; flexible "
    "ones fill the remaining time. Return them in "
    "chronological order."
)

# ── discretionary (with time gaps) ───────────────────────────

DEFAULT_DISCRETIONARY_GAPS_ROLE = "You are {agent_name}, planning the rest of your day."
DEFAULT_DISCRETIONARY_GAPS_FRAMING = "Background:"
DEFAULT_DISCRETIONARY_GAPS_INSTRUCTIONS = (
    "For each activity: choose a destination, specify "
    "which gap (A, B, …) it fits in, and assign "
    "start_time and end_time as HH:MM strings "
    '(e.g. "17:30") that fall within that gap. '
    "You must be home by 23:00. "
    "Return one entry per activity in chronological order."
)

# ── discretionary (no time gaps) ─────────────────────────────

DEFAULT_DISCRETIONARY_NOGAPS_ROLE = (
    "You are {agent_name}, planning your discretionary activities for today."
)
DEFAULT_DISCRETIONARY_NOGAPS_FRAMING = "Background:"
DEFAULT_DISCRETIONARY_NOGAPS_INSTRUCTIONS = (
    "For each activity choose a destination and assign "
    "start_time and end_time as HH:MM strings "
    '(e.g. "08:00"). '
    "The schedule must be feasible: allow travel time "
    "between activities. "
    "Return one entry per activity in chronological order."
)

# ── vehicle_allocation ───────────────────────────────────────

DEFAULT_VEHICLE_ALLOCATION_ROLE = "You are deciding vehicle access for a household."
DEFAULT_VEHICLE_ALLOCATION_FRAMING = ""
DEFAULT_VEHICLE_ALLOCATION_INSTRUCTIONS = (
    "Assign vehicle access (true/false) to each member "
    "for each tour. Prioritise members who need the car "
    "most (long distances, work commutes, chained trips)."
)

# ── escort ───────────────────────────────────────────────────

DEFAULT_ESCORT_ROLE = "You are arranging escort trips for a household."
DEFAULT_ESCORT_FRAMING = (
    "This household needs to arrange escort trips for children who cannot travel alone."
)
DEFAULT_ESCORT_INSTRUCTIONS = (
    "For each child activity, assign a parent for "
    "drop-off and a parent for pick-up. "
    "The same parent can do both."
)

# ── joint_activities ─────────────────────────────────────────

DEFAULT_JOINT_ACTIVITIES_ROLE = "You are planning shared activities for a household."
DEFAULT_JOINT_ACTIVITIES_FRAMING = (
    "This household is considering shared activities that members can do together."
)
DEFAULT_JOINT_ACTIVITIES_INSTRUCTIONS = (
    "Propose 0-2 joint activities that fit everyone's "
    "schedule. Each activity needs a destination, "
    "start/end time, and which members participate. "
    "Only propose activities if they make sense given "
    "the schedules."
)


# ── dataclasses ──────────────────────────────────────────────


@dataclass
class StepPrompt:
    """Three configurable text sections for one LLM step.

    Attributes:
        role: Frames the agent's identity/mindset.
        context_framing: Introduces the data block.
        instructions: Tells the LLM what to do and
            how to respond.
    """

    role: str
    context_framing: str
    instructions: str


@dataclass
class PromptConfig:
    """Holds a :class:`StepPrompt` for each simulation step.

    All fields default to the built-in prompt text. Only
    sections the user overrides in ``config.yaml`` differ
    from the defaults.
    """

    persona: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_PERSONA_ROLE,
            context_framing=DEFAULT_PERSONA_FRAMING,
            instructions=DEFAULT_PERSONA_INSTRUCTIONS,
        )
    )
    mode_choice: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_MODE_CHOICE_ROLE,
            context_framing=DEFAULT_MODE_CHOICE_FRAMING,
            instructions=DEFAULT_MODE_CHOICE_INSTRUCTIONS,
        )
    )
    zone_choice: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_ZONE_CHOICE_ROLE,
            context_framing=DEFAULT_ZONE_CHOICE_FRAMING,
            instructions=DEFAULT_ZONE_CHOICE_INSTRUCTIONS,
        )
    )
    activities: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_ACTIVITIES_ROLE,
            context_framing=DEFAULT_ACTIVITIES_FRAMING,
            instructions=DEFAULT_ACTIVITIES_INSTRUCTIONS,
        )
    )
    destination: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_DESTINATION_ROLE,
            context_framing=DEFAULT_DESTINATION_FRAMING,
            instructions=DEFAULT_DESTINATION_INSTRUCTIONS,
        )
    )
    scheduling: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_SCHEDULING_ROLE,
            context_framing=DEFAULT_SCHEDULING_FRAMING,
            instructions=DEFAULT_SCHEDULING_INSTRUCTIONS,
        )
    )
    discretionary: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_DISCRETIONARY_GAPS_ROLE,
            context_framing=DEFAULT_DISCRETIONARY_GAPS_FRAMING,
            instructions=DEFAULT_DISCRETIONARY_GAPS_INSTRUCTIONS,
        )
    )
    vehicle_allocation: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_VEHICLE_ALLOCATION_ROLE,
            context_framing=DEFAULT_VEHICLE_ALLOCATION_FRAMING,
            instructions=DEFAULT_VEHICLE_ALLOCATION_INSTRUCTIONS,
        )
    )
    escort: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_ESCORT_ROLE,
            context_framing=DEFAULT_ESCORT_FRAMING,
            instructions=DEFAULT_ESCORT_INSTRUCTIONS,
        )
    )
    joint_activities: StepPrompt = field(
        default_factory=lambda: StepPrompt(
            role=DEFAULT_JOINT_ACTIVITIES_ROLE,
            context_framing=DEFAULT_JOINT_ACTIVITIES_FRAMING,
            instructions=DEFAULT_JOINT_ACTIVITIES_INSTRUCTIONS,
        )
    )


def build_prompt(
    step: StepPrompt,
    context: dict[str, str],
    data_block: str,
) -> str:
    """Assemble a final prompt from sections + runtime data.

    Args:
        step: The three configurable text sections.
        context: Placeholder values (e.g. ``agent_name``).
            Uses :meth:`str.format_map` with
            :class:`~collections.defaultdict` fallback so
            unknown keys are left as-is.
        data_block: Runtime data assembled by the calling
            method (demographics, candidates, travel times,
            etc.).

    Returns:
        The assembled prompt string.
    """

    class _Safe(dict):  # type: ignore[type-arg]
        """Return the key itself for missing placeholders."""

        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    safe = _Safe(context)
    role = step.role.format_map(safe)
    framing = step.context_framing.format_map(safe)
    instructions = step.instructions.format_map(safe)
    return f"{role}\n{framing}\n{data_block}\n\n{instructions}"


def load_prompt_config(cfg: dict) -> PromptConfig:  # type: ignore[type-arg]
    """Build a :class:`PromptConfig` from config YAML.

    *cfg* is the ``simulation.prompts`` dict. For each step
    key present, only the sections that appear are overridden;
    missing sections keep their defaults.

    Args:
        cfg: Mapping of step name to section overrides.

    Returns:
        A fully populated :class:`PromptConfig`.
    """
    pc = PromptConfig()
    for step_name, overrides in cfg.items():
        if not hasattr(pc, step_name):
            continue
        step: StepPrompt = getattr(pc, step_name)
        if "role" in overrides:
            step.role = overrides["role"]
        if "context_framing" in overrides:
            step.context_framing = overrides["context_framing"]
        if "instructions" in overrides:
            step.instructions = overrides["instructions"]
    return pc
