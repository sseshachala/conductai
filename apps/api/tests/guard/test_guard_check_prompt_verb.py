"""guard_check_prompt MCP verb — proxy-persona / prompt-gate variant.

Fixes silent pass-through where the LiteLLM plugin's traffic hit the
action-gate guard_check verb and never saw proxy-persona rules like
`no-conduct-tokens` / `proxy-no-credential-leak`. Per Guard architecture
§8, MCP is transport; the proxy PEP declares {prompt, response} — this
verb is the MCP-transport entry into that PEP.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.modules.guard.mcp_impls import GuardCtx, guard_check_prompt_impl


WS_UUID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def _ctx() -> GuardCtx:
    return GuardCtx(
        db=MagicMock(),
        ws_uuid=WS_UUID,
        workspace_id=str(WS_UUID),
        resolved_token="cond_agt_test",
        clerk_user_id="clerk-abc",
        user_email="sudhi@example.com",
        ai_tool="litellm",
        session_id="test-session-1",
    )


def test_missing_prompt_returns_error():
    result = guard_check_prompt_impl(_ctx())
    assert result.startswith("ERROR")
    assert "prompt" in result


def test_forwards_proxy_persona_prompt_gate_and_proxy_source():
    """The wrapper must call guard_check_impl with the persona/gate/source
    overrides that route to the proxy PEP path."""
    captured: dict = {}

    def _fake_impl(ctx, **kwargs):
        captured["kwargs"] = kwargs
        return "ok"

    with patch("app.modules.guard.mcp_impls.guard_check_impl", side_effect=_fake_impl):
        result = guard_check_prompt_impl(
            _ctx(),
            prompt="hello, world",
            model="claude-3-5-sonnet",
            provider="anthropic",
        )

    assert result == "ok"
    kw = captured["kwargs"]
    assert kw["_persona"] == "proxy"
    assert kw["_gate"] == "prompt"
    assert kw["_source"] == "proxy"
    # The wrapper packs prompt/model/provider into tool_input so downstream
    # regex matchers see them; also passes prompt at the top level so the
    # audit trail has the raw text (redacted at record time).
    assert kw["tool_name"] == "llm_call"
    assert kw["tool_input"]["prompt"] == "hello, world"
    assert kw["tool_input"]["model"] == "claude-3-5-sonnet"
    assert kw["tool_input"]["provider"] == "anthropic"
    assert kw["prompt"] == "hello, world"


def test_omits_optional_fields_when_not_supplied():
    captured: dict = {}

    def _fake_impl(ctx, **kwargs):
        captured["kwargs"] = kwargs
        return "ok"

    with patch("app.modules.guard.mcp_impls.guard_check_impl", side_effect=_fake_impl):
        guard_check_prompt_impl(_ctx(), prompt="hello")

    ti = captured["kwargs"]["tool_input"]
    assert ti == {"prompt": "hello"}  # no model / provider keys


def test_end_to_end_block_on_credential_prompt():
    """Proxy-rule matching a credential pattern must BLOCK when invoked via
    the prompt-gate verb. This is the exact case the LiteLLM plugin was
    silently missing before this change."""
    proxy_rule = {
        "rule_id": "test-no-fake-key",
        "match_pattern": r"sk_live_[0-9a-zA-Z]{20,}",
        "action": "block",
        "message": "Credential detected in prompt.",
        "gates": ["prompt"],
    }
    with patch("app.modules.guard.mcp_impls._get_rules", return_value=[proxy_rule]), \
         patch("app.modules.guard.mcp_impls._record_event") as rec, \
         patch("app.modules.guard.mcp_impls.GuardConfig"):
        # Ensure the GuardConfig query returns None (no advisory mode).
        _ctx_obj = _ctx()
        _ctx_obj.db.query.return_value.filter.return_value.first.return_value = None

        result = guard_check_prompt_impl(
            _ctx_obj,
            prompt="my token is sk_live_abcdef0123456789abcdef",
            model="claude-3-5-sonnet",
            provider="anthropic",
        )

    assert result.startswith("BLOCKED"), result
    assert "test-no-fake-key" in result
    # Audit row landed with source="proxy" (not "mcp") so Guard Activity
    # attributes to the correct surface. _record_event positional layout:
    # (db, ws_uuid, tool_name, tool_input, decision, rule_id, ai_tool, ...)
    assert rec.called
    args = rec.call_args.args
    assert args[4] == "blocked"
    assert args[5] == "test-no-fake-key"
    assert rec.call_args.kwargs.get("source") == "proxy"


def test_end_to_end_allow_when_no_rule_matches():
    """No proxy rule matches → returns 'ok' + writes an allowed receipt."""
    with patch("app.modules.guard.mcp_impls._get_rules", return_value=[]), \
         patch("app.modules.guard.mcp_impls._record_event") as rec:
        _ctx_obj = _ctx()
        _ctx_obj.db.query.return_value.filter.return_value.first.return_value = None
        result = guard_check_prompt_impl(_ctx_obj, prompt="hello, nothing suspicious")
    assert result == "ok"
    assert rec.call_args.args[4] == "allowed"
    assert rec.call_args.args[5] is None
    assert rec.call_args.kwargs.get("source") == "proxy"


def test_get_rules_pulls_proxy_persona():
    """Sanity check: _get_rules must accept and forward the persona arg."""
    from app.modules.guard.routers.mcp import _get_rules

    with patch("app.modules.guard.routers.mcp.compute_policy") as cp:
        cp.return_value = [{"id": "r1", "persona": "proxy"}]
        _get_rules(db=MagicMock(), ws_uuid=WS_UUID, persona="proxy")

    assert cp.call_args.args[2] == "proxy"
