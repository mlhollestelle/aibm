"""Tests for the LLM client abstraction layer."""

from unittest.mock import MagicMock, patch

import pytest

from aibm.llm import (
    AnthropicClient,
    GeminiClient,
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


# --- create_client ---


def test_create_client_claude_returns_anthropic() -> None:
    with patch.object(AnthropicClient, "__init__", return_value=None):
        client = create_client("claude-sonnet-4-20250514")
    assert isinstance(client, AnthropicClient)


def test_create_client_gemini_returns_gemini() -> None:
    with patch.object(GeminiClient, "__init__", return_value=None):
        client = create_client("gemini-2.5-flash-lite")
    assert isinstance(client, GeminiClient)
