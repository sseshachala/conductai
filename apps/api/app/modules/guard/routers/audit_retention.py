"""Workspace-scoped hold management and authenticated archive retrieval."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.models.workspace import Workspace
from app.modules.guard.audit_archive import S3ArchiveStore, read_verified_archive
from app.modules.guard.models import GuardAuditArchiveSegment, GuardAuditEvent, GuardAuditRetentionHold

router = APIRouter(prefix="/guard/audit-retention", tags=["guard"])


class HoldIn(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_range(self):
        if self.starts_at.tzinfo is None or (self.ends_at and self.ends_at.tzinfo is None):
            raise ValueError("Hold timestamps must include a timezone")
        if self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("Hold end must not precede its start")
        return self


def _lock_workspace(db, workspace_id):
    set_workspace_rls(db, workspace_id)
    if db.query(Workspace.id).filter(Workspace.id == UUID(str(workspace_id))).with_for_update().first() is None:
        raise HTTPException(404, "workspace_not_found")


@router.get("/holds")
def list_holds(db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id),
               _perm=Depends(require_permission("guard.settings.edit"))):
    return db.query(GuardAuditRetentionHold).filter(
        GuardAuditRetentionHold.workspace_id == UUID(workspace_id),
    ).order_by(GuardAuditRetentionHold.created_at.desc()).limit(1000).all()


@router.post("/holds", status_code=201)
def create_hold(body: HoldIn, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id),
                _perm=Depends(require_permission("guard.settings.edit"))):
    _lock_workspace(db, workspace_id)
    hold = GuardAuditRetentionHold(workspace_id=UUID(workspace_id), **body.model_dump())
    db.add(hold)
    db.commit()
    db.refresh(hold)
    return hold


@router.delete("/holds/{hold_id}")
def release_hold(hold_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id),
                 _perm=Depends(require_permission("guard.settings.edit"))):
    _lock_workspace(db, workspace_id)
    hold = db.query(GuardAuditRetentionHold).filter(
        GuardAuditRetentionHold.id == hold_id, GuardAuditRetentionHold.workspace_id == UUID(workspace_id),
    ).first()
    if hold is None:
        raise HTTPException(404, "hold_not_found")
    hold.active = False
    db.commit()
    return {"released": True}


@router.get("/events/{event_id}")
def archived_event(event_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id),
                   _perm=Depends(require_permission("guard.settings.edit"))):
    row = db.query(GuardAuditEvent).filter(
        GuardAuditEvent.id == event_id, GuardAuditEvent.workspace_id == UUID(workspace_id),
    ).first()
    if row is None or row.archive_segment_id is None:
        raise HTTPException(404, "archived_event_not_found")
    segment = db.query(GuardAuditArchiveSegment).filter(
        GuardAuditArchiveSegment.id == row.archive_segment_id,
        GuardAuditArchiveSegment.workspace_id == UUID(workspace_id),
    ).one()
    manifest, signature = dict(segment.manifest), segment.signature
    # Auth was checked before releasing the request transaction; storage I/O
    # must not consume a pool connection while waiting on an external endpoint.
    db.rollback()
    try:
        rows = read_verified_archive(manifest, signature, settings, S3ArchiveStore(settings), workspace_id=workspace_id)
    except Exception as exc:
        raise HTTPException(503, "archive_unavailable_or_invalid") from exc
    result = next((row for row in rows if row["id"] == str(event_id) and row["workspace_id"] == workspace_id), None)
    if result is None:
        raise HTTPException(503, "archive_event_missing")
    return result
