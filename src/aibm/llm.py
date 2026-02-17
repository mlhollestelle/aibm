"""LLM client abstraction supporting multiple providers."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol


class LLMClient(Protocol):
    """Interface for LLM provider clients.

    Any object with a ``generate_json`` method matching this
    signature can be used as an LLM client by
    :class:`~aibm.agent.Agent`.
    """

    def generate_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        """Send *prompt* and return raw JSON matching *schema*."""
        ...


def _strip_code_fences(text: str) -> str:
    """Remove optional markdown code fences wrapping JSON."""
    stripped = text.strip()
    match = re.match(
        r"^```(?:json)?\s*\n?(.*?)```$",
        stripped,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return stripped


class GeminiClient:
    """LLM client backed by Google Gemini.

    Args:
        client: An existing ``google.genai.Client``.  When *None*
            a new one is created (reads ``GEMINI_API_KEY`` from
            the environment).
    """

    def __init__(self, client: Any = None) -> None:
        if client is None:
            from google import genai

            client = genai.Client()
        self._client: Any = client

    def generate_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        from google.genai import types

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        if response.text is None:
            raise ValueError("LLM returned an empty response")
        return str(response.text)


class AnthropicClient:
    """LLM client backed by Anthropic Claude.

    Args:
        client: An existing ``anthropic.Anthropic`` instance.
            When *None* a new one is created (reads
            ``ANTHROPIC_API_KEY`` from the environment).
        max_tokens: Maximum tokens in the LLM response.
    """

    def __init__(
        self,
        client: Any = None,
        max_tokens: int = 1024,
    ) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client: Any = client
        self._max_tokens = max_tokens

    def generate_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        schema_text = json.dumps(schema, indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            "Respond with valid JSON matching this schema:\n"
            f"{schema_text}\n"
            "Output ONLY the JSON object, no other text."
        )
        response = self._client.messages.create(
            model=model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "user", "content": full_prompt},
            ],
        )
        text: str = response.content[0].text
        if not text:
            raise ValueError("LLM returned an empty response")
        return _strip_code_fences(text)


def create_client(model: str) -> LLMClient:
    """Pick the right LLM client based on the model name.

    Names starting with ``"claude"`` use :class:`AnthropicClient`;
    everything else defaults to :class:`GeminiClient`.
    """
    if model.startswith("claude"):
        return AnthropicClient()
    return GeminiClient()
