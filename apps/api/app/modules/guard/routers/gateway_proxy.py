"""Parallel Gateway Proxy surface.

This namespace is intentionally separate from the legacy ``/proxy`` routes.
It reuses the established Guard enforcement core while giving clients a
stable migration target for canonical Gateway Profiles and LiteLLM routing.
"""
from __future__ import annotations

import time

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, resolve_agent_token, token_is_expired
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.guard.audit import record as _record_audit
from app.modules.guard.gateway_runtime import TransportResolver
from app.modules.guard.gateway_handler import handle_gateway_request

# Test and extension seam retained under the old private name; this now points
# at the neutral canonical handler rather than importing the legacy router.
_proxy = handle_gateway_request

router = APIRouter(prefix="/gateway/v1", tags=["gateway-proxy"])


def _gateway_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[str, str, str | None]:
    """Authenticate either credential header emitted by Claude Code.

    Returns (workspace_id, clerk_user_id, agent_identity_id). The identity
    id is None for legacy guard-mt-* member tokens; audit rows for those
    calls will land with agent_identity_id NULL (see #1959 Phase 0).
    """
    raw = request.headers.get("x-api-key") or request.headers.get("authorization", "")
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Gateway credential required")

    identity = resolve_agent_token(raw, db)
    if not identity:
        detail = (
            "Gateway credential expired"
            if token_is_expired(raw, db)
            else "Invalid gateway credential"
        )
        raise HTTPException(status_code=401, detail=detail)

    workspace_id, clerk_user_id = identity
    requested_workspace = (
        request.headers.get("x-conductai-workspace-id")
        or request.headers.get("x-workspace-id")
    )
    if requested_workspace and requested_workspace != workspace_id:
        raise HTTPException(
            status_code=403,
            detail="Gateway credential does not belong to the requested workspace",
        )
    set_workspace_rls(db, workspace_id)
    # #1959 Phase 0 — resolve the identity row so audit rows for gateway
    # model-catalog / count-tokens paths carry agent_identity_id. Falls
    # back to None for legacy tokens without an identity row.
    _identity_id = None
    try:
        from app.core.auth import resolve_agent_identity_row as _rair
        _ai_row = _rair(raw, db)
        if _ai_row:
            _identity_id = str(getattr(_ai_row, "id", None) or "") or None
    except Exception:
        pass
    return workspace_id, clerk_user_id, _identity_id


def _anthropic_catalog(profile, limit: int) -> list[dict[str, str]]:
    """Return only models explicitly exposed by the selected Gateway Profile."""
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for deployment in profile.deployments if profile else ():
        model_id = deployment.model.strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        entry = {"id": model_id}
        if deployment.alias != model_id:
            entry["display_name"] = deployment.alias
        catalog.append(entry)
        if len(catalog) >= limit:
            break
    return catalog


@router.get("/openai/v1/models")
async def gateway_openai_models(
    _workspace_id: str = Depends(get_workspace_id),
) -> JSONResponse:
    """Let Codex retain its bundled model catalog for this custom provider.

    Codex expects its own rich ``{"models": [...]}`` schema here, not the
    public OpenAI ``/v1/models`` response. An empty successful catalog is the
    documented merge signal for Codex's bundled metadata and requires no
    upstream provider credential.
    """
    return JSONResponse(
        content={"models": []},
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/anthropic/v1/messages")
async def gateway_anthropic(request: Request, background: BackgroundTasks):
    return await _proxy(
        request,
        background,
        provider="anthropic",
        upstream_path="/v1/messages",
        auth_header_in="x-api-key",
        auth_header_out="x-api-key",
        auth_header_fallback="authorization",
        canonical_profile=True,
    )


@router.post("/anthropic/v1/messages/count_tokens")
async def gateway_anthropic_count_tokens(
    request: Request,
    background: BackgroundTasks,
):
    return await _proxy(
        request,
        background,
        provider="anthropic",
        upstream_path="/v1/messages/count_tokens",
        auth_header_in="x-api-key",
        auth_header_out="x-api-key",
        auth_header_fallback="authorization",
        canonical_profile=True,
        operation="token_count",
    )


@router.get("/anthropic/v1/models")
async def gateway_anthropic_models(
    request: Request,
    background: BackgroundTasks,
    limit: int = Query(default=1000, ge=1, le=1000),
    principal: tuple[str, str, str | None] = Depends(_gateway_principal),
    db: Session = Depends(get_db),
) -> JSONResponse:
    started = time.monotonic()
    workspace_id, clerk_user_id, agent_identity_id = principal
    environment_id = request.headers.get("x-conductai-environment-id") or None
    profile = TransportResolver().resolve_profile(
        db,
        workspace_id,
        "anthropic",
        environment_id,
    )
    data = _anthropic_catalog(profile, limit)
    background.add_task(
        _record_audit,
        workspace_id,
        clerk_user_id,
        "claude-code",
        "anthropic",
        "model-catalog",
        "allowed",
        None,
        int((time.monotonic() - started) * 1000),
        body={},
        response_bytes=b"{}",
        prompt_summary="Gateway model catalog",
        routing_meta={"operation": "model_catalog", "billable": False},
        agent_identity_id=agent_identity_id,
        route=request.url.path,
    )
    return JSONResponse(
        content={"data": data},
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.head("/anthropic/api/hello", status_code=204)
async def gateway_anthropic_hello() -> Response:
    return Response(status_code=204)


@router.post("/openai/v1/chat/completions")
async def gateway_openai(request: Request, background: BackgroundTasks):
    return await _proxy(
        request,
        background,
        provider="openai",
        upstream_path="/v1/chat/completions",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
        canonical_profile=True,
    )


@router.post("/openai/v1/responses")
async def gateway_openai_responses(request: Request, background: BackgroundTasks):
    return await _proxy(
        request,
        background,
        provider="openai",
        upstream_path="/v1/responses",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
        canonical_profile=True,
    )


@router.post("/perplexity/chat/completions")
async def gateway_perplexity(request: Request, background: BackgroundTasks):
    return await _proxy(
        request,
        background,
        provider="perplexity",
        upstream_path="/chat/completions",
        auth_header_in="authorization",
        auth_header_out="authorization",
        bearer=True,
        canonical_profile=True,
    )
