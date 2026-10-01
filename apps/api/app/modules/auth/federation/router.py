"""Admin-only draft trust configuration. No runtime enable or token test endpoint."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.integration import Integration
from .config import TrustConfig
from .contracts import ContractModel
from .models import FederationConnection

router = APIRouter(prefix="/workspaces/{workspace_id}/integrations/{integration_id}/federation", tags=["federation"])
admin = require_permission("platform.workspace.edit")


class ConnectionWrite(ContractModel):
    expected_revision: int = Field(ge=0, strict=True)
    config: TrustConfig


class ConnectionOut(ContractModel):
    id: UUID
    workspace_id: UUID
    integration_id: UUID
    revision: int
    config: TrustConfig


def scoped_integration(db: Session, workspace_id: UUID, integration_id: UUID, authenticated_workspace: str, *, lock=False):
    if str(workspace_id) != authenticated_workspace:
        raise HTTPException(403, detail="federation_workspace_mismatch")
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    query = db.query(Integration).filter(Integration.id == integration_id, Integration.workspace_id == workspace_id)
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(404, detail="integration_not_found")
    return row


def connection(db: Session, workspace_id: UUID, integration_id: UUID):
    return db.query(FederationConnection).filter(
        FederationConnection.workspace_id == workspace_id,
        FederationConnection.integration_id == integration_id,
        FederationConnection.authentication_mode == "delegated",
    ).first()


def output(row: FederationConnection) -> ConnectionOut:
    return ConnectionOut(id=row.id, workspace_id=row.workspace_id, integration_id=row.integration_id,
                         revision=row.revision, config=TrustConfig.model_validate(row.config))


@router.get("", response_model=ConnectionOut)
def get_connection(workspace_id: UUID, integration_id: UUID,
                   authorized_workspace: str = Depends(get_workspace_id),
                   _role: str = Depends(admin), db: Session = Depends(get_db)):
    scoped_integration(db, workspace_id, integration_id, authorized_workspace)
    row = connection(db, workspace_id, integration_id)
    if not row:
        raise HTTPException(404, detail="federation_not_configured")
    return output(row)


@router.post("/validate")
def validate_connection(workspace_id: UUID, integration_id: UUID, body: ConnectionWrite,
                        authorized_workspace: str = Depends(get_workspace_id),
                        _role: str = Depends(admin), db: Session = Depends(get_db)):
    from .network import VerificationUnavailable
    from .verifier import InvalidIdentity, KeyCache
    scoped_integration(db, workspace_id, integration_id, authorized_workspace)
    row = connection(db, workspace_id, integration_id)
    if not row or row.revision != body.expected_revision or row.config != body.config.model_dump(mode="json"):
        raise HTTPException(409, detail="federation_revision_conflict")
    try:
        count = KeyCache().key(workspace_id, row.id, row.revision, body.config, None)
    except (VerificationUnavailable, InvalidIdentity) as error:
        raise HTTPException(422, detail=str(error)) from None
    return {"revision": row.revision, "signing_keys": count, "validated_at": datetime.now(timezone.utc)}


@router.put("", response_model=ConnectionOut)
def put_connection(workspace_id: UUID, integration_id: UUID, body: ConnectionWrite,
                   authorized_workspace: str = Depends(get_workspace_id),
                   role: str = Depends(admin), user_id: str | None = Depends(get_user_id),
                   db: Session = Depends(get_db)):
    # Lock the existing parent even for the first save, preventing create races.
    scoped_integration(db, workspace_id, integration_id, authorized_workspace, lock=True)
    row = connection(db, workspace_id, integration_id)
    current = row.revision if row else 0
    if current != body.expected_revision:
        raise HTTPException(409, detail="federation_revision_conflict")
    if row is None:
        row = FederationConnection(workspace_id=workspace_id, integration_id=integration_id)
        db.add(row)
    row.revision = current + 1
    row.config = body.config.model_dump(mode="json")
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.add(AuditLog(workspace_id=workspace_id, actor_id=user_id, actor_role=role,
                    action="federation.config.saved", resource_type="federation_connection",
                    resource_id=str(row.id), meta={"revision": row.revision, "status": body.config.status}))
    response = output(row)
    db.commit()
    return response
