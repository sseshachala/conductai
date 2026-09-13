"""Parallel Gateway Proxy surface.

This namespace is intentionally separate from the legacy ``/proxy`` routes.
It reuses the established Guard enforcement core while giving clients a
stable migration target for canonical Gateway Profiles and LiteLLM routing.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request

from app.modules.guard.routers.proxy import _proxy


router = APIRouter(prefix="/gateway/v1", tags=["gateway-proxy"])


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
