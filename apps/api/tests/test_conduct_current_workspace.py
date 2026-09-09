"""Unit tests for conduct_current_workspace MCP tool.

The impl reads ctx (workspace_id, clerk_user_id, user_email) and does one
DB query joining `workspaces` with `workspace_users` to return the caller's
active workspace + role. Tests exercise all three response envelopes:
- happy path (workspace exists, user is a member) → JSON with id/name/role
- workspace missing → {"error": "workspace_not_found"}
- DB failure → {"error": "lookup_failed: ..."}
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

from app.modules.guard.mcp_impls import conduct_current_workspace_impl


def _ctx(ws_uuid=None, clerk_user_id="user_x", user_email="x@example.com"):
    """Minimal GuardCtx-shaped stub — impl only reads these fields."""
    return SimpleNamespace(
        db=None,
        ws_uuid=ws_uuid or uuid.uuid4(),
        workspace_id=None,
        resolved_token="",
        clerk_user_id=clerk_user_id,
        user_email=user_email,
        ai_tool="http",
        session_id="",
    )


def _stub_db(row):
    """DB stub: db.execute(sql, params).fetchone() → row."""
    class _Result:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return self._row

    class _Db:
        def execute(self, _sql, _params):
            return _Result(row)

    return _Db()


def test_happy_path_returns_workspace_and_role():
    ws_uuid = uuid.uuid4()
    ctx = _ctx(ws_uuid=ws_uuid, clerk_user_id="user_1", user_email="alice@acme.com")
    ctx.db = _stub_db(SimpleNamespace(
        workspace_id=ws_uuid,
        workspace_name="Acme Engineering",
        role="admin",
    ))

    result = json.loads(conduct_current_workspace_impl(ctx))
    assert result["workspace_id"] == str(ws_uuid)
    assert result["workspace_name"] == "Acme Engineering"
    assert result["role"] == "admin"
    assert result["member_email"] == "alice@acme.com"


def test_missing_membership_returns_unknown_role():
    """User is on a workspace but has no workspace_users row (edge — legacy
    owner without membership). Row still returns, but role is NULL → 'unknown'."""
    ctx = _ctx()
    ctx.db = _stub_db(SimpleNamespace(
        workspace_id=ctx.ws_uuid,
        workspace_name="Legacy Workspace",
        role=None,
    ))

    result = json.loads(conduct_current_workspace_impl(ctx))
    assert result["role"] == "unknown"
    assert result["workspace_name"] == "Legacy Workspace"


def test_workspace_not_found_returns_error_envelope():
    ctx = _ctx()
    ctx.db = _stub_db(None)  # fetchone returns None

    result = json.loads(conduct_current_workspace_impl(ctx))
    assert result == {"error": "workspace_not_found"}


def test_db_exception_returns_error_envelope():
    class _BoomDb:
        def execute(self, *_a, **_k):
            raise RuntimeError("connection reset")

    ctx = _ctx()
    ctx.db = _BoomDb()

    result = json.loads(conduct_current_workspace_impl(ctx))
    assert result["error"].startswith("lookup_failed:")
    assert "connection reset" in result["error"]


def test_tool_registered_via_default_registry():
    """Integration: prove the tool is in default_registry with correct annotations.
    This is what /mcp tools/list projects onto the wire."""
    from app.tools.registry import default_registry
    import app.tools.registrations  # noqa: F401  — side-effect: populate registry

    tools = {t["name"]: t for t in default_registry.as_mcp_tools_list()}
    assert "conduct_current_workspace" in tools
    t = tools["conduct_current_workspace"]
    # Spec-mandated Hint suffix (Claude.ai's strict parser rejects the no-suffix form).
    assert t["annotations"]["readOnlyHint"] is True
    assert t["annotations"]["idempotentHint"] is True
    assert t["annotations"]["destructiveHint"] is False
