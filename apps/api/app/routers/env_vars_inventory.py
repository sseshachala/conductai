"""Read-only inventory for legacy ``env_vars`` catch-all rows (#2054 Phase 3).

Discovery-only. The endpoint returns **metadata only** — never credential
values — so an admin can decide which fields to migrate to a proper
provider handle, which are legitimate arbitrary variables (safe as-is),
and which would collide with an existing row on reroute.

Guardrails from the epic:
- Metadata only — field names, suggested reroute, collision flag. No
  values, no fingerprints derived from values, no plaintext in logs.
- No writes. Migration is a separate, admin-approved operation.
- Workspace-scoped through ``get_workspace_id``; cross-tenant reads
  refused via ``require_permission("platform.credentials.manage")``.

The output feeds an operator UI or a scripted migration plan. Any
legitimate custom variable (``MY_CUSTOM_VAR`` etc.) stays in the
``env_vars`` bag — the epic explicitly warns against blindly unpacking
every row.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.routers.env_vars import _ENV_VAR_MAP


router = APIRouter(prefix="/credentials", tags=["credentials"])


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class SuggestedReroute(BaseModel):
    handle: str
    field: str


class CollisionDetail(BaseModel):
    """When rerouting would clash with an existing row."""
    handle: str
    field: str
    existing_integration_id: str
    # Whether the existing row already has this exact field populated
    # (hard collision) or just holds the target handle (soft — the field
    # slot is free, but the row identity contract still needs care).
    field_already_present: bool


class InventoryFieldOut(BaseModel):
    name: str
    suggested_reroute: SuggestedReroute | None
    collision: CollisionDetail | None


class InventoryEnvVarsRowOut(BaseModel):
    integration_id: str
    field_count: int
    fields: list[InventoryFieldOut]


class InventoryEnvironmentOut(BaseModel):
    environment_id: str | None
    environment_name: str | None
    env_vars_rows: list[InventoryEnvVarsRowOut]


class InventoryReport(BaseModel):
    total_env_vars_rows: int
    total_env_vars_fields: int
    reroutable_field_count: int
    unreroutable_field_count: int
    collision_count: int
    environments: list[InventoryEnvironmentOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _target_row_for(
    db: Session,
    workspace_id: str,
    environment_id,
    handle: str,
) -> Integration | None:
    """Look up the row a reroute would land on. May be None if free."""
    return db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == environment_id,
        Integration.handle == handle,
    ).first()


def _decrypt_fields(row: Integration) -> dict[str, str]:
    """Best-effort field-name extraction. Never returns values to callers."""
    if not row.encrypted_credentials:
        return {}
    try:
        blob = decrypt(row.encrypted_credentials) or {}
        return dict(blob) if isinstance(blob, dict) else {}
    except Exception:
        return {}


def _classify_field(
    db: Session,
    workspace_id: str,
    environment_id,
    field_name: str,
) -> tuple[SuggestedReroute | None, CollisionDetail | None]:
    """Suggest a reroute + report any collision. Field names only."""
    mapped = _ENV_VAR_MAP.get(field_name)
    if not mapped:
        # No canonical mapping — legitimate arbitrary variable. Leave in
        # ``env_vars``; the epic explicitly wants this class untouched.
        return None, None
    target_handle, target_field = mapped
    suggestion = SuggestedReroute(handle=target_handle, field=target_field)

    existing = _target_row_for(db, workspace_id, environment_id, target_handle)
    if existing is None:
        return suggestion, None
    existing_fields = _decrypt_fields(existing)
    return suggestion, CollisionDetail(
        handle=target_handle,
        field=target_field,
        existing_integration_id=str(existing.id),
        field_already_present=target_field in existing_fields,
    )


# ---------------------------------------------------------------------------
# GET — inventory across all environments in the workspace
# ---------------------------------------------------------------------------


@router.get("/env-vars/inventory", response_model=InventoryReport)
def inventory_env_vars(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
) -> InventoryReport:
    """Return a metadata-only report of every ``env_vars`` catch-all row.

    Discovery for the #2054 Phase 3 cleanup — surfaces which fields have
    a canonical provider reroute, which don't (legitimate custom vars),
    and which would collide with an existing row on reroute. No values
    are returned or logged.
    """
    from app.models.environment import Environment

    env_vars_rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "env_vars",
    ).order_by(Integration.environment_id, Integration.created_at).all()

    # Cheap env name lookup — a single query beats N per-row queries.
    env_ids = {r.environment_id for r in env_vars_rows if r.environment_id is not None}
    env_name_by_id: dict = {}
    if env_ids:
        for e in db.query(Environment).filter(Environment.id.in_(env_ids)).all():
            env_name_by_id[e.id] = e.name

    per_env: dict = {}
    for row in env_vars_rows:
        env_id = row.environment_id
        bucket = per_env.setdefault(env_id, [])
        fields_out: list[InventoryFieldOut] = []
        for field_name in _decrypt_fields(row):
            suggestion, collision = _classify_field(
                db, workspace_id, env_id, field_name,
            )
            fields_out.append(InventoryFieldOut(
                name=field_name,
                suggested_reroute=suggestion,
                collision=collision,
            ))
        bucket.append(InventoryEnvVarsRowOut(
            integration_id=str(row.id),
            field_count=len(fields_out),
            fields=fields_out,
        ))

    environments = [
        InventoryEnvironmentOut(
            environment_id=str(env_id) if env_id is not None else None,
            environment_name=env_name_by_id.get(env_id),
            env_vars_rows=rows,
        )
        for env_id, rows in per_env.items()
    ]

    total_rows = len(env_vars_rows)
    total_fields = sum(r.field_count for env in environments for r in env.env_vars_rows)
    reroutable = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.suggested_reroute is not None and f.collision is None
    )
    unreroutable = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.suggested_reroute is None
    )
    collisions = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.collision is not None
    )

    return InventoryReport(
        total_env_vars_rows=total_rows,
        total_env_vars_fields=total_fields,
        reroutable_field_count=reroutable,
        unreroutable_field_count=unreroutable,
        collision_count=collisions,
        environments=environments,
    )
