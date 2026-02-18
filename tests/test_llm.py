"""Tests for the LLM client abstraction layer."""

from unittest.mock import MagicMock, patch

import pytest

from aibm.llm import (
    AnthropicClient,
    GeminiClient,
    OpenAIClient,
    RateLimiter,
    _strip_code_fences,
    create_client,
)

# --- _strip_code_fences ---


def test_strip_plain_json_unchanged() -> None:
    assert _strip_code_fences('{"a": 1}') == '{"a": 1}'


def test_strip_json_code_fence() -> None:
    text = '```json\n{"a": 1}\n```'
    assert _strip_code_fences(text) == '{"a": 1}'


def test_strip_plain_code_fence() -> None:
    text = '```\n{"a": 1}\n```'
    assert _strip_code_fences(text) == '{"a": 1}'


def test_strip_code_fence_with_whitespace() -> None:
    text = '  ```json\n{"a": 1}\n```  '
    assert _strip_code_fences(text) == '{"a": 1}'


# --- GeminiClient ---


def test_gemini_generate_json_returns_text() -> None:
    inner = MagicMock()
    inner.models.generate_content.return_value.text = '{"x": 1}'
    client = GeminiClient(client=inner)

    result = client.generate_json(
        model="gemini-2.5-flash-lite",
        prompt="hello",
        schema={"type": "object"},
    )

    assert result == '{"x": 1}'
    inner.models.generate_content.assert_called_once()


def test_gemini_raises_on_empty_response() -> None:
    inner = MagicMock()
    inner.models.generate_content.return_value.text = None
    client = GeminiClient(client=inner)

    with pytest.raises(ValueError, match="empty response"):
        client.generate_json(
            model="gemini-2.5-flash-lite",
            prompt="hello",
            schema={},
        )


# --- AnthropicClient ---


def test_anthropic_generate_json_returns_text() -> None:
    inner = MagicMock()
    inner.messages.create.return_value.content = [MagicMock(text='{"x": 1}')]
    client = AnthropicClient(client=inner)

    result = client.generate_json(
        model="claude-sonnet-4-20250514",
        prompt="hello",
        schema={"type": "object"},
    )

    assert result == '{"x": 1}'
    inner.messages.create.assert_called_once()


def test_anthropic_strips_code_fences() -> None:
    inner = MagicMock()
    inner.messages.create.return_value.content = [
        MagicMock(text='```json\n{"x": 1}\n```')
    ]
    client = AnthropicClient(client=inner)

    result = client.generate_json(
        model="claude-sonnet-4-20250514",
        prompt="hello",
        schema={},
    )

    assert result == '{"x": 1}'


def test_anthropic_raises_on_empty_response() -> None:
    inner = MagicMock()
    inner.messages.create.return_value.content = [MagicMock(text="")]
    client = AnthropicClient(client=inner)

    with pytest.raises(ValueError, match="empty response"):
        client.generate_json(
            model="claude-sonnet-4-20250514",
            prompt="hello",
            schema={},
        )


def test_anthropic_prompt_includes_schema() -> None:
    inner = MagicMock()
    inner.messages.create.return_value.content = [MagicMock(text='{"x": 1}')]
    client = AnthropicClient(client=inner)

    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    client.generate_json(
        model="claude-sonnet-4-20250514",
        prompt="hello",
        schema=schema,
    )

    call_args = inner.messages.create.call_args
    sent_prompt = call_args.kwargs["messages"][0]["content"]
    assert "hello" in sent_prompt
    assert '"type": "object"' in sent_prompt


# --- OpenAIClient ---


def test_openai_generate_json_returns_text() -> None:
    inner = MagicMock()
    msg = MagicMock()
    msg.content = '{"x": 1}'
    inner.chat.completions.create.return_value.choices = [MagicMock(message=msg)]
    client = OpenAIClient(client=inner)

    result = client.generate_json(
        model="gpt-4o",
        prompt="hello",
        schema={"type": "object"},
    )

    assert result == '{"x": 1}'
    inner.chat.completions.create.assert_called_once()


def test_openai_raises_on_empty_response() -> None:
    inner = MagicMock()
    msg = MagicMock()
    msg.content = None
    inner.chat.completions.create.return_value.choices = [MagicMock(message=msg)]
    client = OpenAIClient(client=inner)

    with pytest.raises(ValueError, match="empty response"):
        client.generate_json(model="gpt-4o", prompt="hello", schema={})


def test_openai_passes_schema_as_response_format() -> None:
    inner = MagicMock()
    msg = MagicMock()
    msg.content = '{"x": 1}'
    inner.chat.completions.create.return_value.choices = [MagicMock(message=msg)]
    client = OpenAIClient(client=inner)

    schema = {"type": "object", "properties": {"x": {"type": "number"}}}
    client.generate_json(model="gpt-4o", prompt="hello", schema=schema)

    call_kwargs = inner.chat.completions.create.call_args.kwargs
    rf = call_kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == schema
    assert rf["json_schema"]["strict"] is True


# --- create_client ---


def test_create_client_claude_returns_anthropic() -> None:
    with patch.object(AnthropicClient, "__init__", return_value=None):
        client = create_client("claude-sonnet-4-20250514")
    assert isinstance(client, AnthropicClient)


def test_create_client_gemini_returns_gemini() -> None:
    with patch.object(GeminiClient, "__init__", return_value=None):
        client = create_client("gemini-2.5-flash-lite")
    assert isinstance(client, GeminiClient)


def test_create_client_gpt_returns_openai() -> None:
    with patch.object(OpenAIClient, "__init__", return_value=None):
        client = create_client("gpt-4o")
    assert isinstance(client, OpenAIClient)


def test_create_client_o3_returns_openai() -> None:
    with patch.object(OpenAIClient, "__init__", return_value=None):
        client = create_client("o3-mini")
    assert isinstance(client, OpenAIClient)


# --- RateLimiter ---


def test_rate_limiter_delegates_to_inner_client() -> None:
    inner = MagicMock()
    inner.generate_json.return_value = '{"ok": true}'
    limiter = RateLimiter(inner, max_calls=10, window=60.0)

    result = limiter.generate_json(model="m", prompt="p", schema={"type": "object"})

    assert result == '{"ok": true}'
    inner.generate_json.assert_called_once_with(
        model="m", prompt="p", schema={"type": "object"}
    )


def test_rate_limiter_allows_calls_under_limit() -> None:
    inner = MagicMock()
    inner.generate_json.return_value = "{}"
    limiter = RateLimiter(inner, max_calls=5, window=60.0)

    for _ in range(5):
        limiter.generate_json(model="m", prompt="p", schema={})

    assert inner.generate_json.call_count == 5


@patch("aibm.llm.time.sleep")
@patch("aibm.llm.time.monotonic")
def test_rate_limiter_sleeps_when_limit_reached(
    mock_monotonic: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    inner = MagicMock()
    inner.generate_json.return_value = "{}"

    # 2-call limit, 10-second window
    limiter = RateLimiter(inner, max_calls=2, window=10.0)

    # First two calls at t=0 and t=1 — under the limit
    mock_monotonic.return_value = 0.0
    limiter.generate_json(model="m", prompt="p", schema={})
    mock_monotonic.return_value = 1.0
    limiter.generate_json(model="m", prompt="p", schema={})

    # Third call at t=2 — should sleep until t=10 (oldest + window)
    mock_monotonic.return_value = 2.0
    limiter.generate_json(model="m", prompt="p", schema={})

    mock_sleep.assert_called_once()
    sleep_seconds = mock_sleep.call_args[0][0]
    assert sleep_seconds == pytest.approx(8.0)


def test_rate_limiter_default_values() -> None:
    inner = MagicMock()
    limiter = RateLimiter(inner)
    assert limiter._max_calls == 50
    assert limiter._window == 60.0
