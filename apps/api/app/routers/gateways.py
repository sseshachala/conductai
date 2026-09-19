"""Workspace-scoped canonical Gateway Profile API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.core.credentials import get_credential
from app.models.gateway_profile import GatewayProfile as GatewayProfileRow
from app.models.integration import Integration
from app.core.crypto import decrypt, encrypt
from app.modules.guard.gateway_config import GatewayProfile as GatewayProfileConfig
from app.modules.guard.gateway_config import LiteLLMOptions
from app.modules.guard.gateway_credentials import resolve_gateway_key
from app.modules.guard.gateway_config import profile_from_legacy

router = APIRouter(prefix="/workspaces", tags=["gateway-profiles"])


class GatewayProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    protocol: str
    upstream_url: str | None = None
    credential_ref: str | None = None
    environment_id: str | None = None
    deployments: list[dict[str, Any]] = Field(default_factory=list)
    routing: dict[str, Any] = Field(default_factory=dict)
    reliability: dict[str, Any] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    streaming: dict[str, Any] = Field(default_factory=dict)
    litellm: LiteLLMOptions = Field(default_factory=LiteLLMOptions)
    provider_options: dict[str, Any] = Field(default_factory=dict)


class GatewayProfileOut(GatewayProfileInput):
    id: str | None = None
    schema_version: int = 1
    created_at: str | None = None
    updated_at: str | None = None


class GatewayProfilePushInput(BaseModel):
    environment_id: str


def _config_from_body(body: GatewayProfileInput) -> GatewayProfileConfig:
    return GatewayProfileConfig.model_validate(body.model_dump())


def _output(row: GatewayProfileRow) -> GatewayProfileOut:
    stored = {"name": row.name, "environment_id": str(row.environment_id) if row.environment_id else None, **(row.config or {})}
    return GatewayProfileOut(
        id=str(row.id),
        schema_version=int(row.schema_version),
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        **GatewayProfileConfig.model_validate(stored).model_dump(exclude={"schema_version"}),
    )


def _legacy_profile(db: Session, workspace_id: str) -> GatewayProfileConfig:
    from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives
    from app.core.credentials import get_credential

    primitives = db.get(WorkspaceLLMPrimitives, workspace_id)
    proxy: dict[str, Any] = {}
    try:
        proxy = get_credential(db, workspace_id, "proxy_config") or {}
    except Exception:
        pass
    return profile_from_legacy(
        proxy_config={"LLM_UPSTREAM": proxy.get("LLM_UPSTREAM"), "credential_ref": proxy.get("credential_ref")},
        llm_primitives=(
            {"preferred_provider": primitives.preferred_provider, "tier_map": primitives.tier_map}
            if primitives else None
        ),
    )


@router.get("/{workspace_id}/gateways", response_model=list[GatewayProfileOut])
def list_gateways(
    workspace_id: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    rows = db.query(GatewayProfileRow).filter(GatewayProfileRow.workspace_id == scoped_ws_id).order_by(GatewayProfileRow.name).all()
    if rows:
        return [_output(row) for row in rows]
    legacy = _legacy_profile(db, scoped_ws_id)
    return [GatewayProfileOut(**legacy.model_dump())]


@router.post("/{workspace_id}/gateways", response_model=GatewayProfileOut, status_code=201)
def create_gateway(
    workspace_id: str,
    body: GatewayProfileInput,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    config = _config_from_body(body)
    row = GatewayProfileRow(workspace_id=scoped_ws_id, environment_id=config.environment_id, name=config.name, config=config.model_dump(exclude={"name", "schema_version", "environment_id"}))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A gateway with this name already exists for the environment")
    db.refresh(row)
    return _output(row)


@router.put("/{workspace_id}/gateways/{gateway_id}", response_model=GatewayProfileOut)
def update_gateway(
    workspace_id: str,
    gateway_id: str,
    body: GatewayProfileInput,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    row = db.query(GatewayProfileRow).filter(GatewayProfileRow.id == gateway_id, GatewayProfileRow.workspace_id == scoped_ws_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Gateway profile not found")
    config = _config_from_body(body)
    row.name = config.name
    row.environment_id = config.environment_id
    row.config = config.model_dump(exclude={"name", "schema_version", "environment_id"})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A gateway with this name already exists for the environment")
    db.refresh(row)
    return _output(row)


@router.delete("/{workspace_id}/gateways/{gateway_id}", status_code=204)
def delete_gateway(
    workspace_id: str,
    gateway_id: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    row = db.query(GatewayProfileRow).filter(GatewayProfileRow.id == gateway_id, GatewayProfileRow.workspace_id == scoped_ws_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Gateway profile not found")
    db.delete(row)
    db.commit()


@router.post("/{workspace_id}/gateways/validate")
def validate_gateway(
    workspace_id: str,
    body: GatewayProfileInput,
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    _config_from_body(body)
    return {"valid": True, "warnings": []}


@router.post("/{workspace_id}/gateways/{gateway_id}/push")
def push_gateway(
    workspace_id: str,
    gateway_id: str,
    body: GatewayProfilePushInput,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Project a canonical profile into an environment's encrypted env vars."""
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    row = db.query(GatewayProfileRow).filter(
        GatewayProfileRow.id == gateway_id,
        GatewayProfileRow.workspace_id == scoped_ws_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Gateway profile not found")
    config = GatewayProfileConfig.model_validate({"name": row.name, "environment_id": row.environment_id, **(row.config or {})})
    if not config.upstream_url:
        raise HTTPException(status_code=422, detail="Gateway profile has no upstream URL")

    # Resolve the referenced Vault handle without persisting or returning its value.
    upstream_key = resolve_gateway_key(
        db, scoped_ws_id, config.credential_ref, config.provider, body.environment_id,
    )

    ev_row = db.query(Integration).filter(
        Integration.workspace_id == scoped_ws_id,
        Integration.handle == "env_vars",
        Integration.environment_id == body.environment_id,
    ).first()
    ev_creds: dict[str, Any] = {}
    if ev_row and ev_row.encrypted_credentials:
        ev_creds = decrypt(ev_row.encrypted_credentials) or {}
    ev_creds["PROXY_CONFIG_LLM_UPSTREAM"] = config.upstream_url
    if upstream_key:
        ev_creds["PROXY_CONFIG_LLM_UPSTREAM_API_KEY"] = upstream_key
    encrypted = encrypt(ev_creds)
    if ev_row:
        # bump_encrypted preserves the concurrency contract: any editor
        # holding a stale revision is refused on its next save.
        from app.core.integration_writer import bump_encrypted
        bump_encrypted(ev_row, encrypted)
    else:
        db.add(Integration(
            workspace_id=scoped_ws_id,
            service="env_vars",
            handle="env_vars",
            auth_method="api_key",
            encrypted_credentials=encrypted,
            environment_id=body.environment_id,
        ))
    db.commit()
    return {"pushed": True, "credential_resolved": bool(upstream_key), "environment_id": body.environment_id}


@router.get("/{workspace_id}/gateways/{gateway_id}", response_model=GatewayProfileOut)
def get_gateway(
    workspace_id: str,
    gateway_id: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    row = db.query(GatewayProfileRow).filter(GatewayProfileRow.id == gateway_id, GatewayProfileRow.workspace_id == scoped_ws_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Gateway profile not found")
    return _output(row)
