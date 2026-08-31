"""Lens tool registrations — run history (#1480 PR 8).

Two tools that let Lens surface a user's / a session's run history without
leaving the chat surface:

- `list_my_runs` — cross-session, workspace-scoped, filtered by the calling
  user's clerk_user_id (from `ctx`). Answers "what did I run today?"
- `list_runs_in_session` — filter by the SSE session id introduced in PR 1.
  Answers "what did we run in this conversation?"

Both are read-only free-function tools (not routed through Executor) so
we can read the current user + session directly from ctx.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _LIMIT,
    _LENS_TAGS,
    _READ_ONLY,
)


_RUN_STATUS_ENUM = ["pending", "running", "paused", "succeeded", "failed", "cancelled"]


def _serialize_row(row) -> dict[str, Any]:
    """Common row shape — matches list_runs so consumers can share rendering."""
    r = row.Run
    return {
        "run_id": str(r.id),
        "workflow_id": str(row.workflow_id),
        "workflow_name": row.workflow_name,
        "status": r.status,
        "triggered_by": r.triggered_by,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "actual_turns": r.actual_turns,
    }


def list_my_runs(ctx, status: str | None = None, limit: int = 20):
    """Recent runs triggered by the current user across the workspace org.

    Only returns runs where `triggered_by` matches the caller's
    clerk_user_id — auth is enforced by ctx, not by the LLM. Same as
    list_runs but scoped to me.
    """
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.modules.glens.executor import _org_ws_subquery

    clerk_user_id = getattr(ctx, "clerk_user_id", None)
    if not clerk_user_id or clerk_user_id.startswith("system:"):
        return {"error": "list_my_runs requires a real user context (not system/lens actor)"}

    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = (
            db.query(Run, Workflow.name.label("workflow_name"), Workflow.id.label("workflow_id"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
            .filter(Run.workspace_id.in_(org_ws))
            .filter(Run.triggered_by == clerk_user_id)
        )
        if status:
            q = q.filter(Run.status == status)
        rows = q.order_by(Run.created_at.desc()).limit(min(limit, 100)).all()
        return [_serialize_row(row) for row in rows]
    finally:
        db.close()


def list_runs_in_session(ctx, session_id: str | None = None, status: str | None = None, limit: int = 20):
    """Runs triggered from a Lens chat session (populated by PR 1's
    runs.session_id column). Defaults to the current session in ctx.
    """
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.modules.glens.executor import _org_ws_subquery

    sid = session_id or getattr(ctx, "session_id", None)
    if not sid:
        return {"error": "session_id required (no current session in ctx)"}
    try:
        sid_uuid = uuid.UUID(sid)
    except (ValueError, TypeError):
        return {"error": "session_id must be a UUID"}

    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = (
            db.query(Run, Workflow.name.label("workflow_name"), Workflow.id.label("workflow_id"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
            .filter(Run.workspace_id.in_(org_ws))
            .filter(Run.session_id == sid_uuid)
        )
        if status:
            q = q.filter(Run.status == status)
        rows = q.order_by(Run.created_at.desc()).limit(min(limit, 100)).all()
        return [_serialize_row(row) for row in rows]
    finally:
        db.close()


TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_my_runs",
        description=(
            "Recent workflow runs triggered by the CURRENT user in this workspace org. "
            "Use for 'what did I run today', 'my recent runs', 'show my last workflow'. "
            "Returns run_id, workflow_name, status, timings. Cross-session — spans "
            "every Lens conversation the user has had. For a single-session view "
            "use list_runs_in_session instead."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": _RUN_STATUS_ENUM,
                    "description": "Filter to one lifecycle state",
                },
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_my_runs,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_runs_in_session",
        description=(
            "Runs triggered from THIS Lens chat session (or a specific session_id). "
            "Use for 'what did we run here', 'runs from this conversation', 'show "
            "everything I've kicked off in this session'. Only lists Lens-originated "
            "runs — runs triggered from the workflow UI or CLI won't appear."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session UUID; defaults to current session in ctx",
                },
                "status": {
                    "type": "string",
                    "enum": _RUN_STATUS_ENUM,
                    "description": "Filter to one lifecycle state",
                },
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_runs_in_session,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
