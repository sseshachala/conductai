"""
Playbook submission scores — eval harness read/write endpoints.

POST  /playbooks/submit                — community YAML submission (auth or reCAPTCHA)
GET   /playbooks/submissions           — list rows, filterable by ?status=
GET   /playbooks/{slug}/score          — latest row for a slug (404 if none)
PATCH /playbooks/{slug}/submission     — update status (promoted | needs_work | pending)
"""
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.config import settings
from app.core.database import get_db
from app.models.playbook_submission import PlaybookSubmission

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_VALID_STATUSES = {"pending", "promoted", "needs_work"}
_RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def _verify_recaptcha(token: str) -> bool:
    """Return True if the reCAPTCHA v3 token is valid and score >= threshold."""
    if not settings.recaptcha_secret_key:
        return True  # dev mode — skip verification when key not configured
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(_RECAPTCHA_VERIFY_URL, data={
            "secret": settings.recaptcha_secret_key,
            "response": token,
        })
    data = resp.json()
    return data.get("success") and float(data.get("score", 0)) >= settings.recaptcha_min_score


class PlaybookSubmitBody(BaseModel):
    yaml_content: str
    recaptcha_token: str | None = None  # required for unauthenticated submissions
    submitter_email: str | None = None  # optional, shown in admin queue


class SubmitOut(BaseModel):
    id: str
    slug: str
    status: str
    message: str


class SubmissionOut(BaseModel):
    slug: str
    source: str
    structural_score: int
    quality_score: int
    grade: str
    status: str
    eval_run_at: datetime
    notes: str | None = None

    class Config:
        from_attributes = True


class SubmissionPatch(BaseModel):
    status: str  # promoted | needs_work | pending


@router.post("/submit", response_model=SubmitOut, status_code=201)
async def submit_playbook(
    body: PlaybookSubmitBody,
    db: Session = Depends(get_db),
    authorization: Annotated[str | None, Header()] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
):
    """
    Community playbook submission.
    - Logged-in users: Authorization header validates identity (no captcha needed).
    - Anonymous users: recaptcha_token must be provided and score >= threshold.
    """
    from app.core.auth import _verify_clerk_token, _clerk_enabled
    from app.dsl.loader import load_workflow_yaml

    # ── Determine submitter identity ──────────────────────────────────────────
    workspace_id: str | None = None
    submitter_email: str | None = body.submitter_email

    is_authenticated = False
    if authorization and authorization.startswith("Bearer ") and _clerk_enabled():
        claims = _verify_clerk_token(authorization.split(" ", 1)[1])
        if claims:
            is_authenticated = True
            workspace_id = x_workspace_id or claims.get("org_id")

    if not is_authenticated:
        # Anonymous path — require a valid reCAPTCHA token
        if not body.recaptcha_token:
            raise HTTPException(status_code=401, detail="recaptcha_token required for unauthenticated submissions")
        if not await _verify_recaptcha(body.recaptcha_token):
            raise HTTPException(status_code=403, detail="Human verification failed — please try again")

    # ── Validate YAML against the DSL ─────────────────────────────────────────
    try:
        workflow = load_workflow_yaml(body.yaml_content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid playbook YAML: {e}")

    slug = getattr(workflow, "name", None) or "community-submission"
    slug = slug.lower().replace(" ", "-")[:64]

    # ── Store in submissions queue ─────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    row = PlaybookSubmission(
        slug=slug,
        source="community",
        structural_score=0,
        quality_score=0,
        grade="pending",
        status="pending",
        eval_run_at=now,
        yaml_content=body.yaml_content,
        submitter_email=submitter_email,
        submitter_workspace_id=workspace_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return SubmitOut(
        id=str(row.id),
        slug=row.slug,
        status=row.status,
        message="Submission received — our team will review it shortly.",
    )


# Static route must come before /{slug}/score to avoid path collision.
@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    status: str | None = Query(default=None, description="Filter by status: pending | promoted | needs_work"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "security", "viewer")),
):
    """Return all playbook submission rows, optionally filtered by status."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )
    q = db.query(PlaybookSubmission)
    if status:
        q = q.filter(PlaybookSubmission.status == status)
    return q.order_by(PlaybookSubmission.eval_run_at.desc()).all()


@router.get("/{slug}/score", response_model=SubmissionOut)
def get_playbook_score(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "security", "viewer")),
):
    """Return the most recent eval score for a playbook slug. 404 if no row exists."""
    row = (
        db.query(PlaybookSubmission)
        .filter(PlaybookSubmission.slug == slug)
        .order_by(PlaybookSubmission.eval_run_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No submission found for slug '{slug}'")
    return row


@router.patch("/{slug}/submission", response_model=SubmissionOut)
def patch_submission(
    slug: str,
    body: SubmissionPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Update the status of a playbook submission. Admin only."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    row = (
        db.query(PlaybookSubmission)
        .filter(PlaybookSubmission.slug == slug)
        .order_by(PlaybookSubmission.eval_run_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No submission found for slug '{slug}'")

    row.status = body.status
    if body.status == "promoted":
        row.promoted_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
