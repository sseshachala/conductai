"""Guard MCP tool impls — Conduct platform verbs (agents, projects, playbooks, workflow runs, current workspace).

Dispatched through ``mcp_impls.dispatch_guard_tool``; see that module for the impl contract."""

from __future__ import annotations

import json
from sqlalchemy import text as _sql
from app.modules.guard.routers.mcp import (  # noqa: E402
    _list_agents,
    _list_playbooks,
    _list_projects,
    _run_workflow,
    _get_run_status,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.guard.mcp_impls import GuardCtx


def conduct_list_agents_impl(ctx: GuardCtx, **arguments) -> str:
    db = ctx.db
    ws_uuid = ctx.ws_uuid

    return json.dumps(_list_agents(db, ws_uuid), indent=2)


def conduct_list_projects_impl(ctx: GuardCtx, **arguments) -> str:
    db = ctx.db
    ws_uuid = ctx.ws_uuid

    return json.dumps(_list_projects(db, ws_uuid), indent=2)


def conduct_list_playbooks_impl(ctx: GuardCtx, **arguments) -> str:
    db = ctx.db
    ws_uuid = ctx.ws_uuid

    return json.dumps(_list_playbooks(db, ws_uuid), indent=2)


def conduct_run_workflow_impl(ctx: GuardCtx, **arguments) -> str:
    db = ctx.db
    ws_uuid = ctx.ws_uuid
    user_email = ctx.user_email

    wf_id = arguments.get("workflow_id", "")
    payload = arguments.get("payload") or {}
    if not wf_id:
        return "Error — workflow_id is required."
    try:
        result = _run_workflow(db, ws_uuid, wf_id, payload, user_email)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return f"Error — {e}"


def conduct_get_run_impl(ctx: GuardCtx, **arguments) -> str:
    db = ctx.db
    ws_uuid = ctx.ws_uuid

    wf_id = arguments.get("workflow_id", "")
    run_id = arguments.get("run_id", "")
    if not wf_id or not run_id:
        return "Error — workflow_id and run_id are required."
    try:
        result = _get_run_status(db, ws_uuid, wf_id, run_id)
        return json.dumps(result, indent=2)
    except ValueError as e:
        return f"Error — {e}"


def conduct_current_workspace_impl(ctx: GuardCtx, **arguments) -> str:
    """Return the caller's active workspace: id, name, and their role.

    LLMs use this to remind themselves which workspace context they're in —
    useful when a user is a member of multiple workspaces and has multiple
    Conduct MCP connectors installed (see issue #1747 for the alternative
    in-chat workspace-switching design).

    Returns JSON: {workspace_id, workspace_name, role, member_email}. If the
    workspace or membership can't be resolved, returns an {error} envelope.
    """
    db = ctx.db
    ws_uuid = ctx.ws_uuid
    clerk_user_id = ctx.clerk_user_id
    user_email = ctx.user_email

    try:
        row = db.execute(
            _sql("""
                SELECT w.id AS workspace_id, w.name AS workspace_name, wu.role AS role
                FROM workspaces w
                LEFT JOIN workspace_users wu
                       ON wu.workspace_id = w.id AND wu.clerk_user_id = :uid
                WHERE w.id = :ws
                LIMIT 1
            """),
            {"ws": str(ws_uuid), "uid": clerk_user_id or ""},
        ).fetchone()
    except Exception as e:
        return json.dumps({"error": f"lookup_failed: {e}"})

    if row is None:
        return json.dumps({"error": "workspace_not_found"})

    return json.dumps({
        "workspace_id":   str(row.workspace_id),
        "workspace_name": row.workspace_name,
        "role":           row.role or "unknown",
        "member_email":   user_email,
    }, indent=2)
