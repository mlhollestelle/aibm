"""Tests for workflow/scripts/_config.py."""

from _config import _deep_merge


def test_deep_merge_simple_override():
    base = {"a": 1, "b": 2}
    override = {"b": 99, "c": 3}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": 99, "c": 3}


def test_deep_merge_nested():
    base = {"simulation": {"model": "gpt-4o-mini", "seed": 42}}
    override = {"simulation": {"model": "gpt-4o"}}
    result = _deep_merge(base, override)
    assert result == {"simulation": {"model": "gpt-4o", "seed": 42}}


def test_deep_merge_does_not_mutate_base():
    base = {"simulation": {"model": "gpt-4o-mini"}}
    override = {"simulation": {"model": "gpt-4o"}}
    _deep_merge(base, override)
    assert base["simulation"]["model"] == "gpt-4o-mini"


def test_deep_merge_empty_override():
    base = {"a": 1}
    result = _deep_merge(base, {})
    assert result == {"a": 1}


def test_deep_merge_deeply_nested():
    base = {"simulation": {"prompts": {"persona": {"role": "old"}}}}
    override = {"simulation": {"prompts": {"persona": {"role": "new"}}}}
    result = _deep_merge(base, override)
    assert result["simulation"]["prompts"]["persona"]["role"] == "new"
