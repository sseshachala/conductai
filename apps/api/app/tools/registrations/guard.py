"""Guard MCP tool registrations for the default ToolRegistry.

Reuses the exact schemas from `apps/api/app/modules/guard/routers/mcp._TOOLS`
and dispatches every call through `dispatch_guard_tool` — the same function
the legacy /guard/mcp endpoint calls after #1219 Phase 3b Chunk B1
extraction. Both surfaces run identical code paths — zero divergence risk.

Each impl opens its own SessionLocal (parallels the Lens registrations
pattern), builds a GuardCtx from MCPContext + a fresh session, dispatches,
closes. Enriched MCPContext fields (user_email, session_id, resolved_token)
must be populated by the adapter; the /mcp HTTP adapter does this in
mcp/http.py.

Adding a new guard tool: add the ToolDef schema to
routers/mcp._TOOLS + the branch to mcp_impls.dispatch_guard_tool.
This module re-projects both automatically — nothing to edit here.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from app.tools.registry import default_registry
from app.tools.types import ToolAnnotations, ToolDef


# Import the schema list once (module load) — cheap, no side effects.
from app.modules.guard.routers.mcp import _TOOLS as _GUARD_TOOL_SCHEMAS


_GUARD_TAGS = ("guard",)


# Per-tool annotations. Pure-read tools use read_only; the write tools
# (guard_activity, guard_check with side-effect recording, guard_enable,
# guard_discover_register, post_finding, trigger_fix, conduct_run_workflow)
# don't; guard_check + trigger_fix + post_finding + guard_discover_register
# + conduct_run_workflow are open_world (they mutate DB / enqueue runs).
_ANNOTATIONS: dict[str, ToolAnnotations] = {
    "guard_status":            ToolAnnotations(read_only=True),
    "guard_check":             ToolAnnotations(open_world=True),
    "guard_sync":              ToolAnnotations(read_only=True),
    "guard_enable":            ToolAnnotations(read_only=True),
    "guard_spend":             ToolAnnotations(read_only=True),
    "guard_local_risks":       ToolAnnotations(read_only=True),
    "guard_activity":          ToolAnnotations(open_world=True),
    "guard_recent_activity":   ToolAnnotations(read_only=True),
    "guard_discover":          ToolAnnotations(read_only=True),
    "guard_discover_register": ToolAnnotations(open_world=True, destructive=False),
    "post_finding":            ToolAnnotations(open_world=True),
    "trigger_fix":             ToolAnnotations(open_world=True, destructive=True),
    "conduct_list_agents":     ToolAnnotations(read_only=True),
    "conduct_list_projects":   ToolAnnotations(read_only=True),
    "conduct_list_playbooks":  ToolAnnotations(read_only=True),
    "conduct_run_workflow":    ToolAnnotations(open_world=True, destructive=True),
    "conduct_get_run":         ToolAnnotations(read_only=True),
}


def _build_gctx(ctx, db):
    """Construct a GuardCtx from MCPContext + a fresh session."""
    from app.modules.guard.mcp_impls import GuardCtx

    try:
        ws_uuid = uuid.UUID(ctx.workspace_id)
    except (ValueError, TypeError, AttributeError):
        # Registration-time impls should always receive a valid workspace
        # from the adapter; a bad one here means a bug — fail loudly.
        raise ValueError(f"MCPContext.workspace_id is not a UUID: {ctx.workspace_id!r}")

    return GuardCtx(
        db=db,
        ws_uuid=ws_uuid,
        workspace_id=str(ws_uuid),
        resolved_token=getattr(ctx, "resolved_token", "") or "",
        clerk_user_id=getattr(ctx, "clerk_user_id", None),
        user_email=getattr(ctx, "user_email", None),
        ai_tool=getattr(ctx, "surface", "http") or "http",
        session_id=getattr(ctx, "session_id", None) or "",
    )


def _impl(tool_name: str) -> Callable[..., Any]:
    """Build a ctx-accepting impl for one guard tool."""
    def _guard_impl(ctx, **kwargs):
        from app.core.database import SessionLocal
        from app.modules.guard.mcp_impls import dispatch_guard_tool

        db = SessionLocal()
        try:
            gctx = _build_gctx(ctx, db)
            return dispatch_guard_tool(tool_name, kwargs, gctx)
        finally:
            db.close()

    _guard_impl.__name__ = f"guard_impl_{tool_name}"
    return _guard_impl


def _to_tooldef(schema: dict[str, Any]) -> ToolDef:
    """Project the /guard/mcp _TOOLS schema dict onto a ToolDef."""
    name = schema["name"]
    return ToolDef(
        name=name,
        description=schema["description"],
        input_schema=schema["inputSchema"],
        impl=_impl(name),
        annotations=_ANNOTATIONS.get(name, ToolAnnotations()),
        tags=_GUARD_TAGS,
    )


_TOOLS: list[ToolDef] = [_to_tooldef(s) for s in _GUARD_TOOL_SCHEMAS]


def register(replace: bool = False) -> None:
    """Register all guard tools into the default registry."""
    default_registry.register_all(_TOOLS, replace=replace)


# Side-effect on import: populate the registry.
register()
