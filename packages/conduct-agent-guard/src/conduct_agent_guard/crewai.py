"""CrewAI: global ``before_tool_call`` hook.

    register_conduct_hook()   # once, before crew.kickoff()
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from crewai.hooks import register_before_tool_call_hook

from conduct_agent_guard.core import ToolGuard

log = logging.getLogger(__name__)


def register_conduct_hook(guard: ToolGuard | None = None) -> Callable[[Any], bool | None]:
    """Register a hook that checks every tool call. Returns it for ``unregister_...``."""
    guard = guard or ToolGuard(surface="crewai")

    def conduct_before_tool_call(context: Any) -> bool | None:
        verdict = guard.check_sync(context.tool_name, context.tool_input)
        if verdict.blocked:
            log.warning("Conduct blocked %s: %s", context.tool_name, verdict.reason)
            return False  # CrewAI contract: False skips the tool.
        return None

    register_before_tool_call_hook(conduct_before_tool_call)
    return conduct_before_tool_call
