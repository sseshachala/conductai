"""Conduct Guard for agent SDKs.

Each SDK adapter lives in its own module so you only import (and install)
the framework you use:

    from conduct_agent_guard.claude import conduct_hooks              # Claude Agent SDK
    from conduct_agent_guard.openai_agents import guard_tools          # OpenAI Agents SDK
    from conduct_agent_guard.langchain import ConductMiddleware        # LangChain / LangGraph
    from conduct_agent_guard.adk import conduct_before_tool_callback   # Google ADK
    from conduct_agent_guard.crewai import register_conduct_hook       # CrewAI
"""
from conduct_agent_guard.core import ToolGuard, ToolVerdict

__version__ = "0.1.0"
__all__ = ["ToolGuard", "ToolVerdict", "__version__"]
