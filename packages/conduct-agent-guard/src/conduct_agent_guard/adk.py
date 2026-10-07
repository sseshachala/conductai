"""Google ADK: ``before_tool_callback``.

    agent = LlmAgent(..., before_tool_callback=conduct_before_tool_callback())
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from conduct_agent_guard.core import ToolGuard


def conduct_before_tool_callback(
    guard: ToolGuard | None = None,
) -> Callable[[Any, dict[str, Any], Any], Awaitable[dict[str, Any] | None]]:
    """Returning a dict skips the tool and hands the dict to the model as its result."""
    guard = guard or ToolGuard(surface="google-adk")

    async def before_tool(tool: Any, args: dict[str, Any], tool_context: Any) -> dict[str, Any] | None:
        verdict = await guard.check(tool.name, args)
        if verdict.blocked:
            return {"error": verdict.reason, "blocked_by": "conduct_guard"}
        return None

    return before_tool
