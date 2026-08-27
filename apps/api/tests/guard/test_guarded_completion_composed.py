"""#1254 — guarded_completion promoted to the composable engine.

Locks in the promotion so a future refactor can't silently regress
guarded_completion back to single-source _policy.evaluate.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse


def _fake_decision(action_name: str, rule_id: str | None = None):
    from app.guard.policy_types import PolicyAction
    return SimpleNamespace(
        action=PolicyAction[action_name],
        rule_id=rule_id,
        reason="fake reason" if rule_id else None,
        matched_rules=[{"id": rule_id}] if rule_id else [],
        defense_score=42,
        inject_guidance=False,
        guidance=None,
        source="test",
    )


def _run(coro):
    return asyncio.run(coro)


def test_guarded_completion_calls_evaluate_composed_not_legacy_evaluate():
    """The promotion — no direct calls to _policy.evaluate from guarded_completion."""
    from app.guard.gateway import guarded_completion

    async def _fake_upstream(**kwargs):
        return JSONResponse(status_code=200, content={"choices": []})

    with patch("app.guard.gateway._evaluate_composed",
               return_value=_fake_decision("ALLOW")) as composed_mock, \
         patch("app.guard.policy.evaluate") as legacy_mock, \
         patch("app.guard.router.upstream", side_effect=_fake_upstream):
        _run(guarded_completion(
            workspace_id="00000000-0000-0000-0000-000000000001",
            clerk_user_id="", ai_tool="lens",
            provider="openai", model="gpt-4o-mini",
            body={"model": "gpt-4o-mini", "messages": []},
            upstream_url="https://api.openai.com",
            upstream_path="/v1/chat/completions",
            real_key="sk-test",
            auth_header_out="Authorization",
            bearer=True, is_stream=False,
            background=BackgroundTasks(),
        ))

    composed_mock.assert_called_once()
    # RulePolicySource may still be called via composed → that's fine, but the
    # OUTER dispatch must go through the composed engine, not the raw legacy fn.
    call_stack_legacy = legacy_mock.call_count
    assert call_stack_legacy == 0, (
        "guarded_completion should route through evaluate_composed, "
        f"not call _policy.evaluate directly ({call_stack_legacy} direct calls)"
    )


def test_composed_block_still_short_circuits_and_returns_403():
    """Verify BLOCK path from the composed engine is honored the same way."""
    from app.guard.gateway import guarded_completion

    with patch("app.guard.gateway._evaluate_composed",
               return_value=_fake_decision("BLOCK", rule_id="R-blocked")), \
         patch("app.guard.router.upstream") as upstream_mock:
        resp = _run(guarded_completion(
            workspace_id="00000000-0000-0000-0000-000000000001",
            clerk_user_id="", ai_tool="lens",
            provider="openai", model="gpt-4o-mini",
            body={"model": "gpt-4o-mini", "messages": []},
            upstream_url="https://api.openai.com",
            upstream_path="/v1/chat/completions",
            real_key="sk-test",
            auth_header_out="Authorization",
            bearer=True, is_stream=False,
            background=BackgroundTasks(),
        ))

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 403
    upstream_mock.assert_not_called()  # BLOCK must not touch the upstream
