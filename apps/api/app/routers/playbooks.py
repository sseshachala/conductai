"""
Playbook submission scores — eval harness read/write endpoints.

GET   /playbooks/submissions           — list rows, filterable by ?status=
GET   /playbooks/{slug}/score          — latest row for a slug (404 if none)
PATCH /playbooks/{slug}/submission     — update status (promoted | needs_work | pending)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.playbook_submission import PlaybookSubmission

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_VALID_STATUSES = {"pending", "promoted", "needs_work"}


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


# Static route must come before /{slug}/score to avoid path collision.
@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    status: str | None = Query(default=None, description="Filter by status: pending | promoted | needs_work"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
