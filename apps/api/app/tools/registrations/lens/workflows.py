"""Lens tool registrations — workflows domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _actor_impl,
    _window_start,
    _LIMIT,
    _DECISION,
    _TS_SINCE,
    _TS_UNTIL,
    _RULE_ID,
    _DAYS_WINDOW,
    _TIME_WINDOW,
    _READ_ONLY,
    _READ_ONLY_OPEN_WORLD,
    _LENS_TAGS,
    _ACTOR_TAGS
)


# ── Free-function tool implementations ─────────────────────────────────
def list_workflows(ctx, status: str | None = None, limit: int = 20):
    """Enumerate workflows in this workspace's org. Migrated from
    Executor._tool_list_workflows (epic #1655)."""
    from app.core.database import SessionLocal
    from app.modules.guard.routers.spend import _org_ws_subquery
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = db.query(Workflow).filter(Workflow.workspace_id.in_(org_ws))
        status = (status or "active").lower()
        if status == "active":
            q = q.filter(Workflow.archived_at.is_(None))
        elif status == "archived":
            q = q.filter(Workflow.archived_at.isnot(None))
        rows = q.order_by(Workflow.updated_at.desc()).limit(min(limit, 100)).all()
        return [
            {
                "workflow_id": str(w.id),
                "name": w.name,
                "guard_enabled": bool(w.guard_enabled),
                "archived": w.archived_at is not None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
            }
            for w in rows
        ]
    finally:
        db.close()


def get_blocked_workflows(ctx, since: str | None = None, until: str | None = None,
                          workflow_id: str | None = None, rule_id: str | None = None,
                          limit: int = 20):
    """Workflows Guard has blocked, ranked by block count. Migrated from
    Executor._tool_get_blocked_workflows (epic #1655)."""
    from sqlalchemy import func as sa_func
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent
    from app.modules.guard.routers.spend import _org_ws_subquery
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        base = (
            db.query(GuardAuditEvent)
            .filter(GuardAuditEvent.workspace_id.in_(org_ws))
            .filter(GuardAuditEvent.decision == "blocked")
            .filter(GuardAuditEvent.conductai_workflow_id.isnot(None))
        )
        if since:
            base = base.filter(GuardAuditEvent.ts >= since)
        if until:
            base = base.filter(GuardAuditEvent.ts <= until)
        if workflow_id:
            base = base.filter(GuardAuditEvent.conductai_workflow_id == workflow_id)
        if rule_id:
            base = base.filter(GuardAuditEvent.rule_id == rule_id)

        top_rule = (
            sa_func.mode()
            .within_group(GuardAuditEvent.rule_id.asc())
            .filter(GuardAuditEvent.rule_id.isnot(None))
            .label("top_rule_id")
        )
        rows = (
            base.with_entities(
                GuardAuditEvent.conductai_workflow_id.label("workflow_id"),
                sa_func.max(GuardAuditEvent.conductai_workflow).label("name"),
                sa_func.count().label("block_count"),
                sa_func.max(GuardAuditEvent.ts).label("last_blocked_at"),
                top_rule,
            )
            .group_by(GuardAuditEvent.conductai_workflow_id)
            .order_by(sa_func.count().desc())
            .limit(min(limit, 100))
            .all()
        )
        return [
            {
                "workflow_id": r.workflow_id,
                "name": r.name,
                "block_count": int(r.block_count),
                "top_rule_id": r.top_rule_id,
                "last_blocked_at": r.last_blocked_at.isoformat() if r.last_blocked_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_workflow_details(ctx, workflow_id: str | None = None, name: str | None = None):
    """One workflow: full metadata + latest run status. Match by workflow_id
    OR name. Migrated from Executor._tool_get_workflow_details (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.routers.spend import _org_ws_subquery
    if not workflow_id and not name:
        return {"error": "workflow_id or name required"}
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = db.query(Workflow).filter(Workflow.workspace_id.in_(org_ws))
        if workflow_id:
            try:
                q = q.filter(Workflow.id == _uuid.UUID(workflow_id))
            except ValueError:
                return {"error": "workflow_id must be a UUID"}
        else:
            q = q.filter(Workflow.name == name)
        wf = q.first()
        if not wf:
            return {"error": "Workflow not found"}
        latest_run = (
            db.query(Run)
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .filter(WorkflowVersion.workflow_id == wf.id)
            .order_by(Run.created_at.desc())
            .first()
        )
        return {
            "workflow_id": str(wf.id),
            "name": wf.name,
            "default_mode": wf.default_mode,
            "guard_enabled": bool(wf.guard_enabled),
            "agent_identity_required": bool(wf.agent_identity_required),
            "archived": wf.archived_at is not None,
            "playbook_slug": wf.playbook_slug,
            "source_repo": wf.source_repo,
            "created_at": wf.created_at.isoformat() if wf.created_at else None,
            "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
            "latest_run": None if not latest_run else {
                "run_id": str(latest_run.id),
                "status": latest_run.status,
                "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
                "actual_turns": latest_run.actual_turns,
                "budget_exhausted": latest_run.budget_exhausted,
            },
        }
    finally:
        db.close()


def list_runs(ctx, workflow_id: str | None = None, status: str | None = None,
              since: str | None = None, until: str | None = None, limit: int = 20):
    """Recent runs across workflows. Migrated from
    Executor._tool_list_runs (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.routers.spend import _org_ws_subquery
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        q = (
            db.query(Run, Workflow.name.label("workflow_name"), Workflow.id.label("workflow_id"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
            .filter(Run.workspace_id.in_(org_ws))
        )
        if workflow_id:
            try:
                q = q.filter(Workflow.id == _uuid.UUID(workflow_id))
            except ValueError:
                return {"error": "workflow_id must be a UUID"}
        if status:
            q = q.filter(Run.status == status)
        if since:
            q = q.filter(Run.created_at >= since)
        if until:
            q = q.filter(Run.created_at <= until)
        rows = q.order_by(Run.created_at.desc()).limit(min(limit, 100)).all()
        return [
            {
                "run_id": str(r.Run.id),
                "workflow_id": str(r.workflow_id),
                "workflow_name": r.workflow_name,
                "status": r.Run.status,
                "triggered_by": r.Run.triggered_by,
                "started_at": r.Run.started_at.isoformat() if r.Run.started_at else None,
                "completed_at": r.Run.completed_at.isoformat() if r.Run.completed_at else None,
                "actual_turns": r.Run.actual_turns,
                "budget_exhausted": r.Run.budget_exhausted,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_run(ctx, run_id: str):
    """One run: status, timings, turns, outcome. Migrated from
    Executor._tool_get_run (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.routers.spend import _org_ws_subquery
    try:
        rid = _uuid.UUID(run_id)
    except ValueError:
        return {"error": "run_id must be a UUID"}
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        row = (
            db.query(Run, Workflow.name.label("workflow_name"), Workflow.id.label("workflow_id"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
            .filter(Run.id == rid)
            .filter(Run.workspace_id.in_(org_ws))
            .first()
        )
        if not row:
            return {"error": "Run not found"}
        r = row.Run
        return {
            "run_id": str(r.id),
            "workflow_id": str(row.workflow_id),
            "workflow_name": row.workflow_name,
            "status": r.status,
            "triggered_by": r.triggered_by,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "paused_at": r.paused_at.isoformat() if r.paused_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "current_block_id": r.current_block_id,
            "max_turns": r.max_turns,
            "actual_turns": r.actual_turns,
            "budget_exhausted": r.budget_exhausted,
            "outcome": r.outcome,
            "attempt_count": r.attempt_count,
        }
    finally:
        db.close()


def list_run_events(ctx, run_id: str, kind: str | None = None, limit: int = 100):
    """Events emitted during one workflow run. Migrated from
    Executor._tool_list_run_events (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.routers.spend import _org_ws_subquery
    try:
        rid = _uuid.UUID(run_id)
    except ValueError:
        return {"error": "run_id must be a UUID"}
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        run = db.query(Run).filter(
            Run.id == rid, Run.workspace_id.in_(org_ws)).first()
        if not run:
            return {"error": "Run not found"}
        q = db.query(RunEvent).filter(RunEvent.run_id == rid)
        if kind:
            q = q.filter(RunEvent.kind == kind)
        rows = q.order_by(RunEvent.created_at.asc()).limit(min(limit, 500)).all()
        return [{"id": str(r.id), "block_id": r.block_id, "kind": r.kind,
                 "payload": r.payload,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        db.close()


def list_playbooks(ctx, category: str | None = None):
    """Playbook catalog — builtin templates + user-submitted templates.
    Optional category filter (e.g. 'incident_response', 'ci_cd')."""
    from app.core.database import SessionLocal
    from app.routers.playbooks import _TEMPLATE_PLAYBOOKS, _PLAYBOOK_META

    entries: list[dict] = []
    for slug in _TEMPLATE_PLAYBOOKS:
        meta = _PLAYBOOK_META.get(slug)
        if not meta:
            continue
        if category and meta.get("category") != category:
            continue
        entries.append({
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "description": meta.get("description"),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "featured": meta.get("featured", False),
            "source": "builtin",
        })
    db = SessionLocal()
    try:
        db_playbooks = (
            db.query(Workflow)
            .filter(Workflow.workspace_id == ctx.workspace_id, Workflow.is_template == True)  # noqa: E712
            .all()
        )
        for wf in db_playbooks:
            entries.append({
                "slug": wf.playbook_slug or str(wf.id),
                "name": wf.name,
                "description": "",
                "category": "custom",
                "tags": [],
                "featured": False,
                "source": "user",
            })
    finally:
        db.close()
    return {"count": len(entries), "playbooks": entries}

def get_playbook(ctx, slug: str):
    """Playbook detail — name, description, blocks, inputs, YAML source."""
    from app.routers.playbooks import get_playbook as _get_playbook_route
    try:
        return _get_playbook_route(slug)
    except Exception as e:
        return {"error": str(e), "slug": slug}


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_workflows",
        description="Enumerate workflows in this workspace's org. status = active (default) | archived | all.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "archived", "all"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_workflows,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_run_events",
        description=(
            "Events emitted during one workflow run — block_started/completed/failed, "
            "approval_requested, etc. Use when the user asks 'what happened during run X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
                "kind": {"type": "string", "description": "Filter to one event kind"},
                "limit": _LIMIT,
            },
            "required": ["run_id"],
        },
        impl=list_run_events,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_workflow_details",
        description=(
            "One workflow's full metadata + latest run status. Match by workflow_id "
            "OR name. Use when the user asks 'what's the status of workflow X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow UUID"},
                "name": {"type": "string", "description": "Workflow name"},
            },
            "required": [],
        },
        impl=get_workflow_details,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_runs",
        description=(
            "Recent workflow runs across this workspace's org. Filters: "
            "workflow_id, status (pending/running/paused/succeeded/failed/cancelled), "
            "since/until (ISO ts). Returns run_id, workflow_id, workflow_name, "
            "status, started_at, completed_at, triggered_by, actual_turns."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "paused", "succeeded", "failed", "cancelled"],
                },
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_runs,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_run",
        description=(
            "One run's status + timings + outcome payload. Use when the user asks "
            "'what happened in run <id>' or drills into a specific run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
            },
            "required": ["run_id"],
        },
        impl=get_run,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_blocked_workflows",
        description=(
            "Workflows Guard has blocked, ranked by block count. Returns "
            "[{workflow_id, name, block_count, top_rule_id, last_blocked_at}]. "
            "Optional filters: since/until (ISO ts), workflow_id, rule_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "rule_id": _RULE_ID,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=get_blocked_workflows,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_playbooks",
        description="Playbook catalog — builtin templates + user-submitted templates. Optional category filter (e.g. 'incident_response', 'ci_cd').",
        input_schema={
            "type": "object",
            "properties": {"category": {"type": "string", "description": "Filter by category slug."}},
            "required": [],
        },
        impl=list_playbooks,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_playbook",
        description="Playbook detail — name, description, blocks, inputs, YAML source.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Playbook slug (e.g. 'incident_response')."}},
            "required": ["slug"],
        },
        impl=get_playbook,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
