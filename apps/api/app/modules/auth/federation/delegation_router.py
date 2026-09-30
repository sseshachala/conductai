"""Admin-approved external principals and delegations; no delete/downgrade API."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.workspace import Workspace
from app.modules.agent_identity.models import AgentIdentity
from .config import TrustConfig
from .delegation_models import FederationCallerBinding, FederationGrant, FederationPrincipal
from .delegation_schemas import BindingWrite, GrantWrite, PrincipalWrite
from .models import FederationConnection
from .router import admin

router = APIRouter(prefix="/workspaces/{workspace_id}/federation", tags=["federation"])


def owned(db, model, workspace, identifier):
    row = db.query(model).filter(model.workspace_id == workspace, model.id == identifier).first()
    if row is None:
        raise HTTPException(404, detail="federation_resource_not_found")
    return row


def authorize(db, workspace, authenticated):
    if str(workspace) != authenticated:
        raise HTTPException(403, detail="federation_workspace_mismatch")
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace)
    # Serialize creation and updates, including unique caller/principal races.
    db.query(Workspace).filter(Workspace.id == workspace).with_for_update().one()


def save(db, model, identifier, workspace, body, immutable, user, role):
    row = db.query(model).filter(model.workspace_id == workspace, model.id == identifier).first()
    if body.expected_revision != (row.revision if row else 0):
        raise HTTPException(409, detail="federation_revision_conflict")
    values = body.model_dump(exclude={"expected_revision"})
    if model is FederationPrincipal and "display_name" not in body.model_fields_set:
        # Older clients must not clear a name when updating approval status/actions.
        values["display_name"] = row.display_name if row else None
    if model is FederationCallerBinding:
        values["caller_id"] = str(values["caller_id"])
    if row and any(getattr(row, key) != values[key] for key in immutable):
        raise HTTPException(409, detail="federation_binding_is_immutable")
    if row is None:
        row = model(id=identifier, workspace_id=workspace, revision=0)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, list(value) if isinstance(value, tuple) else value)
    row.revision += 1
    db.add(AuditLog(workspace_id=workspace, actor_id=user, actor_role=role,
                    action="federation.authorization.saved", resource_type=model.__tablename__,
                    resource_id=str(identifier), meta={"schema_version": 1, "revision": row.revision,
                                                       "status": row.status, "actions": row.actions}))
    response = {"id": row.id, "revision": row.revision, **values}
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail="federation_binding_conflict") from None
    return response


@router.put("/principals/{principal_id}")
def put_principal(workspace_id: UUID, principal_id: UUID, body: PrincipalWrite,
                  authenticated: str = Depends(get_workspace_id), role: str = Depends(admin),
                  user: str | None = Depends(get_user_id), db: Session = Depends(get_db)):
    authorize(db, workspace_id, authenticated)
    return save(db, FederationPrincipal, principal_id, workspace_id, body,
                ("issuer", "subject", "kind"), user, role)


@router.put("/bindings/{binding_id}")
def put_binding(workspace_id: UUID, binding_id: UUID, body: BindingWrite,
                authenticated: str = Depends(get_workspace_id), role: str = Depends(admin),
                user: str | None = Depends(get_user_id), db: Session = Depends(get_db)):
    authorize(db, workspace_id, authenticated)
    caller = owned(db, AgentIdentity, workspace_id, str(body.caller_id))
    if body.status == "active" and (caller.token_type != "api" or caller.lifecycle_state != "active"):
        raise HTTPException(422, detail="federation_requires_active_service_caller")
    trust = owned(db, FederationConnection, workspace_id, body.connection_id)
    if body.status == "active" and TrustConfig.model_validate(trust.config).status != "active":
        raise HTTPException(422, detail="federation_connection_not_active")
    return save(db, FederationCallerBinding, binding_id, workspace_id, body,
                ("caller_id", "connection_id"), user, role)


@router.put("/grants/{grant_id}")
def put_grant(workspace_id: UUID, grant_id: UUID, body: GrantWrite,
              authenticated: str = Depends(get_workspace_id), role: str = Depends(admin),
              user: str | None = Depends(get_user_id), db: Session = Depends(get_db)):
    authorize(db, workspace_id, authenticated)
    binding = owned(db, FederationCallerBinding, workspace_id, body.binding_id)
    principal = owned(db, FederationPrincipal, workspace_id, body.principal_id)
    trust = owned(db, FederationConnection, workspace_id, binding.connection_id)
    if body.status == "active" and principal.issuer != trust.config["issuer"]:
        raise HTTPException(422, detail="federation_issuer_mismatch")
    if body.status == "active" and body.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, detail="federation_grant_expired")
    if body.status == "active" and not set(body.actions) <= (set(binding.actions) & set(principal.actions)):
        raise HTTPException(422, detail="federation_scope_exceeds_approval")
    return save(db, FederationGrant, grant_id, workspace_id, body,
                ("binding_id", "principal_id"), user, role)
