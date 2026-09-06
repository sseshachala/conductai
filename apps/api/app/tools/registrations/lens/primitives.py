"""Lens tool registrations — primitives domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

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
def list_machines_sync_state(ctx, filter: str = "all"):
    """Per-machine sync state — user_email, detected tools, mcp_registered,
    hook_registered, last_sync_at, in_sync. filter=out_of_sync returns only
    machines missing a tool registration.

    GuardDeveloperTools.workspace_id is Text, not UUID, so we pass a string
    directly (no uuid conversion).
    """
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardDeveloperTools
    db = SessionLocal()
    try:
        rows = (
            db.query(GuardDeveloperTools)
            .filter(GuardDeveloperTools.workspace_id == ctx.workspace_id)
            .order_by(GuardDeveloperTools.reported_at.desc())
            .all()
        )
        out: list[dict] = []
        for r in rows:
            detected = list(r.detected_tools or [])
            mcp_reg = list(r.mcp_registered or [])
            hook_reg = list(r.hook_registered or [])
            in_sync = all(t in mcp_reg or t in hook_reg for t in detected)
            if filter == "out_of_sync" and in_sync:
                continue
            out.append({
                "user_email": r.user_email,
                "detected_tools": detected,
                "mcp_registered": mcp_reg,
                "hook_registered": hook_reg,
                "last_sync_at": r.reported_at.isoformat() if r.reported_at else None,
                "in_sync": in_sync,
            })
        return {"count": len(out), "machines": out}
    finally:
        db.close()

def get_llm_primitives(ctx):
    """Workspace LLM routing config — preferred provider + per-tier models
    (cheap / balanced / smart). API keys are never returned; those live in
    Vault."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceLLMPrimitives).filter(
            WorkspaceLLMPrimitives.workspace_id == ws_uuid
        ).first()
        if row is None:
            return {
                "configured": False,
                "preferred_provider": "anthropic",
                "tier_map": {},
                "updated_at": None,
            }
        return {
            "configured": True,
            "preferred_provider": row.preferred_provider,
            "tier_map": row.tier_map or {},
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        db.close()

def get_rate_limits(ctx):
    """Workspace rate limits — default RPM/TPM plus any per-agent overrides.
    Blocks return 429 with x-guard reason when either cap trips."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardRateLimit
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = db.query(GuardRateLimit).filter(GuardRateLimit.workspace_id == ws_uuid).all()
        default_row = next((r for r in rows if r.agent_identity_id is None), None)
        overrides = [
            {
                "agent_identity_id": r.agent_identity_id,
                "rpm": r.rpm,
                "tpm": r.tpm,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows if r.agent_identity_id is not None
        ]
        return {
            "default": {
                "rpm": default_row.rpm if default_row else None,
                "tpm": default_row.tpm if default_row else None,
                "updated_at": default_row.updated_at.isoformat() if default_row and default_row.updated_at else None,
            },
            "overrides": overrides,
            "override_count": len(overrides),
        }
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_machines_sync_state",
        description="Per-machine Guard sync state — detected tools vs MCP/hook registrations. filter=out_of_sync returns only unsynced machines.",
        input_schema={
            "type": "object",
            "properties": {"filter": {"type": "string", "description": "'all' (default) or 'out_of_sync'."}},
            "required": [],
        },
        impl=list_machines_sync_state,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_llm_primitives",
        description="Workspace LLM routing config — preferred provider + per-tier models. API keys are never returned.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_llm_primitives,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_rate_limits",
        description="Workspace rate limits — default RPM/TPM plus any per-agent overrides.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_rate_limits,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
