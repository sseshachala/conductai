"""
POST /guard/developer-tools  — CLI pushes tool coverage snapshot
GET  /guard/developer-tools  — dashboard reads per-developer coverage
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardDeveloperTools

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
    """Return the latest tool coverage snapshot for every developer in the workspace."""
    rows = (
        db.query(GuardDeveloperTools)
        .filter(GuardDeveloperTools.workspace_id == workspace_id)
        .order_by(GuardDeveloperTools.reported_at.desc())
        .all()
    )
    return [
        DeveloperToolsOut(
            email=row.user_email,
            detected_tools=row.detected_tools or [],
            mcp_registered=row.mcp_registered or [],
            hook_registered=row.hook_registered or [],
            reported_at=row.reported_at,
        )
        for row in rows
    ]
