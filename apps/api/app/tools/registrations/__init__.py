"""Per-surface tool registrations for the default ToolRegistry.

Importing this package fires each surface module's registrations as a side
effect — every tool ends up in `app.tools.registry.default_registry` before
the first MCP request. See epic #1219.

- lens: 21 Executor tools (Phase 3b Chunk A)
- guard: 17 MCP tools (Phase 3b Chunk B) — delegates to the same
  dispatch_guard_tool the legacy /guard/mcp endpoint calls, so byte-parity
  across surfaces is guaranteed by construction.
"""
from app.tools.registrations import guard, lens  # noqa: F401  # side-effect
