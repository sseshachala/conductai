"""Gateway adapter for the shared resolver, including server-issued run tokens."""
import hashlib
from datetime import datetime, timezone

from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from .ingress import CONNECTION_HEADER, TOKEN_HEADER, authenticate_context
from .resolver import FederationDenied, recheck


def error_response(error):
    return JSONResponse(status_code=error.status, content={"error": {
        "type": "conduct_federation", "message": error.code, "identity_required": True}})


def prepare_gateway(request, workspace_id, token, internal_key="", operation="inference"):
    try:
        if internal_key.startswith("cond_run_"):
            # Bind propagation to the authenticated token's run, never an arbitrary run header.
            from app.modules.agent_identity.run_token_model import AgentRunToken
            from .workflow import load_run_context
            with SessionLocal() as db:
                set_workspace_rls(db, workspace_id)
                row = db.query(AgentRunToken).filter(
                    AgentRunToken.workspace_id == workspace_id,
                    AgentRunToken.token_hash == hashlib.sha256(internal_key.encode()).hexdigest(),
                    AgentRunToken.invalidated_at.is_(None), AgentRunToken.expires_at > datetime.now(timezone.utc),
                ).first()
                if row is None:
                    raise FederationDenied("federation_run_token_invalid", 401)
                context = load_run_context(db, workspace_id, row.run_id, "gateway.inference")
                if context:
                    declared = request.headers.get("x-conductai-run-id")
                    if declared and declared != row.run_id:
                        raise FederationDenied("federation_run_mismatch")
                if TOKEN_HEADER in request.headers or CONNECTION_HEADER in request.headers:
                    raise FederationDenied("federation_run_evidence_not_accepted")
        else:
            context = authenticate_context(request, workspace_id, internal_key or token,
                action="gateway.inference", resource_type="gateway_request")
        if context and operation != "inference":
            raise FederationDenied("federation_action_forbidden")
        return context
    except FederationDenied as error:
        return error_response(error)
    except SQLAlchemyError:
        return error_response(FederationDenied("federation_storage_unavailable", 503))


def recheck_gateway(context):
    if context is None:
        return
    try:
        with SessionLocal() as db:
            recheck(db, context, "gateway.inference")
    except SQLAlchemyError:
        raise FederationDenied("federation_storage_unavailable", 503) from None


def delegated_policy_check(check, context):
    """Recheck each v2 target/retry, not merely the first routing decision."""
    if context is None:
        return check
    async def checked(target):
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(recheck_gateway, context)
        return await check(target)
    return checked
