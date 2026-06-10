"""
POST /guard/session-reports  — CLI pushes a developer session report (member token auth)
GET  /guard/session-reports  — admin/security lists all reports for a workspace
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_guard_hook_auth, require_permission
from app.core.database import get_db
from app.modules.guard.models import SessionReport

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/session-reports", tags=["guard"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class SessionReportIn(BaseModel):
    developer_email: str
    archetype: Optional[str] = None
    autonomy_score: Optional[float] = None
    planning_ratio: Optional[float] = None
    sessions: int = 0
    prompts: int = 0
    commits: int = 0
    lines_per_hour: Optional[float] = None
    active_days: Optional[int] = None
    tools_json: Optional[dict] = None
    report_md: Optional[str] = None


class SessionReportOut(BaseModel):
    id: str
    workspace_id: str
    developer_email: str
    archetype: Optional[str]
    autonomy_score: Optional[float]
    planning_ratio: Optional[float]
    sessions: int
    prompts: int
    commits: int
    lines_per_hour: Optional[float]
    active_days: Optional[int]
    tools_json: Optional[dict]
    created_at: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _report_to_out(r: SessionReport) -> SessionReportOut:
    return SessionReportOut(
        id=str(r.id),
        workspace_id=str(r.workspace_id),
        developer_email=r.developer_email,
        archetype=r.archetype,
        autonomy_score=r.autonomy_score,
        planning_ratio=r.planning_ratio,
        sessions=r.sessions,
        prompts=r.prompts,
        commits=r.commits,
        lines_per_hour=r.lines_per_hour,
        active_days=r.active_days,
        tools_json=r.tools_json,
        created_at=r.created_at.isoformat(),
    )


# ── GET /guard/session-reports ────────────────────────────────────────────────


@router.get("", response_model=list[SessionReportOut])
def list_session_reports(
    workspace_id: UUID = Query(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.activity.view_all")),
):
    """List session reports for a workspace, newest first, up to 200 rows.

    Requires guard.activity.view_all (admin or security role).
    """
    rows = (
        db.query(SessionReport)
        .filter(SessionReport.workspace_id == workspace_id)
        .order_by(SessionReport.created_at.desc())
        .limit(200)
        .all()
    )
    return [_report_to_out(r) for r in rows]


# ── POST /guard/session-reports ───────────────────────────────────────────────


@router.post("", response_model=SessionReportOut, status_code=201)
def create_session_report(
    body: SessionReportIn,
    db: Session = Depends(get_db),
    auth_workspace_id: str = Depends(get_guard_hook_auth),
):
    """Push a new session report from the CLI.

    Auth accepts a member token, Clerk JWT, or cond_live_ API key —
    the same trust model as POST /guard/events. The workspace_id is
    derived from the token, not the request body.
    """
    try:
        ws_uuid = uuid.UUID(auth_workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id from token")

    report = SessionReport(
        workspace_id=ws_uuid,
        developer_email=body.developer_email,
        archetype=body.archetype,
        autonomy_score=body.autonomy_score,
        planning_ratio=body.planning_ratio,
        sessions=body.sessions,
        prompts=body.prompts,
        commits=body.commits,
        lines_per_hour=body.lines_per_hour,
        active_days=body.active_days,
        tools_json=body.tools_json,
        report_md=body.report_md,
    )
    db.add(report)
    db.commit()

    log.info(
        "session_report.created",
        report_id=str(report.id),
        workspace_id=auth_workspace_id,
        developer_email=body.developer_email,
        archetype=body.archetype,
        sessions=body.sessions,
    )

    return _report_to_out(report)
