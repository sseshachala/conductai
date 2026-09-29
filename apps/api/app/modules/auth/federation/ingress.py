"""Shared post-authentication boundary for MCP, Gateway and workflow ingress."""
from uuid import UUID, uuid4

from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import resolve_agent_identity_row
from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from .resolver import FederationDenied, resolve

CONNECTION_HEADER = "conduct-federation-connection"
TOKEN_HEADER = "conduct-subject-token"


def provenance(context):
    """Versioned reference-only attribution; no token, subject or mapped claims."""
    return {"schema_version": 1, "request_id": context.request_id,
            "caller_id": str(context.caller.agent_identity_id),
            "principal_id": str(context.principal.principal_id),
            "grant_id": str(context.delegation.grant_id),
            "connection_id": str(context.evidence.connection_id),
            "mapping_version": context.evidence.mapping_version,
            "actions": list(context.delegation.actions), "resources": list(context.delegation.resources),
            "evidence_expires_at": context.evidence.expires_at.isoformat()}


def failure(error, msg_id=None):
    return JSONResponse(status_code=error.status, content={
        "jsonrpc": "2.0", "id": msg_id,
        "error": {"code": -32001, "message": error.code,
                  "data": {"code": error.code, "identity_required": True}},
    })


def tool_failure(error):
    return {"content": [{"type": "text", "text": error.code}], "isError": True,
            "structuredContent": {"code": error.code, "identity_required": True, "status": error.status}}


def authenticate_context(request, workspace_id, token, *, action, resource_type):
    """Called only after the transport's normal caller authentication succeeds."""
    # Phase 3 binds service credentials only; legacy member/OAuth CLI tokens
    # cannot acquire bindings and retain their existing path without extra I/O.
    if not token.startswith("cond_api_"):
        if CONNECTION_HEADER in request.headers or TOKEN_HEADER in request.headers:
            raise FederationDenied("federation_service_caller_required")
        return None
    request_id = str(uuid4())
    with SessionLocal() as db:
        try:
            from app.core.workspace_context import set_workspace_rls
            set_workspace_rls(db, workspace_id)
            selections = request.headers.getlist(CONNECTION_HEADER)
            evidence = request.headers.getlist(TOKEN_HEADER)
            if len(selections) > 1 or len(evidence) > 1:
                raise FederationDenied("federation_ambiguous_evidence", 401)
            try:
                connection = UUID(selections[0]) if selections else None
            except ValueError:
                raise FederationDenied("federation_invalid_connection", 401) from None
            caller = resolve_agent_identity_row(token, db)
            if caller is None:
                raise FederationDenied("federation_caller_inactive", 401)
            if str(caller.workspace_id) != str(workspace_id):
                raise FederationDenied("federation_workspace_mismatch")
            context = resolve(db, workspace=UUID(str(workspace_id)), caller=caller,
                              connection_id=connection, subject_token=evidence[0] if evidence else None,
                              request_id=request_id, action=action)
            if context:
                db.add(AuditLog(workspace_id=context.workspace_id, action="federation.identity.verified",
                                resource_type=resource_type, resource_id=request_id, meta=provenance(context)))
                db.commit()
            return context
        except FederationDenied as error:
            db.rollback()
            try:
                set_workspace_rls(db, workspace_id)
                db.add(AuditLog(workspace_id=UUID(str(workspace_id)), action="federation.identity.denied",
                                resource_type=resource_type, resource_id=request_id,
                                meta={"schema_version": 1, "code": error.code}))
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                raise FederationDenied("federation_storage_unavailable", 503) from None
            raise
        except SQLAlchemyError:
            db.rollback()
            raise FederationDenied("federation_storage_unavailable", 503) from None
