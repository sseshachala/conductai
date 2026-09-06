"""Lens tool registrations — policies domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _impl,
    _run,
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
def list_policies(ctx):
    """All custom workspace policies. Migrated from
    Executor._tool_list_policies (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import WorkspaceCustomRule
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid
        ).all()
        return [
            {"rule_id": r.rule_id, "enabled": r.enabled, "persona": r.persona,
             "action": r.body.get("action"), "description": r.body.get("description"),
             "match_tool": r.body.get("match_tool"), "match_pattern": r.body.get("match_pattern"),
             "severity": r.body.get("severity", "medium")}
            for r in rows
        ]
    finally:
        db.close()


def get_policy(ctx, rule_id: str):
    """Full body of one custom policy by rule_id. Migrated from
    Executor._tool_get_policy (epic #1655)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import WorkspaceCustomRule
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not row:
            return {"error": f"Policy '{rule_id}' not found"}
        return {"rule_id": row.rule_id, "enabled": row.enabled, "persona": row.persona, **row.body}
    finally:
        db.close()


def list_credentials(ctx, environment_id: str | None = None, service: str | None = None):
    """Vault inventory — service + handle + auth_method + scopes + last_used_at
    per Integration row. NEVER returns encrypted_credentials or any raw
    secret material.

    Optional filters: environment_id (Vault UUID), service
    (github / slack / linear / …).
    """
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.integration import Integration
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(Integration).filter(Integration.workspace_id == ws_uuid)
        if service:
            q = q.filter(Integration.service == service)
        if environment_id:
            try:
                q = q.filter(Integration.environment_id == _uuid.UUID(environment_id))
            except ValueError:
                pass
        rows = q.order_by(Integration.created_at.desc()).all()
        return {
            "count": len(rows),
            "credentials": [
                {
                    "id": str(r.id),
                    "service": r.service,
                    "handle": r.handle,
                    "auth_method": r.auth_method,
                    "scopes": r.scopes or [],
                    "environment_id": str(r.environment_id) if r.environment_id else None,
                    "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_policies",
        description="All custom workspace policies (rule_id, enabled, persona, action, description).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_policies,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_policy",
        description="Full body of one custom policy by rule_id.",
        input_schema={
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
        impl=get_policy,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_credentials",
        description="Vault inventory — metadata only. Returns service, handle, auth_method, scopes, environment, last_used_at. NEVER returns the secret value.",
        input_schema={
            "type": "object",
            "properties": {
                "environment_id": {"type": "string", "description": "Filter by environment (Vault) UUID."},
                "service": {"type": "string", "description": "Filter by service slug (github/slack/…)"},
            },
            "required": [],
        },
        impl=list_credentials,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
