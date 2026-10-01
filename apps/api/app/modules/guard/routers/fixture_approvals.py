"""Human-reviewed fixture permissions; never a general rule override."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.guard_fixture_approval import GuardFixtureApproval

router = APIRouter(prefix="/guard/fixture-approvals", tags=["guard-fixtures"])


class FingerprintIn(BaseModel):
    action_digest: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    rule_id: Literal["no-private-key"] = "no-private-key"


class ApprovalIn(FingerprintIn):
    subject_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=500)
    synthetic_reviewed: Literal[True]
    ttl_seconds: int = Field(default=600, ge=60, le=3600)


def _actor(user_id):
    if not user_id:
        raise HTTPException(403, "A mapped user is required for fixture approvals")
    return user_id


def _out(row):
    return {
        "id": str(row.id),
        "subject_id": row.subject_id,
        "action_digest": row.action_digest,
        "rule_id": "no-private-key",
        "approved_by": row.approved_by,
        "reason": row.reason,
        "expires_at": row.expires_at,
        "consumed_at": row.consumed_at,
        "revoked_at": row.revoked_at,
    }


def _audit(db, row, actor, action):
    db.add(
        AuditLog(
            workspace_id=row.workspace_id,
            actor_id=actor,
            action="guard.fixture." + action,
            resource_type="guard_fixture_approval",
            resource_id=str(row.id),
            meta={
                "rule_id": "no-private-key",
                "action_digest": row.action_digest,
                "expires_at": row.expires_at.isoformat(),
            },
        )
    )


@router.post("", status_code=201)
def approve_fixture(
    body: ApprovalIn,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str | None = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    actor = _actor(user_id)
    if not body.reason.strip():
        raise HTTPException(422, "A review reason is required")
    # Approval is for another mapped user, never the reviewing agent itself.
    if actor == body.subject_id:
        raise HTTPException(
            403, "A different workspace administrator must review the fixture"
        )
    from app.models.workspace_user import WorkspaceUser

    member = (
        db.query(WorkspaceUser)
        .filter(
            WorkspaceUser.workspace_id == UUID(workspace_id),
            WorkspaceUser.clerk_user_id == body.subject_id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(404, "Fixture subject is not a workspace member")
    row = GuardFixtureApproval(
        workspace_id=UUID(workspace_id),
        subject_id=body.subject_id,
        approved_by=actor,
        action_digest=body.action_digest,
        reason=body.reason.strip(),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=body.ttl_seconds),
    )
    db.add(row)
    db.flush()
    _audit(db, row, actor, "approved")
    db.commit()
    return _out(row)


@router.get("")
def list_fixtures(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(GuardFixtureApproval)
        .filter(GuardFixtureApproval.workspace_id == UUID(workspace_id))
        .order_by(GuardFixtureApproval.created_at.desc())
        .limit(100)
        .all()
    )
    return [_out(row) for row in rows]


@router.post("/consume")
def consume_fixture(
    body: FingerprintIn,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str | None = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.view")),
    db: Session = Depends(get_db),
):
    actor = _actor(user_id)
    now = datetime.now(timezone.utc)
    row = (
        db.query(GuardFixtureApproval)
        .filter(
            GuardFixtureApproval.workspace_id == UUID(workspace_id),
            GuardFixtureApproval.subject_id == actor,
            GuardFixtureApproval.action_digest == body.action_digest,
            GuardFixtureApproval.expires_at > now,
            GuardFixtureApproval.consumed_at.is_(None),
            GuardFixtureApproval.revoked_at.is_(None),
        )
        .order_by(GuardFixtureApproval.created_at)
        .with_for_update()
        .first()
    )
    now = datetime.now(timezone.utc)
    if row is None or row.expires_at <= now:
        return {"approved": False}
    row.consumed_at = now
    _audit(db, row, actor, "consumed")
    db.commit()
    return {
        "approved": True,
        "id": str(row.id),
        "action_digest": row.action_digest,
        "rule_id": "no-private-key",
    }


@router.post("/{approval_id}/revoke")
def revoke_fixture(
    approval_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str | None = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    actor = _actor(user_id)
    row = (
        db.query(GuardFixtureApproval)
        .filter(
            GuardFixtureApproval.id == approval_id,
            GuardFixtureApproval.workspace_id == UUID(workspace_id),
        )
        .with_for_update()
        .first()
    )
    if row is None:
        raise HTTPException(404, "Fixture approval not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        _audit(db, row, actor, "revoked")
        db.commit()
    return _out(row)
