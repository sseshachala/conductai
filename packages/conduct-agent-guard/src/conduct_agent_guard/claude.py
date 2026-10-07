"""Claude Agent SDK: ``PreToolUse`` hook.

    options = ClaudeAgentOptions(hooks=conduct_hooks())
"""
from __future__ import annotations

from typing import Any

from claude_agent_sdk import HookMatcher

from conduct_agent_guard.core import ToolGuard


def conduct_hooks(guard: ToolGuard | None = None) -> dict[str, list[HookMatcher]]:
    """Hooks dict for ``ClaudeAgentOptions(hooks=...)``. Checks every tool call."""
    guard = guard or ToolGuard(surface="claude-agent-sdk")

    async def pre_tool_use(input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        verdict = await guard.check(
            input_data["tool_name"], input_data.get("tool_input"), input_data.get("session_id")
        )
        if not verdict.blocked:
            return {}
        # "deny", not "ask": approvals are decided in Conduct, not by a local prompt.
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": verdict.reason,
            }
        }

    return {"PreToolUse": [HookMatcher(hooks=[pre_tool_use])]}
