"""Persist server-verified initiating identity separately from mutable run state."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.core.workspace_context import set_workspace_rls
from app.models.run import Run, RunEvent
from .contracts import CallingIntegration, DelegatedIdentityContext, DelegationBinding, ExternalPrincipal, VerificationEvidence
from .delegation_models import FederationPrincipal
from .ingress import authenticate_context, provenance
from .models import FederationConnection
from .resolver import FederationDenied, recheck

EVENT_KIND = "federation_initiated"


def prepare_run(request, workspace_id):
    if request is None:  # Direct in-process, non-HTTP callers have no delegated authority.
        return None
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    try:
        # Retain only the approved intersection, so later Gateway use requires
        # its own explicit grant as well as workflows.run.
        context = authenticate_context(request, workspace_id, token, action=None, resource_type="workflow_run")
        if context:
            from app.core.database import SessionLocal
            with SessionLocal() as db:
                recheck(db, context, "workflows.run")
        return context
    except FederationDenied as error:
        raise HTTPException(error.status, detail={"code": error.code, "identity_required": True}) from None
    except SQLAlchemyError:
        raise HTTPException(503, detail={"code": "federation_storage_unavailable", "identity_required": True}) from None


def attach_run(db, run, context):
    if context is None:
        return
    if str(run.workspace_id) != str(context.workspace_id):
        raise FederationDenied("federation_workspace_mismatch")
    recheck(db, context, "workflows.run")
    db.flush()
    # IDs and expiry only: never persist access tokens or IdP claim payloads.
    payload = {**provenance(context), "verified_at": context.evidence.verified_at.isoformat(),
               "audience": context.evidence.audience, "workspace_id": str(context.workspace_id)}
    db.add(RunEvent(run_id=run.id, kind=EVENT_KIND, payload=payload))


def load_run_context(db, workspace_id, run_id, action="workflows.run"):
    """Read trusted RunEvent, not initial_state, output state or caller headers."""
    workspace = UUID(str(workspace_id))
    set_workspace_rls(db, workspace)
    rows = db.query(RunEvent).join(Run, Run.id == RunEvent.run_id).filter(
        Run.workspace_id == workspace, Run.id == run_id, RunEvent.kind == EVENT_KIND,
    ).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise FederationDenied("federation_run_context_invalid")
    try:
        data = rows[0].payload
        if data["workspace_id"] != str(workspace):
            raise ValueError("workspace mismatch")
        principal = db.query(FederationPrincipal).filter(
            FederationPrincipal.workspace_id == workspace, FederationPrincipal.id == data["principal_id"],
        ).one()
        connection = db.query(FederationConnection).filter(
            FederationConnection.workspace_id == workspace, FederationConnection.id == data["connection_id"],
            FederationConnection.authentication_mode == "delegated",
        ).one()
        context = DelegatedIdentityContext(
            mode="delegated", workspace_id=workspace, request_id=data["request_id"], run_id=run_id,
            caller=CallingIntegration(workspace_id=workspace, agent_identity_id=data["caller_id"]),
            principal=ExternalPrincipal(workspace_id=workspace, principal_id=principal.id,
                                        kind=principal.kind, issuer=principal.issuer, subject=principal.subject),
            delegation=DelegationBinding(workspace_id=workspace, grant_id=data["grant_id"],
                caller_agent_identity_id=data["caller_id"], principal_id=principal.id,
                actions=data["actions"], resources=data["resources"]),
            evidence=VerificationEvidence(workspace_id=workspace, connection_id=connection.id,
                issuer=principal.issuer, subject=principal.subject, method="oauth_access_token",
                audience=data["audience"], verified_at=data["verified_at"], expires_at=data["evidence_expires_at"],
                mapping_version=data["mapping_version"]),
        )
    except (KeyError, ValueError, TypeError, SQLAlchemyError):
        raise FederationDenied("federation_run_context_invalid") from None
    recheck(db, context, action)
    return context


def check_run(db, workspace_id, run_id, block_id=None):
    try:
        context = load_run_context(db, workspace_id, run_id)
        if context:
            db.add(RunEvent(run_id=run_id, block_id=block_id, kind="federation_authorized",
                            payload=provenance(context)))
            db.flush()
        return context
    except SQLAlchemyError:
        raise FederationDenied("federation_storage_unavailable", 503) from None
