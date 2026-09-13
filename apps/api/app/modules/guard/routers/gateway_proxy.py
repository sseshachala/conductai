"""Parallel Gateway Proxy surface.

This namespace is intentionally separate from the legacy ``/proxy`` routes.
It reuses the established Guard enforcement core while giving clients a
stable migration target for canonical Gateway Profiles and LiteLLM routing.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from app.core.auth import get_workspace_id
from app.modules.guard.routers.proxy import _proxy


router = APIRouter(prefix="/gateway/v1", tags=["gateway-proxy"])


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
        canonical_profile=True,
    )


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
