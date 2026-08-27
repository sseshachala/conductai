"""Lens Phase 1 (`_guarded_openai_completion`) now routes through LLMClient.

Verifies:
- Delegates to `guarded_client_call` with the caller's messages/system/tools
- `GuardedLLMBlocked` from the helper is surfaced as a clean "Guard blocked
  Lens call" exception the outer stream handler can render
- agent_identity_id is threaded through so audit rows attribute correctly

Mocks `guarded_client_call` — no live LLM, no policy engine, no DB.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

# Import llm_client first so its re-exports run before adapter loads.
import app.runtime.llm_client  # noqa: F401


def _fake_executor():
    ex = MagicMock()
    ex.workspace_id = "00000000-0000-0000-0000-000000000001"
    ex.db = None
    ex.agent_identity_id = None
    return ex


def test_delegates_to_guarded_client_call_with_caller_payload():
    from app.modules.glens.routers import chat as _chat

    captured: dict = {}
    fake_response = MagicMock()

    def _fake_call(**kwargs):
        captured.update(kwargs)
        return fake_response

    with patch.object(_chat, "_llm_client", return_value=MagicMock()), \
         patch("app.guard.gateway.guarded_client_call", side_effect=_fake_call):
        client = MagicMock()
        result = _chat._guarded_openai_completion(
            _fake_executor(),
            provider="openai", model="gpt-4o-mini",
            upstream_url="ignored", api_key="ignored",
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful.",
            tools=[{"name": "get_x", "input_schema": {"type": "object", "properties": {}}}],
            max_tokens=512,
            client=client,
        )

    assert result is fake_response
    assert captured["client"] is client
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["system"] == "You are helpful."
    assert captured["ai_tool"] == "lens"
    assert captured["clerk_user_id"] == "system:lens"


def test_blocked_call_raises_with_readable_message():
    from app.modules.glens.routers import chat as _chat
    from app.guard.gateway import GuardedLLMBlocked

    def _fake_call(**_):
        raise GuardedLLMBlocked(
            status=403,
            detail="Blocked by Guard rule no-env-read: env access prohibited",
            payload={},
        )

    with patch.object(_chat, "_llm_client", return_value=MagicMock()), \
         patch("app.guard.gateway.guarded_client_call", side_effect=_fake_call):
        try:
            _chat._guarded_openai_completion(
                _fake_executor(),
                provider="openai", model="gpt-4o-mini",
                upstream_url="ignored", api_key="ignored",
                messages=[], system="", tools=None, max_tokens=1,
                client=MagicMock(),
            )
        except Exception as e:
            msg = str(e)
            assert "Guard blocked Lens call" in msg
            assert "no-env-read" in msg
        else:
            raise AssertionError("expected an exception")


def test_agent_identity_id_threaded_through():
    from app.modules.glens.routers import chat as _chat

    captured: dict = {}
    with patch.object(_chat, "_llm_client", return_value=MagicMock()), \
         patch("app.guard.gateway.guarded_client_call",
               side_effect=lambda **kw: (captured.update(kw), MagicMock())[1]):
        ex = _fake_executor()
        ex.agent_identity_id = "ai-42"
        _chat._guarded_openai_completion(
            ex, provider="openai", model="gpt-4o-mini",
            upstream_url="ignored", api_key="ignored",
            messages=[], system="", tools=None, max_tokens=1,
            client=MagicMock(),
        )

    assert captured["agent_identity_id"] == "ai-42"
