"""LangChain / LangGraph (``create_agent``): tool-call middleware.

    agent = create_agent(model, tools, middleware=[ConductMiddleware()])
"""
from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from conduct_agent_guard.core import ToolGuard, ToolVerdict


class ConductMiddleware(AgentMiddleware):
    """Checks every tool call; a block becomes an error ``ToolMessage``."""

    def __init__(self, guard: ToolGuard | None = None) -> None:
        super().__init__()
        self.guard = guard or ToolGuard(surface="langchain")

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        call = request.tool_call
        verdict = self.guard.check_sync(call["name"], call.get("args"))
        return _blocked(call, verdict) if verdict.blocked else handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        call = request.tool_call
        verdict = await self.guard.check(call["name"], call.get("args"))
        return _blocked(call, verdict) if verdict.blocked else await handler(request)


def _blocked(call: dict[str, Any], verdict: ToolVerdict) -> ToolMessage:
    return ToolMessage(
        content=verdict.reason, tool_call_id=call["id"], name=call["name"], status="error"
    )
