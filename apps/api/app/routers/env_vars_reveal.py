"""Audited per-field credential reveal (#2054 Phase 1 finisher).

The environment editor's bulk list used to return every decrypted value
in one shot with no audit trail — a mass-reveal endpoint dressed up as
a normal read. The reviewer flagged this in round 1 as a P2. This
module owns the replacement: fetch metadata via ``GET /env-vars/{env_id}``,
then request one value at a time via ``POST .../env-vars/{env_id}/reveal``
which records an audit event with actor, target, and timestamp.

Guardrails:

- Workspace-scoped through ``get_workspace_id`` and gated by
  ``platform.credentials.manage``.
- Environment ownership verified before decryption.
- One field per call. Batch reveals are refused so an audit row exists
  per exposed field.
- Failures (row missing, decrypt errors, requested field not present)
  are recorded in the same audit row so misuse doesn't hide.
- The response body carries only the requested value plus the identity
  the caller already knew; nothing about neighbouring fields leaks.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import audit, get_workspace_id, require_permission
from app.core.crypto import decrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.routers.env_vars_helpers import verify_env_ownership


router = APIRouter(prefix="/credentials", tags=["credentials"])


class RevealRequest(BaseModel):
    handle: str
    field: str


class RevealResponse(BaseModel):
    handle: str
    field: str
    value: str


def _audit_reveal(
    db: Session,
    *,
    workspace_id: str,
    env_id: str,
    handle: str,
    field: str,
    outcome: str,
    integration_id: str | None = None,
) -> None:
    """One audit row per attempt — success and failure both recorded so
    misuse leaves a trail rather than looking like a metadata read."""
    audit(
        db,
        workspace_id,
        "credential.reveal",
        resource_type="integration",
        resource_id=integration_id,
        metadata={
            "handle": handle,
            "field": field,
            "environment_id": env_id,
            "outcome": outcome,
        },
    )


@router.post(
    "/env-vars/{env_id}/reveal",
    response_model=RevealResponse,
)
def reveal_env_var(
    env_id: str,
    body: RevealRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
) -> RevealResponse:
    """Decrypt and return one credential field. Every call is audited.

    The caller supplies ``handle`` + ``field`` — the same identity the
    list endpoint returned. There is no bulk variant on purpose: one
    audit row per exposed field is the whole point.
    """
    verify_env_ownership(db, env_id, workspace_id)

    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
        Integration.handle == body.handle,
    ).first()
    if not row or not row.encrypted_credentials:
        _audit_reveal(
            db,
            workspace_id=workspace_id,
            env_id=env_id,
            handle=body.handle,
            field=body.field,
            outcome="not_found",
        )
        raise HTTPException(status_code=404, detail="Credential not found")

    try:
        creds = decrypt(row.encrypted_credentials) or {}
    except Exception:
        _audit_reveal(
            db,
            workspace_id=workspace_id,
            env_id=env_id,
            handle=body.handle,
            field=body.field,
            outcome="unreadable",
            integration_id=str(row.id),
        )
        raise HTTPException(
            status_code=422,
            detail="Credential ciphertext could not be decrypted; contact an admin.",
        )

    if body.field not in creds:
        _audit_reveal(
            db,
            workspace_id=workspace_id,
            env_id=env_id,
            handle=body.handle,
            field=body.field,
            outcome="field_not_present",
            integration_id=str(row.id),
        )
        raise HTTPException(status_code=404, detail="Field not present on credential")

    value = creds[body.field]
    _audit_reveal(
        db,
        workspace_id=workspace_id,
        env_id=env_id,
        handle=body.handle,
        field=body.field,
        outcome="ok",
        integration_id=str(row.id),
    )
    return RevealResponse(handle=body.handle, field=body.field, value=value)
