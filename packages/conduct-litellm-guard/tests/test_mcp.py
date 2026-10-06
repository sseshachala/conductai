"""``pre_mcp_call`` — LiteLLM MCP tool calls route to the action gate."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from conduct_litellm_guard import ConductGuard
from conduct_litellm_guard.guardrail import ConductGuardBlocked


@pytest.fixture(autouse=True)
def _agent_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONDUCT_AGENT_TOKEN", "cond_agt_test_placeholder")


def _guard(prompt: str = "ok", action: str = "ok") -> ConductGuard:
    g = ConductGuard()
    g._client.guard_check = AsyncMock(return_value=prompt)
    g._client.guard_check_action = AsyncMock(return_value=action)
    return g


def _mcp_data() -> dict:
    # Shape of LiteLLM's synthetic pre_mcp_call payload (proxy/utils.py).
    return {
        "model": "mcp-tool-call",
        "messages": [{"role": "user", "content": "Tool: delete_repository\nArguments: {...}"}],
        "mcp_tool_name": "delete_repository",
        "mcp_arguments": {"repo": "acme/payments-service"},
    }


async def test_mcp_call_hits_action_gate_with_tool_and_args() -> None:
    g = _guard()
    await g.async_pre_call_hook(None, None, _mcp_data(), "call_mcp_tool")
    kwargs = g._client.guard_check_action.await_args.kwargs
    assert kwargs["tool_name"] == "delete_repository"
    assert kwargs["tool_input"] == {"repo": "acme/payments-service"}
    g._client.guard_check.assert_awaited_once()  # prompt rules still scan the args


async def test_action_block_blocks_even_when_prompt_allows() -> None:
    g = _guard(action="BLOCKED — repo deletion needs approval [rule: no-repo-delete]")
    with pytest.raises(ConductGuardBlocked) as exc:
        await g.async_pre_call_hook(None, None, _mcp_data(), "call_mcp_tool")
    assert exc.value.decision.rule_id == "no-repo-delete"


async def test_action_approval_blocks() -> None:
    g = _guard(action="PENDING approval — HITL required [rule: prod-gate]")
    with pytest.raises(ConductGuardBlocked):
        await g.async_pre_call_hook(None, None, _mcp_data(), "call_mcp_tool")


async def test_prompt_block_still_blocks_mcp_call() -> None:
    g = _guard(prompt="BLOCKED — credential in args [rule: proxy-no-credential-leak]")
    with pytest.raises(ConductGuardBlocked) as exc:
        await g.async_pre_call_hook(None, None, _mcp_data(), "call_mcp_tool")
    assert exc.value.decision.rule_id == "proxy-no-credential-leak"


async def test_llm_call_skips_action_gate() -> None:
    g = _guard()
    data = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    await g.async_pre_call_hook(None, None, data, "acompletion")
    g._client.guard_check_action.assert_not_awaited()


async def test_action_transport_error_fails_closed() -> None:
    g = _guard()
    g._client.guard_check_action = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(ConductGuardBlocked):
        await g.async_pre_call_hook(None, None, _mcp_data(), "call_mcp_tool")


async def test_non_dict_arguments_are_wrapped() -> None:
    g = _guard()
    data = {**_mcp_data(), "mcp_arguments": '{"repo": "x"}'}
    await g.async_pre_call_hook(None, None, data, "call_mcp_tool")
    assert g._client.guard_check_action.await_args.kwargs["tool_input"] == {"arguments": '{"repo": "x"}'}


async def test_upstream_unified_path_routes_via_check() -> None:
    """The in-tree LiteLLM wrapper calls ``check(data={**request_data, ...})``
    with ``call_type="request"`` — request_data still carries mcp_tool_name."""
    g = _guard(action="BLOCKED — no [rule: r1]")
    decision = await g.check(data={**_mcp_data(), "prompt": None}, call_type="request")
    assert decision.verdict == "block"
