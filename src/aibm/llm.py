"""LLM client abstraction supporting multiple providers."""

from __future__ import annotations

import collections
import json
import re
import time
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


class RateLimiter:
    """Wrapper that throttles calls to an LLM client.

    Enforces a maximum number of ``generate_json`` calls within
    a rolling time window.  When the limit is reached the wrapper
    sleeps until room opens up.

    Args:
        client: The underlying :class:`LLMClient` to delegate to.
        max_calls: Maximum calls allowed in the window (default 50).
        window: Length of the rolling window in seconds (default 60).
    """

    def __init__(
        self,
        client: LLMClient,
        max_calls: int = 50,
        window: float = 60.0,
    ) -> None:
        self._client = client
        self._max_calls = max_calls
        self._window = window
        self._timestamps: collections.deque[float] = collections.deque()

    def generate_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        """Throttle then delegate to the wrapped client."""
        now = time.monotonic()

        # Drop timestamps outside the window
        while self._timestamps and now - self._timestamps[0] >= self._window:
            self._timestamps.popleft()

        # If at the limit, sleep until the oldest call expires
        if len(self._timestamps) >= self._max_calls:
            sleep_for = self._window - (now - self._timestamps[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._timestamps.popleft()

        self._timestamps.append(time.monotonic())
        return self._client.generate_json(model=model, prompt=prompt, schema=schema)


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


class OpenAIClient:
    """LLM client backed by OpenAI.

    Args:
        client: An existing ``openai.OpenAI`` instance.  When *None*
            a new one is created (reads ``OPENAI_API_KEY`` from
            the environment).
        max_tokens: Maximum tokens in the LLM response.
    """

    def __init__(
        self,
        client: Any = None,
        max_tokens: int = 1024,
    ) -> None:
        if client is None:
            import openai

            client = openai.OpenAI()
        self._client: Any = client
        self._max_tokens = max_tokens

    def generate_json(
        self,
        model: str,
        prompt: str,
        schema: dict[str, Any],
    ) -> str:
        response = self._client.chat.completions.create(
            model=model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": schema,
                    "strict": True,
                },
            },
        )
        text: str | None = response.choices[0].message.content
        if not text:
            raise ValueError("LLM returned an empty response")
        return text


def create_client(model: str) -> LLMClient:
    """Pick the right LLM client based on the model name.

    Names starting with ``"claude"`` use :class:`AnthropicClient`;
    names starting with ``"gpt-"``, ``"o1"``, or ``"o3"`` use
    :class:`OpenAIClient`; everything else defaults to
    :class:`GeminiClient`.
    """
    if model.startswith("claude"):
        return AnthropicClient()
    if model.startswith(("gpt-", "o1", "o3")):
        return OpenAIClient()
    return GeminiClient()
