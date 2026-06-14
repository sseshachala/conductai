"""
POST /guard/developer-tools  — CLI pushes tool coverage snapshot
GET  /guard/developer-tools  — dashboard reads per-developer coverage
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text as _sql
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardDeveloperTools

# MCP-sourced surfaces that should appear in Tool Coverage
_MCP_SURFACES = {"claude_chat", "claude_desktop", "claude_work", "claude-chat", "claude-desktop", "claude-work"}
_MCP_SURFACE_LABEL = "claude_chat"  # canonical key for "connected via remote MCP"

router = APIRouter(prefix="/guard/developer-tools", tags=["guard"])


class ToolEntry(BaseModel):
    name: str
    mcp_registered: bool = False
    hook_registered: bool = False


class DeveloperToolsIn(BaseModel):
    email: str
    tools: list[ToolEntry]


class DeveloperToolsOut(BaseModel):
    email: str
    detected_tools: list[str]
    mcp_registered: list[str]
    hook_registered: list[str]
    reported_at: datetime


@router.post("", status_code=204)
def report_developer_tools(
    body: DeveloperToolsIn,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """CLI pushes AI tool coverage snapshot for a developer (upsert by workspace + email)."""
    detected = [t.name for t in body.tools]
    mcp_reg  = [t.name for t in body.tools if t.mcp_registered]
    hook_reg = [t.name for t in body.tools if t.hook_registered]

    stmt = pg_insert(GuardDeveloperTools).values(
        workspace_id=workspace_id,
        user_email=body.email,
        detected_tools=detected,
        mcp_registered=mcp_reg,
        hook_registered=hook_reg,
        reported_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        constraint="uq_guard_dev_tools",
        set_=dict(
            detected_tools=detected,
            mcp_registered=mcp_reg,
            hook_registered=hook_reg,
            reported_at=datetime.now(timezone.utc),
        ),
    )
    db.execute(stmt)
    db.commit()


@router.get("", response_model=list[DeveloperToolsOut])
def get_developer_tools(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Return the latest tool coverage snapshot for every developer in the workspace.
    Also injects MCP-sourced surfaces (claude_chat, claude_desktop, claude_work) from
    recent audit events so Claude.ai connections show up in Tool Coverage."""
    rows = (
        db.query(GuardDeveloperTools)
        .filter(GuardDeveloperTools.workspace_id == workspace_id)
        .order_by(GuardDeveloperTools.reported_at.desc())
        .all()
    )

    # Find users with recent MCP-sourced events (last 7 days).
    # Resolve clerk_user_ids (user_3D6E...) to real emails via users table.
    since = datetime.now(timezone.utc) - timedelta(days=7)
    ws_uuid = uuid.UUID(workspace_id)
    mcp_rows = db.execute(
        _sql("""
            SELECT DISTINCT user_email
            FROM guard_audit_events
            WHERE workspace_id = :w AND ts >= :since AND ai_tool = ANY(:surfaces)
        """),
        {"w": ws_uuid, "since": since, "surfaces": list(_MCP_SURFACES)},
    ).fetchall()

    # Build map: email → set of MCP surfaces seen
    mcp_by_email: dict[str, set[str]] = {}
    for r in mcp_rows:
        email = r.user_email or ""
        if email:
            mcp_by_email.setdefault(email, set()).add("claude_chat")

    result = []
    seen_emails = set()
    for row in rows:
        email = row.user_email
        seen_emails.add(email)
        detected = list(row.detected_tools or [])
        mcp_reg  = list(row.mcp_registered or [])
        hook_reg = list(row.hook_registered or [])

        if email in mcp_by_email and "claude_chat" not in detected:
            detected.append("claude_chat")
            mcp_reg.append("claude_chat")

        result.append(DeveloperToolsOut(
            email=email,
            detected_tools=detected,
            mcp_registered=mcp_reg,
            hook_registered=hook_reg,
            reported_at=row.reported_at,
        ))

    # Also surface MCP-only users who never ran CLI sync
    for email, _ in mcp_by_email.items():
        if email not in seen_emails:
            result.append(DeveloperToolsOut(
                email=email,
                detected_tools=["claude_chat"],
                mcp_registered=["claude_chat"],
                hook_registered=[],
                reported_at=datetime.now(timezone.utc),
            ))

    return result
