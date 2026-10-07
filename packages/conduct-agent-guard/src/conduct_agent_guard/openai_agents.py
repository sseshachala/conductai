"""OpenAI Agents SDK: tool input guardrail.

    agent = Agent(..., tools=guard_tools([lookup, delete_repo]))
"""
from __future__ import annotations

import json
from typing import Any

from agents import (
    FunctionTool,
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
    tool_input_guardrail,
)

from conduct_agent_guard.core import ToolGuard


def conduct_tool_guardrail(guard: ToolGuard | None = None) -> ToolInputGuardrail[Any]:
    """A guardrail to put in ``function_tool(tool_input_guardrails=[...])``."""
    guard = guard or ToolGuard(surface="openai-agents")

    @tool_input_guardrail(name="conduct_guard")
    async def _conduct(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        ctx = data.context
        try:
            args = json.loads(ctx.tool_arguments or "{}")
        except ValueError:
            args = ctx.tool_arguments
        verdict = await guard.check(ctx.tool_name, args)
        info = {"verdict": verdict.decision.verdict, "rule_id": verdict.decision.rule_id}
        if verdict.blocked:
            # The model gets the reason instead of the tool result and can adapt.
            return ToolGuardrailFunctionOutput.reject_content(verdict.reason, output_info=info)
        return ToolGuardrailFunctionOutput.allow(output_info=info)

    return _conduct


def guard_tools(tools: list[Any], guard: ToolGuard | None = None) -> list[Any]:
    """Attach the Conduct guardrail to every function tool. Returns the same list.

    Tool guardrails are per function tool in this SDK; hosted tools are not covered.
    """
    guardrail = conduct_tool_guardrail(guard)
    for tool in tools:
        if isinstance(tool, FunctionTool):
            tool.tool_input_guardrails = [*(tool.tool_input_guardrails or []), guardrail]
    return tools
