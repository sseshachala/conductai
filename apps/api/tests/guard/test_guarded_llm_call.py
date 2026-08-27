"""#1254 — in-process Lens sibling of guarded_completion.

Verifies `guarded_llm_call` composes the same primitives (policy + upstream
+ audit) as `guarded_completion`, but returns the raw upstream JSON dict
so in-process callers can parse it into their SDK shape.

No live provider, no DB — mocks `guarded_completion` and drives the
BackgroundTasks manually to prove the flow.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_allowed_call_returns_upstream_json_dict():
    from app.guard.gateway import guarded_llm_call

    upstream = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}

    async def _fake_completion(**kwargs):
        # Simulate the router's success return: JSONResponse with upstream JSON body.
        return JSONResponse(status_code=200, content=upstream)

    with patch("app.guard.gateway.guarded_completion", side_effect=_fake_completion):
        raw = _run(guarded_llm_call(
            workspace_id="00000000-0000-0000-0000-000000000001",
            provider="openai", model="gpt-4o-mini",
            body={"model": "gpt-4o-mini", "messages": [], "max_tokens": 512},
            upstream_url="https://api.openai.com",
            upstream_path="/v1/chat/completions",
            real_key="sk-test",
        ))

    assert raw == upstream


def test_blocked_call_raises_guarded_llm_blocked():
    from app.guard.gateway import guarded_llm_call, GuardedLLMBlocked

    async def _fake_completion(**kwargs):
        return JSONResponse(
            status_code=403,
            content={"detail": "Blocked by Guard rule R-42: policy violation"},
        )

    with patch("app.guard.gateway.guarded_completion", side_effect=_fake_completion):
        with pytest.raises(GuardedLLMBlocked) as excinfo:
            _run(guarded_llm_call(
                workspace_id="00000000-0000-0000-0000-000000000001",
                provider="openai", model="gpt-4o-mini",
                body={},
                upstream_url="https://api.openai.com",
                upstream_path="/v1/chat/completions",
                real_key="sk-test",
            ))

    assert excinfo.value.status == 403
    assert "R-42" in excinfo.value.detail


def test_scheduled_background_audit_tasks_are_awaited():
    """guarded_llm_call must drive `background()` — otherwise audit writes
    scheduled by _router.upstream never run in the in-process flow."""
    from app.guard.gateway import guarded_llm_call
    from fastapi import BackgroundTasks

    ran: list[str] = []

    async def _fake_audit():
        ran.append("audit-async")

    def _fake_audit_sync():
        ran.append("audit-sync")

    async def _fake_completion(**kwargs):
        bg: BackgroundTasks = kwargs["background"]
        bg.add_task(_fake_audit)
        bg.add_task(_fake_audit_sync)
        return JSONResponse(status_code=200, content={"choices": []})

    with patch("app.guard.gateway.guarded_completion", side_effect=_fake_completion):
        _run(guarded_llm_call(
            workspace_id="00000000-0000-0000-0000-000000000001",
            provider="openai", model="gpt-4o-mini",
            body={},
            upstream_url="https://api.openai.com",
            upstream_path="/v1/chat/completions",
            real_key="sk-test",
        ))

    assert ran == ["audit-async", "audit-sync"], f"background tasks not driven: {ran}"
