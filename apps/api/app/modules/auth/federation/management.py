"""Admin management projections and connection creation; no credential disclosure."""
from typing import Annotated, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.models.integration import Integration
from app.modules.agent_identity.models import AgentIdentity
from .config import TrustConfig
from .contracts import ContractModel
from .delegation_models import FederationCallerBinding, FederationGrant, FederationPrincipal
from .delegation_router import authorize
from .delegation_schemas import Action, BindingWrite, GrantWrite, PrincipalWrite
from .models import FederationConnection
from .router import ConnectionWrite, admin, output, put_connection

router = APIRouter(prefix="/workspaces/{workspace_id}/federation", tags=["federation"])


def scoped(db, workspace_id, authenticated):
    if str(workspace_id) != authenticated:
        raise HTTPException(403, detail="federation_workspace_mismatch")
    set_workspace_rls(db, workspace_id)


def approval_output(row, schema):
    values = {name: getattr(row, name) for name in schema.model_fields if name != "expected_revision"}
    return {"id": row.id, "revision": row.revision, **values}


@router.get("/overview")
def overview(workspace_id: UUID, authenticated: str = Depends(get_workspace_id),
             _role: str = Depends(admin), db: Session = Depends(get_db)):
    scoped(db, workspace_id, authenticated)
    connections = db.query(FederationConnection, Integration.handle).join(
        Integration, (Integration.id == FederationConnection.integration_id)
        & (Integration.workspace_id == FederationConnection.workspace_id),
    ).filter(FederationConnection.workspace_id == workspace_id).order_by(FederationConnection.created_at).all()
    result = {"connections": [{**output(row).model_dump(mode="json"), "name": name} for row, name in connections],
              "actions": list(get_args(Action))}
    for key, model, schema in (("principals", FederationPrincipal, PrincipalWrite),
                               ("bindings", FederationCallerBinding, BindingWrite),
                               ("grants", FederationGrant, GrantWrite)):
        result[key] = [approval_output(row, schema) for row in db.query(model).filter(
            model.workspace_id == workspace_id).order_by(model.id).all()]
    callers = db.query(AgentIdentity.id, AgentIdentity.name).filter(
        AgentIdentity.workspace_id == workspace_id, AgentIdentity.token_type == "api",
        AgentIdentity.lifecycle_state == "active").order_by(AgentIdentity.name).all()
    result["callers"] = [{"id": row.id, "name": row.name} for row in callers]
    return result


class ConnectionCreate(ContractModel):
    name: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^\S(?:.*\S)?$")]
    config: TrustConfig


@router.post("/connections", status_code=201)
def create_connection(workspace_id: UUID, body: ConnectionCreate,
                      authenticated: str = Depends(get_workspace_id), role: str = Depends(admin),
                      user: str | None = Depends(get_user_id), db: Session = Depends(get_db)):
    authorize(db, workspace_id, authenticated)
    if body.config.status != "draft":
        raise HTTPException(422, detail="federation_create_as_draft")
    if db.query(Integration.id).filter(Integration.workspace_id == workspace_id,
                                      Integration.handle == body.name).first():
        raise HTTPException(409, detail="federation_name_conflict")
    integration = Integration(workspace_id=workspace_id, handle=body.name,
                              service="identity_federation", auth_method="oidc")
    db.add(integration)
    db.flush()
    # Reuse revision handling, config validation and audit; one atomic commit.
    return put_connection(workspace_id, integration.id, ConnectionWrite(expected_revision=0, config=body.config),
                          authenticated, role, user, db)
