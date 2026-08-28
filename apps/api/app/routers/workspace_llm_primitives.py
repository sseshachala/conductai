"""Workspace LLM Model Primitives — GET/PUT config for one workspace.

See #1347. Config-only; API keys stay in Vault.

tier_map is nested by provider so switching preferred_provider does not
overwrite the other providers\' tier configs:

    {
      "anthropic": {"cheap": "...", "balanced": "...", "smart": "..."},
      "openai":    {"cheap": "...", "balanced": "...", "smart": "..."},
      ...
    }
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives

router = APIRouter(prefix="/workspaces", tags=["workspace-llm-primitives"])

DEFAULT_PREFERRED_PROVIDER = "anthropic"
SUPPORTED_PROVIDERS = {"anthropic", "openai", "perplexity", "together"}
SUPPORTED_TIERS = {"cheap", "balanced", "smart"}

# Anthropic uses native Claude models. Everything else speaks OpenAI protocol
# (openai, perplexity, together via OpenAI-compat) so the same GPT tier map
# is a sensible starting default; users tune from there.
ANTHROPIC_TIER_MAP: dict[str, str] = {
    "cheap":    "claude-haiku-4-5-20251001",
    "balanced": "claude-sonnet-4-6",
    "smart":    "claude-opus-4-7",
}
OPENAI_COMPAT_TIER_MAP: dict[str, str] = {
    "cheap":    "gpt-4.1-mini",
    "balanced": "gpt-4.1",
    "smart":    "gpt-4.1",
}

DEFAULT_TIER_MAPS: dict[str, dict[str, str]] = {
    "anthropic": dict(ANTHROPIC_TIER_MAP),
    "openai":    dict(OPENAI_COMPAT_TIER_MAP),
}


def tier_map_defaults_for(provider: str) -> dict[str, str]:
    """Return the seed tier map for a provider we have not seen yet."""
    if provider == "anthropic":
        return dict(ANTHROPIC_TIER_MAP)
    return dict(OPENAI_COMPAT_TIER_MAP)


class LLMPrimitivesOut(BaseModel):
    preferred_provider: str
    tier_map: dict[str, dict[str, str]]
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class LLMPrimitivesUpdate(BaseModel):
    preferred_provider: str = Field(..., min_length=1)
    tier_map: dict[str, dict[str, str]] = Field(default_factory=dict)


def _read_stored(raw: Any) -> dict[str, dict[str, str]]:
    """Coerce the JSONB payload back into {provider: {tier: model}}."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for provider, tiers in raw.items():
        if not isinstance(tiers, dict):
            continue
        cleaned = {k: v for k, v in tiers.items() if isinstance(v, str) and v.strip()}
        if cleaned:
            out[provider] = cleaned
    return out


def _defaults() -> LLMPrimitivesOut:
    return LLMPrimitivesOut(
        preferred_provider=DEFAULT_PREFERRED_PROVIDER,
        tier_map={k: dict(v) for k, v in DEFAULT_TIER_MAPS.items()},
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
        tier_map=_read_stored(row.tier_map),
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

    cleaned: dict[str, dict[str, str]] = {}
    for prov, tiers in body.tier_map.items():
        prov_key = str(prov).strip().lower()
        if prov_key not in SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=422,
                detail=f"tier_map provider {prov_key!r} must be one of {sorted(SUPPORTED_PROVIDERS)}",
            )
        prov_tiers: dict[str, str] = {}
        for tier, model in (tiers or {}).items():
            if tier not in SUPPORTED_TIERS:
                raise HTTPException(
                    status_code=422,
                    detail=f"tier_map[{prov_key}] key {tier!r} must be one of {sorted(SUPPORTED_TIERS)}",
                )
            if not isinstance(model, str) or not model.strip():
                continue
            prov_tiers[tier] = model.strip()
        if prov_tiers:
            cleaned[prov_key] = prov_tiers

    row = db.get(WorkspaceLLMPrimitives, scoped_ws_id)
    if row is None:
        row = WorkspaceLLMPrimitives(
            workspace_id=scoped_ws_id,
            preferred_provider=provider,
            tier_map=cleaned,
        )
        db.add(row)
    else:
        row.preferred_provider = provider
        row.tier_map = cleaned
    db.commit()
    db.refresh(row)
    return LLMPrimitivesOut(
        preferred_provider=row.preferred_provider,
        tier_map=_read_stored(row.tier_map),
        updated_at=row.updated_at,
    )
