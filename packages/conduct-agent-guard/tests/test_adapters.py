"""Each adapter, driven through its SDK's real types. Conduct is stubbed.

Skips an adapter whose SDK isn't installed (``pip install -e '.[claude,openai,...]'``).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from conduct_agent_guard.core import ToolVerdict
from conduct_litellm_guard import GuardDecision


class FakeGuard:
    """Blocks any tool whose name starts with ``delete``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def _verdict(self, name: str, args: object) -> ToolVerdict:
        self.calls.append((name, args))
        blocked = name.startswith("delete")
        return ToolVerdict(
            blocked=blocked,
            reason="no deletes [rule: r1]" if blocked else "",
            decision=GuardDecision(verdict="block" if blocked else "allow", raw=""),
        )

    async def check(self, name, args, session_id=None):  # noqa: ANN001
        return self._verdict(name, args)

    def check_sync(self, name, args, session_id=None):  # noqa: ANN001
        return self._verdict(name, args)


# ── Claude Agent SDK ────────────────────────────────────────────────────


async def test_claude_hook_denies_and_allows() -> None:
    pytest.importorskip("claude_agent_sdk")
    from conduct_agent_guard.claude import conduct_hooks

    g = FakeGuard()
    hook = conduct_hooks(g)["PreToolUse"][0].hooks[0]
    denied = await hook({"tool_name": "delete_repo", "tool_input": {"r": 1}}, "id1", None)
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no deletes" in denied["hookSpecificOutput"]["permissionDecisionReason"]
    assert await hook({"tool_name": "Read", "tool_input": {}}, "id2", None) == {}
    assert g.calls[0] == ("delete_repo", {"r": 1})


# ── OpenAI Agents SDK ───────────────────────────────────────────────────


async def test_openai_guardrail_rejects_and_attaches() -> None:
    pytest.importorskip("agents")
    from agents import ToolInputGuardrailData, function_tool

    from conduct_agent_guard.openai_agents import conduct_tool_guardrail, guard_tools

    g = FakeGuard()
    guardrail = conduct_tool_guardrail(g)
    ctx = SimpleNamespace(tool_name="delete_repo", tool_arguments=json.dumps({"r": 1}))
    out = await guardrail.run(ToolInputGuardrailData(context=ctx, agent=None))
    assert out.behavior["type"] == "reject_content"
    assert g.calls[0] == ("delete_repo", {"r": 1})

    @function_tool
    def lookup(q: str) -> str:
        """Look something up."""
        return q

    (tool,) = guard_tools([lookup], g)
    assert len(tool.tool_input_guardrails) == 1


# ── LangChain ───────────────────────────────────────────────────────────


def _lc_request(name: str):  # noqa: ANN202
    return SimpleNamespace(tool_call={"name": name, "args": {"r": 1}, "id": "call_1"})


def test_langchain_sync_blocks_and_passes() -> None:
    pytest.importorskip("langchain")
    from conduct_agent_guard.langchain import ConductMiddleware

    m = ConductMiddleware(FakeGuard())
    blocked = m.wrap_tool_call(_lc_request("delete_repo"), lambda r: pytest.fail("ran tool"))
    assert blocked.status == "error" and "no deletes" in blocked.content
    assert m.wrap_tool_call(_lc_request("lookup"), lambda r: "ran") == "ran"


async def test_langchain_async_blocks() -> None:
    pytest.importorskip("langchain")
    from conduct_agent_guard.langchain import ConductMiddleware

    async def handler(r):  # noqa: ANN001, ANN202
        pytest.fail("ran tool")

    out = await ConductMiddleware(FakeGuard()).awrap_tool_call(_lc_request("delete_repo"), handler)
    assert out.tool_call_id == "call_1"


# ── Google ADK ──────────────────────────────────────────────────────────


async def test_adk_callback_replaces_result() -> None:
    pytest.importorskip("google.adk")
    from conduct_agent_guard.adk import conduct_before_tool_callback

    cb = conduct_before_tool_callback(FakeGuard())
    out = await cb(SimpleNamespace(name="delete_repo"), {"r": 1}, None)
    assert out["blocked_by"] == "conduct_guard"
    assert await cb(SimpleNamespace(name="lookup"), {}, None) is None


# ── CrewAI ──────────────────────────────────────────────────────────────


def test_crewai_hook_registers_and_blocks() -> None:
    pytest.importorskip("crewai")
    from crewai.hooks import get_before_tool_call_hooks, unregister_before_tool_call_hook

    from conduct_agent_guard.crewai import register_conduct_hook

    hook = register_conduct_hook(FakeGuard())
    try:
        assert hook in get_before_tool_call_hooks()
        assert hook(SimpleNamespace(tool_name="delete_repo", tool_input={})) is False
        assert hook(SimpleNamespace(tool_name="lookup", tool_input={})) is None
    finally:
        unregister_before_tool_call_hook(hook)
