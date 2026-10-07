"""Claude Agent SDK + Conduct. Needs ANTHROPIC_API_KEY and CONDUCT_AGENT_TOKEN.

    pip install "conduct-agent-guard[claude]"
    python examples/claude_agent_sdk_example.py
"""
import asyncio
from typing import Any

from _demo import MODEL, PROMPT, SYSTEM, memory_save, search_web
from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool

from conduct_agent_guard.claude import conduct_hooks


@tool("search_web", "Search the web and return the top result.", {"query": str})
async def _search(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": search_web(args["query"])}]}


@tool("memory_save", "Save text to memory.", {"text": str, "scope": str, "source": str})
async def _save(args: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": memory_save(**args)}]}


async def main() -> None:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        model=MODEL,
        mcp_servers={"demo": create_sdk_mcp_server("demo", tools=[_search, _save])},
        allowed_tools=["mcp__demo__search_web", "mcp__demo__memory_save"],
        hooks=conduct_hooks(),  # ← the only Conduct line
        max_turns=6,
    )
    async for message in query(prompt=PROMPT, options=options):
        if type(message).__name__ == "ResultMessage":
            print(message.result)


asyncio.run(main())
