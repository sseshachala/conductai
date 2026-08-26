"""Shared types for the tool registry.

Every tool exposed to any client (HTTP MCP, stdio MCP, Lens chat) is
described by one ToolDef. Adapters (mcp.http / mcp.stdio / lens_executor)
project the registry onto their transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class ToolAnnotations:
    """MCP 2026-07-28 spec tool annotations.

    Each tool declares its side-effect profile. Callers (and reasoning
    models) use these to decide when to invoke the tool and how to render
    its results.
    """
    read_only: bool = False       # Does not modify workspace state
    idempotent: bool = False      # Safe to call more than once with same args
    destructive: bool = False     # Deletes or overwrites data
    open_world: bool = False      # Calls out to external systems


@dataclass
class ToolDef:
    """One tool, one shape.

    The impl is a plain Python callable; adapters wrap it into their
    transport (JSON-RPC handler / async stream / in-process dispatch).
    """
    name: str
    description: str
    input_schema: dict[str, Any]                 # JSON Schema for arguments
    impl: Callable[..., Any]                     # Actual function
    permission: str | None = None                # RBAC permission required
    annotations: ToolAnnotations = field(default_factory=ToolAnnotations)
    tags: tuple[str, ...] = field(default_factory=tuple)


class ToolContext(Protocol):
    """What every tool call has access to at runtime.

    Adapters supply this from their transport (HTTP request → HttpContext,
    stdio client → StdioContext, Lens dispatch → LensContext). Tools should
    only read from ctx; never mutate it.
    """
    @property
    def workspace_id(self) -> str: ...

    @property
    def clerk_user_id(self) -> str | None: ...
