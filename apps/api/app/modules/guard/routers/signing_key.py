"""
POST   /workspaces/{workspace_id}/signing-key  — generate or rotate signing key
GET    /workspaces/{workspace_id}/signing-key  — fingerprint metadata only
DELETE /workspaces/{workspace_id}/signing-key  — revoke key
"""
from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import require_permission
from app.core.database import get_db
from app.modules.guard.models import WorkspaceSigningKey

router = APIRouter(prefix="/workspaces/{workspace_id}/signing-key", tags=["guard-signing-key"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class SigningKeyMeta(BaseModel):
    fingerprint: str
    created_at: datetime
    rotated_at: Optional[datetime] = None


class SigningKeyCreated(BaseModel):
    """Returned only at POST time. raw_key is shown once and never stored in plaintext."""
    raw_key: str           # hex-encoded 32-byte key -- write to ~/.conductguard/signing.key
    fingerprint: str
    created_at: datetime
    rotated_at: Optional[datetime] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ws_uuid(workspace_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")


def _fingerprint(key_bytes: bytes) -> str:
    return hashlib.sha256(key_bytes).hexdigest()[:16]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=SigningKeyCreated, status_code=201)
def generate_signing_key(
    workspace_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
):
    """Generate a new signing key or rotate the existing one.

    The raw key bytes are returned exactly once. Pass them to
    `conduct guard install --signing-key <hex>` during developer onboarding.
    Subsequent calls to GET return only the fingerprint.
    """
    ws_uuid = _ws_uuid(workspace_id)
    key_bytes = os.urandom(32)
    fp = _fingerprint(key_bytes)
    now = datetime.now(timezone.utc)

    existing = db.get(WorkspaceSigningKey, ws_uuid)
    if existing:
        existing.key_bytes = key_bytes
        existing.fingerprint = fp
        existing.rotated_at = now
        db.commit()
        db.refresh(existing)
        return SigningKeyCreated(
            raw_key=key_bytes.hex(),
            fingerprint=fp,
            created_at=existing.created_at,
            rotated_at=existing.rotated_at,
        )

    row = WorkspaceSigningKey(
        workspace_id=ws_uuid,
        key_bytes=key_bytes,
        fingerprint=fp,
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SigningKeyCreated(
        raw_key=key_bytes.hex(),
        fingerprint=fp,
        created_at=row.created_at,
        rotated_at=None,
    )


@router.get("", response_model=SigningKeyMeta)
def get_signing_key(
    workspace_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
):
    """Return fingerprint metadata. Never returns key bytes."""
    ws_uuid = _ws_uuid(workspace_id)
    row = db.get(WorkspaceSigningKey, ws_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="No signing key configured for this workspace")
    return SigningKeyMeta(
        fingerprint=row.fingerprint,
        created_at=row.created_at,
        rotated_at=row.rotated_at,
    )


@router.delete("", status_code=204)
def revoke_signing_key(
    workspace_id: str,
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
):
    """Delete the signing key. Future policy sync responses will be unsigned."""
    ws_uuid = _ws_uuid(workspace_id)
    row = db.get(WorkspaceSigningKey, ws_uuid)
    if not row:
        raise HTTPException(status_code=404, detail="No signing key configured for this workspace")
    db.delete(row)
    db.commit()
