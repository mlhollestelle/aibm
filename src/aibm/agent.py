"""Agent — the basic unit of the simulation."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from google import genai
from google.genai import types


@dataclass
class ModeOption:
    """One row of mode-choice input data.

    Attributes:
        mode: Name of the travel mode (e.g. "car", "bike", "transit").
        travel_time: Travel time in minutes for this mode.
    """

    mode: str
    travel_time: float


@dataclass
class ModeChoice:
    """The result of an LLM-powered mode choice.

    Attributes:
        option: The chosen ModeOption.
        reasoning: A short story from the agent explaining the choice.
    """

    option: ModeOption
    reasoning: str


@dataclass
class Agent:
    """A single agent in the simulation.

    Attributes:
        name: Human-readable label.
        model: Gemini model used for decision-making.
        id: Unique identifier (auto-generated if not supplied).
    """

    name: str
    model: str = "gemini-2.5-flash-lite"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __repr__(self) -> str:
        return f"Agent(id={self.id!r}, name={self.name!r})"

    def choose_mode(
        self,
        options: list[ModeOption],
        client: genai.Client | None = None,
    ) -> ModeChoice:
        """Ask a Gemini LLM to pick a travel mode and explain the reasoning.

        The LLM receives the agent's name and each option with its travel time,
        then returns JSON with two fields:
        ``reasoning`` (a short personal story) and ``choice`` (the mode name).

        Args:
            options: Available modes with their travel times.
            client: A ``genai.Client`` instance. A fresh one is created when
                ``None`` is passed (reads ``GEMINI_API_KEY`` from the environment).

        Returns:
            A ``ModeChoice`` with the selected ``ModeOption`` and the reasoning.

        Raises:
            ValueError: If options is empty.
        """
        if not options:
            raise ValueError("options must contain at least one ModeOption")

        if client is None:
            client = genai.Client()

        options_text = "\n".join(
            f"- {opt.mode}: {opt.travel_time} minutes" for opt in options
        )
        prompt = (
            f"You are {self.name}, deciding how to travel today.\n"
            f"Available options:\n{options_text}\n\n"
            "Pick exactly one mode. Respond with:\n"
            '- "reasoning": a short personal story (2-3 sentences) explaining'
            " your choice.\n"
            '- "choice": the mode name exactly as listed above.'
        )

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "reasoning": {"type": "string"},
                        "choice": {"type": "string"},
                    },
                    "required": ["reasoning", "choice"],
                },
            ),
        )

        if response.text is None:
            raise ValueError("LLM returned an empty response")
        data = json.loads(response.text)
        chosen_name: str = data["choice"]
        chosen_option = next(opt for opt in options if opt.mode == chosen_name)
        return ModeChoice(option=chosen_option, reasoning=data["reasoning"])
