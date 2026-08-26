"""ToolRegistry — single source of truth for every registered tool.

Adapters (mcp.http / mcp.stdio / lens_executor) read from the registry and
project onto their transport. Adding a tool = one register() call. It
appears on every adapter automatically.
"""
from __future__ import annotations

import structlog
from typing import Any, Iterable

from app.tools.types import ToolDef

log = structlog.get_logger(__name__)


class ToolRegistryError(Exception):
    """Raised on registration or lookup failure."""


class ToolRegistry:
    """In-memory map of tool name → ToolDef. Idempotent for register().

    Registration order is preserved for tools/list responses (stable ordering
    downstream).
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef, *, replace: bool = False) -> ToolDef:
        """Register a tool. If a tool with the same name is already
        registered, raise ToolRegistryError — unless replace=True.
        """
        if tool.name in self._tools and not replace:
            existing = self._tools[tool.name]
            if existing is tool:
                return tool
            raise ToolRegistryError(
                f"Tool {tool.name!r} already registered (existing description: "
                f"{existing.description[:60]!r})"
            )
        self._tools[tool.name] = tool
        return tool

    def unregister(self, name: str) -> bool:
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolDef:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolRegistryError(f"Unknown tool {name!r}")
        return tool

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def list(self, *, tag: str | None = None) -> list[ToolDef]:
        """List registered tools, optionally filtered by tag.

        Order matches registration order — MCP tools/list responses stay stable.
        """
        if tag is None:
            return list(self._tools.values())
        return [t for t in self._tools.values() if tag in t.tags]

    def count(self) -> int:
        return len(self._tools)

    def register_all(self, tools: Iterable[ToolDef], *, replace: bool = False) -> None:
        for t in tools:
            self.register(t, replace=replace)

    def as_mcp_tools_list(self) -> list[dict[str, Any]]:
        """Project registered tools onto the MCP JSON-RPC tools/list response
        shape (name / description / inputSchema + annotations)."""
        out: list[dict[str, Any]] = []
        for t in self._tools.values():
            entry: dict[str, Any] = {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
            }
            # MCP 2026-07-28 tool annotations
            entry["annotations"] = {
                "readOnly": t.annotations.read_only,
                "idempotent": t.annotations.idempotent,
                "destructive": t.annotations.destructive,
                "openWorld": t.annotations.open_world,
            }
            out.append(entry)
        return out


# Module-level default registry — adapters read from this by default. Tests
# construct their own ToolRegistry() for isolation.
default_registry = ToolRegistry()
