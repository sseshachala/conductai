"""
POST /guard/session-reports  — CLI pushes a developer session report (member token auth)
GET  /guard/session-reports  — admin/security lists all reports for a workspace
GET  /guard/session-reports/{id}/html — styled HTML report (API key or Clerk JWT via ?token=)
"""

import uuid
from datetime import date as _date
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import (
    _verify_clerk_token,
    get_guard_hook_auth,
    get_workspace_id,
    require_permission,
)
from app.core.database import SessionLocal, get_db
from app.core.keyset import before_clause
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.embedding import (
    embedding_client_for_workspace as _embedding_client_for_workspace,
)
from app.modules.guard.models import SessionReport
from app.modules.guard.routers.session_report_html import _build_html

log = structlog.get_logger(__name__)

_bearer_optional = HTTPBearer(auto_error=False)

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
    report_md: Optional[str]
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
        report_md=r.report_md,
        created_at=r.created_at.isoformat(),
    )


# ── GET /guard/session-reports ────────────────────────────────────────────────


@router.get("", response_model=list[SessionReportOut])
def list_session_reports(
    workspace_id: UUID = Query(..., description="Workspace UUID"),
    limit: int = Query(default=50, ge=1, le=200),
    before: str | None = Query(default=None, description="Keyset cursor '<created_at>|<id>' from the last row"),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.activity.view_all")),
):
    """List session reports for a workspace, newest first (default 50, max 200).

    Requires guard.activity.view_all (admin or security role).
    """
    q = db.query(SessionReport).filter(SessionReport.workspace_id == workspace_id)
    cursor = before_clause(SessionReport.created_at, SessionReport.id, before)
    if cursor is not None:
        q = q.filter(cursor)
    rows = (
        q.order_by(SessionReport.created_at.desc(), SessionReport.id.desc())
        .limit(limit)
        .all()
    )
    return [_report_to_out(r) for r in rows]


# ── GET /guard/session-reports/{id} ───────────────────────────────────────────


@router.get("/search")
def search_session_reports(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(default=5, ge=1, le=20),
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Semantic search over session reports using pgvector."""
    from sqlalchemy import text as sa_text

    db.rollback()
    client = _embedding_client_for_workspace(workspace_id)
    if not client:
        raise HTTPException(status_code=503, detail="Embedding service not configured")

    embedding = client.embed(q[:2000])
    set_workspace_rls(db, workspace_id)
    rows = db.execute(
        sa_text(
            "SELECT id, developer_email, archetype, autonomy_score, sessions, prompts, "
            "report_md, created_at, "
            "(embedding <=> CAST(:vec AS vector)) AS distance "
            "FROM session_reports "
            "WHERE workspace_id = :workspace_id AND embedding IS NOT NULL "
            "ORDER BY distance ASC LIMIT :limit"
        ),
        {"workspace_id": workspace_id, "vec": str(embedding), "limit": limit},
    ).fetchall()

    return [
        {
            "id": str(r.id),
            "developer_email": r.developer_email,
            "archetype": r.archetype,
            "autonomy_score": r.autonomy_score,
            "sessions": r.sessions,
            "prompts": r.prompts,
            "summary": (r.report_md or "")[:500],
            "created_at": r.created_at.isoformat(),
            "score": round(1 - r.distance, 3),
        }
        for r in rows
    ]


@router.get("/{report_id}", response_model=SessionReportOut)
def get_session_report(
    report_id: UUID,
    workspace_id: UUID = Query(..., description="Workspace UUID"),
    _: str = Depends(require_permission("guard.activity.view_all")),
    db: Session = Depends(get_db),
) -> SessionReportOut:
    r = (
        db.query(SessionReport)
        .filter(
            SessionReport.id == report_id, SessionReport.workspace_id == workspace_id
        )
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return _report_to_out(r)


def _embed_session_report(
    report_id: str, workspace_id: str, expected_report_md: str
) -> None:
    try:
        client = _embedding_client_for_workspace(workspace_id)
        if not client:
            return
        embedding = client.embed(expected_report_md[:8000])
        with SessionLocal() as write_db:
            set_workspace_rls(write_db, workspace_id)
            write_db.query(SessionReport).filter(
                SessionReport.id == uuid.UUID(report_id),
                SessionReport.workspace_id == uuid.UUID(workspace_id),
                SessionReport.report_md == expected_report_md,
            ).update({SessionReport.embedding: embedding}, synchronize_session=False)
            write_db.commit()
    except Exception as exc:
        log.warning("session_report.embed_failed", report_id=report_id, error=str(exc))


# ── POST /guard/session-reports ───────────────────────────────────────────────


@router.post("", response_model=SessionReportOut, status_code=201)
def create_session_report(
    body: SessionReportIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_workspace_id: str = Depends(get_guard_hook_auth),
):
    """Push a new session report from the CLI.

    Auth accepts a member token or Clerk JWT — the same trust model as
    POST /guard/events. The workspace_id is derived from the token,
    not the request body.
    """
    try:
        ws_uuid = uuid.UUID(auth_workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id from token")

    today = _date.today()
    report = (
        db.query(SessionReport)
        .filter(
            SessionReport.workspace_id == ws_uuid,
            SessionReport.developer_email == body.developer_email,
            SessionReport.created_at
            >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
        )
        .first()
    )
    created = report is None
    if report is None:
        report = SessionReport(
            workspace_id=ws_uuid, developer_email=body.developer_email
        )
        db.add(report)

    report.archetype = body.archetype
    report.autonomy_score = body.autonomy_score
    report.planning_ratio = body.planning_ratio
    report.sessions = body.sessions
    report.prompts = body.prompts
    report.commits = body.commits
    report.lines_per_hour = body.lines_per_hour
    report.active_days = body.active_days
    report.tools_json = body.tools_json
    report.report_md = body.report_md
    db.commit()

    db.refresh(report)
    output = _report_to_out(report)
    report_id = str(report.id)
    db.rollback()
    if body.report_md:
        background_tasks.add_task(
            _embed_session_report, report_id, str(ws_uuid), body.report_md
        )

    log.info(
        "session_report.upserted",
        report_id=str(report.id),
        workspace_id=auth_workspace_id,
        developer_email=body.developer_email,
        created=created,
    )

    return output


# ── GET /guard/session-reports/{report_id}/html ───────────────────────────────

_HTML_401 = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>401 — Authentication required</h2>"
    "<p>Pass <code>?token=your-api-key</code> or a Clerk JWT.</p>"
    "</body></html>",
    status_code=401,
)

_HTML_401_INVALID = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>401 — Invalid credentials</h2>"
    "</body></html>",
    status_code=401,
)

_HTML_404 = HTMLResponse(
    "<html><body style='font-family:sans-serif;padding:40px'>"
    "<h2>404 — Report not found</h2>"
    "</body></html>",
    status_code=404,
)




@router.get("/{report_id}/html", response_class=HTMLResponse)
async def get_session_report_html(
    report_id: str,
    token: str | None = Query(None),
    workspace_id: str | None = Query(None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Return a styled HTML view of a session report.

    Auth: accepts ?token= or Authorization: Bearer with a Clerk JWT.
    Workspace isolation is enforced — the report must belong to the
    authenticated workspace.
    """
    api_key_val = token or (credentials.credentials if credentials else None)
    if not api_key_val:
        return _HTML_401

    # Resolve workspace_id from the credential
    ws_id: str | None = None

    # Clerk JWT path — verify token, then require workspace_id query param
    claims = _verify_clerk_token(api_key_val)
    if not claims:
        return _HTML_401_INVALID
    # Clerk org_id is not a UUID — workspace_id must be passed explicitly
    if not workspace_id:
        return HTMLResponse(
            "<html><body><h1>400</h1><p>Pass ?workspace_id= alongside ?token= for Clerk auth.</p></body></html>",
            status_code=400,
        )
    ws_id = workspace_id

    # Fetch the report, enforcing workspace isolation
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        return _HTML_404

    try:
        ws_uuid = uuid.UUID(ws_id)
    except ValueError:
        return _HTML_401_INVALID

    report = (
        db.query(SessionReport)
        .filter(
            SessionReport.id == report_uuid,
            SessionReport.workspace_id == ws_uuid,
        )
        .first()
    )
    if not report:
        return _HTML_404

    return HTMLResponse(_build_html(report))
