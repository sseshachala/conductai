"""#1219 Phase 3b Chunk B — Guard MCP tool registrations.

Non-DB unit tests: prove the 17 schemas in
apps/api/app/modules/guard/routers/mcp._TOOLS have matching ToolDefs, prove
annotations are set for every tool, prove default_registry populates on
import, prove GuardCtx is constructable from a minimal MCPContext.

Byte-parity of the actual dispatch is exercised by
tests/regression/test_mcp_parity.py — both endpoints call the same
dispatch_guard_tool function so drift is impossible by construction.
"""
from __future__ import annotations

import uuid

from app.mcp.server import MCPContext
from app.modules.guard.mcp_impls import GuardCtx, dispatch_guard_tool
from app.modules.guard.routers.mcp import _TOOLS as _GUARD_TOOL_SCHEMAS
from app.tools.registrations import guard as guard_reg
from app.tools.registry import default_registry


def test_every_guard_schema_has_registration():
    schema_names = {s["name"] for s in _GUARD_TOOL_SCHEMAS}
    registered_names = {t.name for t in guard_reg._TOOLS}
    assert schema_names == registered_names


def test_default_registry_contains_all_guard_tools():
    guard_registered = default_registry.list(tag="guard")
    assert len(guard_registered) == len(_GUARD_TOOL_SCHEMAS)


def test_all_guard_tools_have_annotations():
    for t in guard_reg._TOOLS:
        # every tool must have explicit annotations in _ANNOTATIONS —
        # missing entry means someone added a schema without deciding on
        # side-effect profile.
        assert t.name in guard_reg._ANNOTATIONS, f"{t.name} missing annotation entry"


def test_write_tools_are_not_read_only():
    for name in ("guard_activity", "post_finding", "trigger_fix",
                 "conduct_run_workflow", "guard_discover_register", "guard_check"):
        tool = next(t for t in guard_reg._TOOLS if t.name == name)
        assert not tool.annotations.read_only, f"{name} should not be read_only"


def test_destructive_tools_are_the_two_expected():
    destructive = {t.name for t in guard_reg._TOOLS if t.annotations.destructive}
    assert destructive == {"trigger_fix", "conduct_run_workflow"}


def test_build_gctx_from_minimal_mcp_context():
    ws = uuid.uuid4()
    ctx = MCPContext(
        workspace_id=str(ws),
        clerk_user_id="user_test",
        surface="http",
        user_email="test@example.com",
        session_id="sess-abc",
        resolved_token="cond_test_xyz",
    )
    gctx = guard_reg._build_gctx(ctx, db=None)
    assert isinstance(gctx, GuardCtx)
    assert gctx.ws_uuid == ws
    assert gctx.user_email == "test@example.com"
    assert gctx.session_id == "sess-abc"
    assert gctx.ai_tool == "http"
    assert gctx.resolved_token == "cond_test_xyz"


def test_unknown_tool_returns_marker_string():
    """dispatch_guard_tool is the source of truth — unknown tool returns
    exactly the same 'Unknown tool: X' string both endpoints emit."""
    class _Ctx:
        db = None
        ws_uuid = uuid.uuid4()
        workspace_id = str(ws_uuid)
        resolved_token = ""
        clerk_user_id = None
        user_email = None
        ai_tool = "http"
        session_id = "s"
    out = dispatch_guard_tool("no_such_tool", {}, _Ctx())
    assert out == "Unknown tool: no_such_tool"
