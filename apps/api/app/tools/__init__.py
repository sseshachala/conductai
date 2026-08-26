"""ToolRegistry — one source of truth for every tool exposed to any client.

See epic #1219 for design context. Two MCP surfaces + Lens Executor merge
into one registry; adapters project registered tools onto HTTP MCP,
stdio MCP, and in-process Lens dispatch.
"""
