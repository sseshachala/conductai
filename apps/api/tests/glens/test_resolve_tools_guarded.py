"""#1254 — _resolve_tools uses the in-process Guard gateway.

Verifies `_guarded_openai_completion` builds the correct OpenAI-shape
payload, awaits `guarded_llm_call`, and adapts the JSON response back to
an LLMResponse the loop can iterate on.

Mocks `guarded_llm_call` — no live LLM, no policy engine, no DB.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _fake_executor():
    ex = MagicMock()
    ex.workspace_id = "00000000-0000-0000-0000-000000000001"
    ex.db = None
    return ex


def test_openai_shape_payload_is_built_from_messages_system_tools():
    """The payload handed to guarded_llm_call must match what OpenAI's
    /v1/chat/completions expects — same shape OpenAIClient.create builds."""
    from app.modules.glens.routers.chat import _guarded_openai_completion

    captured: dict = {}

    async def _fake_guarded(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }

    tools = [
        {"name": "get_event_count", "description": "count", "input_schema": {"type": "object", "properties": {}}},
    ]
    with patch("app.guard.gateway.guarded_llm_call", side_effect=_fake_guarded):
        resp = _guarded_openai_completion(
            _fake_executor(), "openai", "gpt-4o-mini",
            "https://api.openai.com", "sk-test",
            messages=[{"role": "user", "content": "hi"}],
            system="sys-prompt", tools=tools, max_tokens=512,
        )

    body = captured["body"]
    assert body["model"] == "gpt-4o-mini"
    assert body["max_tokens"] == 512
    assert body["messages"][0] == {"role": "system", "content": "sys-prompt"}
    assert body["messages"][1] == {"role": "user", "content": "hi"}
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "get_event_count"
    assert captured["ai_tool"] == "lens"
    assert captured["upstream_path"] == "/v1/chat/completions"
    assert captured["upstream_url"] == "https://api.openai.com"

    # Response was adapted into LLMResponse
    assert resp.stop_reason == "end_turn"
    assert resp.content[0].text == "ok"
    assert resp.usage.input_tokens == 10 and resp.usage.output_tokens == 3


def test_tool_calls_are_parsed_into_toolusablock():
    from app.modules.glens.routers.chat import _guarded_openai_completion
    from app.runtime.llm_client import LLMToolUseBlock

    async def _fake_guarded(**kwargs):
        return {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {
                            "name": "get_event_count",
                            "arguments": '{"decision": "blocked"}',
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

    with patch("app.guard.gateway.guarded_llm_call", side_effect=_fake_guarded):
        resp = _guarded_openai_completion(
            _fake_executor(), "openai", "gpt-4o-mini",
            "https://api.openai.com", "sk-test",
            messages=[{"role": "user", "content": "how many blocks?"}],
            system="s", tools=[], max_tokens=512,
        )

    assert resp.stop_reason == "tool_use"
    blocks = [b for b in resp.content if isinstance(b, LLMToolUseBlock)]
    assert len(blocks) == 1
    assert blocks[0].name == "get_event_count"
    assert blocks[0].input == {"decision": "blocked"}
    assert blocks[0].id == "call_1"


def test_blocked_call_raises_with_readable_message():
    from app.modules.glens.routers.chat import _guarded_openai_completion
    from app.guard.gateway import GuardedLLMBlocked

    async def _fake_blocked(**kwargs):
        raise GuardedLLMBlocked(status=403, detail="Blocked by Guard rule R-42", payload={})

    import pytest
    with patch("app.guard.gateway.guarded_llm_call", side_effect=_fake_blocked):
        with pytest.raises(Exception, match="Guard blocked Lens call: Blocked by Guard rule R-42"):
            _guarded_openai_completion(
                _fake_executor(), "openai", "gpt-4o-mini",
                "https://api.openai.com", "sk-test",
                messages=[{"role": "user", "content": "hi"}],
                system="s", tools=[], max_tokens=512,
            )


def test_raw_content_populated_so_make_assistant_turn_emits_tool_calls():
    """#1342 regression — _guarded_openai_completion must populate _raw_content
    on the returned LLMResponse. Without it, OpenAIClient.make_assistant_turn
    reads an empty dict and emits an assistant message with no tool_calls —
    the next turn's role:tool messages then fail OpenAI's pairing check
    with a 400.
    """
    from app.modules.glens.routers.chat import _guarded_openai_completion
    from app.runtime.adapters.openai import OpenAIClient

    async def _fake_guarded(**kwargs):
        return {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_abc",
                        "function": {"name": "get_event_count", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }

    with patch("app.guard.gateway.guarded_llm_call", side_effect=_fake_guarded):
        resp = _guarded_openai_completion(
            _fake_executor(), "openai", "gpt-4o-mini",
            "https://api.openai.com", "sk-test",
            messages=[{"role": "user", "content": "hi"}],
            system="s", tools=[], max_tokens=512,
        )

    # _raw_content must be the raw provider message (not None, not empty)
    assert resp._raw_content is not None
    assert resp._raw_content.get("tool_calls"), "_raw_content missing tool_calls — pairing will break"

    # Round-trip through OpenAIClient.make_assistant_turn — the assistant
    # message MUST carry tool_calls so subsequent role:tool messages pair.
    client = OpenAIClient(api_key="sk-x")
    turn = client.make_assistant_turn(resp)
    assert turn[0]["role"] == "assistant"
    assert "tool_calls" in turn[0]
    assert turn[0]["tool_calls"][0]["id"] == "call_abc"


def test_upstream_error_is_distinct_from_guard_block():
    """#1342 — an OpenAI 400 must NOT be relabeled as 'Guard blocked'.
    LensUpstreamError is a separate exception class; the chat handler
    surfaces it with an upstream-error prefix, not the Guard-block prefix.
    """
    from app.modules.glens.routers.chat import _guarded_openai_completion
    from app.guard.gateway import LensUpstreamError

    async def _fake_upstream_err(**kwargs):
        raise LensUpstreamError(
            status=400,
            detail="Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool_calls'.",
            payload={"error": {"type": "invalid_request_error"}},
        )

    import pytest
    with patch("app.guard.gateway.guarded_llm_call", side_effect=_fake_upstream_err):
        with pytest.raises(Exception) as exc_info:
            _guarded_openai_completion(
                _fake_executor(), "openai", "gpt-4o-mini",
                "https://api.openai.com", "sk-test",
                messages=[{"role": "user", "content": "hi"}],
                system="s", tools=[], max_tokens=512,
            )
    msg = str(exc_info.value)
    assert "Guard blocked" not in msg, f"upstream error mislabeled as Guard block: {msg}"
    assert "upstream" in msg.lower()
    assert "400" in msg
