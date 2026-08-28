"""Workspace LLM Model Primitives — GET/PUT config for one workspace.

See #1347. Config-only; API keys stay in Vault.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives

router = APIRouter(prefix="/workspaces", tags=["workspace-llm-primitives"])

# Defaults returned when a workspace has no row yet. Kept in sync with
# app.runtime.model_router canonical model constants.
DEFAULT_PREFERRED_PROVIDER = "anthropic"
DEFAULT_TIER_MAP: dict[str, str] = {
    "cheap":    "claude-haiku-4-5-20251001",
    "balanced": "claude-sonnet-4-6",
    "smart":    "claude-opus-4-7",
}
SUPPORTED_PROVIDERS = {"anthropic", "openai", "perplexity", "together"}
SUPPORTED_TIERS = {"cheap", "balanced", "smart"}


class LLMPrimitivesOut(BaseModel):
    preferred_provider: str
    tier_map: dict[str, str]
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class LLMPrimitivesUpdate(BaseModel):
    preferred_provider: str = Field(..., min_length=1)
    tier_map: dict[str, str] = Field(default_factory=dict)


def _defaults() -> LLMPrimitivesOut:
    return LLMPrimitivesOut(
        preferred_provider=DEFAULT_PREFERRED_PROVIDER,
        tier_map=dict(DEFAULT_TIER_MAP),
        updated_at=None,
    )


@router.get("/{workspace_id}/llm-primitives", response_model=LLMPrimitivesOut)
def get_llm_primitives(
    workspace_id: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    row = db.get(WorkspaceLLMPrimitives, scoped_ws_id)
    if row is None:
        return _defaults()
    return LLMPrimitivesOut(
        preferred_provider=row.preferred_provider,
        tier_map=row.tier_map or {},
        updated_at=row.updated_at,
    )


@router.put("/{workspace_id}/llm-primitives", response_model=LLMPrimitivesOut)
def put_llm_primitives(
    workspace_id: str,
    body: LLMPrimitivesUpdate,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")

    provider = body.preferred_provider.strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"preferred_provider must be one of {sorted(SUPPORTED_PROVIDERS)}",
        )

    tier_map = {k: v for k, v in body.tier_map.items() if k and v}
    for tier in tier_map:
        if tier not in SUPPORTED_TIERS:
            raise HTTPException(
                status_code=422,
                detail=f"tier_map key {tier!r} must be one of {sorted(SUPPORTED_TIERS)}",
            )

    row = db.get(WorkspaceLLMPrimitives, scoped_ws_id)
    if row is None:
        row = WorkspaceLLMPrimitives(
            workspace_id=scoped_ws_id,
            preferred_provider=provider,
            tier_map=tier_map,
        )
        db.add(row)
    else:
        row.preferred_provider = provider
        row.tier_map = tier_map
    db.commit()
    db.refresh(row)
    return LLMPrimitivesOut(
        preferred_provider=row.preferred_provider,
        tier_map=row.tier_map or {},
        updated_at=row.updated_at,
    )
