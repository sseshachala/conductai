"""Anthropic adapter caches the tool catalogue when cache_tools=True.

Locks the invariant: with a non-empty tools list and cache_tools=True, the
LAST tool in the array carries `cache_control: {"type": "ephemeral"}`, which
tells Anthropic to cache the entire request prefix (system prompt + all
tools). This is the biggest win for Lens — ~10 KB of tool schemas paid
~90% less on cache hit within the 5-minute TTL.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _fake_response():
    """Minimal Anthropic response object shape the adapter expects."""
    r = MagicMock()
    r.content = []
    r.stop_reason = "end_turn"
    r.usage = MagicMock(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    r.model = "claude-test"
    return r


def _build_client_with_mock_sdk():
    """Instantiate AnthropicClient with a mocked SDK — skip __init__ so no
    real Anthropic client is created (would need a live API key)."""
    # Import via llm_client (parent) to avoid the adapter's circular import
    # chain when adapter is imported first.
    from app.runtime.llm_client import AnthropicClient
    client = AnthropicClient.__new__(AnthropicClient)  # skip __init__
    client._client = MagicMock()
    client._client.messages.create.return_value = _fake_response()
    client._pricing_snapshot = {}
    client._provider = "anthropic"
    return client


_TOOLS = [
    {"name": "get_a", "description": "A", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_b", "description": "B", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_c", "description": "C", "input_schema": {"type": "object", "properties": {}}},
]


def _captured_kwargs(cache_tools: bool, tools=_TOOLS) -> dict:
    client = _build_client_with_mock_sdk()
    client.create(
        model="claude-test",
        messages=[{"role": "user", "content": "hi"}],
        system="you are a helper",
        tools=tools,
        cache_tools=cache_tools,
    )
    assert client._client.messages.create.called
    return client._client.messages.create.call_args.kwargs


def test_cache_tools_true_marks_last_tool():
    kwargs = _captured_kwargs(cache_tools=True)
    tools_out = kwargs["tools"]
    assert len(tools_out) == 3
    # Only the LAST tool carries the marker — one marker caches the whole prefix
    assert "cache_control" not in tools_out[0]
    assert "cache_control" not in tools_out[1]
    assert tools_out[-1]["cache_control"] == {"type": "ephemeral"}


def test_cache_tools_true_does_not_mutate_input():
    """The caller's tool list must not be mutated in place."""
    tools_input = [dict(t) for t in _TOOLS]
    client = _build_client_with_mock_sdk()
    client.create(
        model="claude-test",
        messages=[{"role": "user", "content": "hi"}],
        system="s",
        tools=tools_input,
        cache_tools=True,
    )
    for t in tools_input:
        assert "cache_control" not in t, "adapter mutated caller's tool list"


def test_cache_tools_false_leaves_tools_untouched():
    kwargs = _captured_kwargs(cache_tools=False)
    tools_out = kwargs["tools"]
    for t in tools_out:
        assert "cache_control" not in t


def test_cache_tools_true_sets_anthropic_beta_header():
    kwargs = _captured_kwargs(cache_tools=True)
    headers = kwargs.get("extra_headers") or {}
    assert headers.get("anthropic-beta") == "prompt-caching-2024-07-31"


def test_no_tools_no_crash():
    """cache_tools=True with tools=None is a no-op."""
    client = _build_client_with_mock_sdk()
    client.create(
        model="claude-test",
        messages=[{"role": "user", "content": "hi"}],
        system="s",
        tools=None,
        cache_tools=True,
    )
    kwargs = client._client.messages.create.call_args.kwargs
    assert "tools" not in kwargs
