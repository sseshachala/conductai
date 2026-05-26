import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role
from app.db.session import get_db
from app.models.conduct_api_key import ConductApiKey

router = APIRouter(prefix="/workspaces/{workspace_id}/api-keys", tags=["api-keys"])

PREFIX = "cond_live_"


def _generate_key() -> tuple[str, str, str]:
    """Return (plaintext, prefix, sha256_hex)."""
    raw       = PREFIX + os.urandom(32).hex()
    prefix    = raw[:20]
    key_hash  = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, key_hash


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ── Schemas ───────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str
    expires_at: Optional[datetime] = None


class ApiKeyOut(BaseModel):
    id:           str
    name:         str
    key_prefix:   str
    role:         str
    created_at:   datetime
    last_used_at: Optional[datetime]
    expires_at:   Optional[datetime]


class ApiKeyCreated(ApiKeyOut):
    key: str  # plaintext — returned once only


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    workspace_id: str,
    user_id:      Annotated[str, Depends(get_user_id)],
    _ws:          str = Depends(get_workspace_id),
    _role:        str = Depends(require_workspace_role("admin", "editor")),
    db:           Session = Depends(get_db),
):
    rows = db.query(ConductApiKey).filter(
        ConductApiKey.workspace_id == workspace_id
    ).order_by(ConductApiKey.created_at.desc()).all()
    return [ApiKeyOut(
        id=r.id, name=r.name, key_prefix=r.key_prefix, role=r.role,
        created_at=r.created_at, last_used_at=r.last_used_at, expires_at=r.expires_at,
    ) for r in rows]


@router.post("", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    workspace_id: str,
    body:         ApiKeyCreate,
    user_id:      Annotated[str, Depends(get_user_id)],
    role:         str = Depends(require_workspace_role("admin")),
    db:           Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    plaintext, prefix, key_hash = _generate_key()

    row = ConductApiKey(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        user_id=user_id,
        name=body.name.strip(),
        key_prefix=prefix,
        key_hash=key_hash,
        role="admin",
        created_at=datetime.now(timezone.utc),
        expires_at=body.expires_at,
    )
    db.add(row)
    db.commit()

    return ApiKeyCreated(
        id=row.id, name=row.name, key_prefix=row.key_prefix, role=row.role,
        created_at=row.created_at, last_used_at=None, expires_at=row.expires_at,
        key=plaintext,
    )


@router.delete("/{key_id}", status_code=204)
def revoke_api_key(
    workspace_id: str,
    key_id:       str,
    _role:        str = Depends(require_workspace_role("admin")),
    db:           Session = Depends(get_db),
):
    row = db.query(ConductApiKey).filter(
        ConductApiKey.id == key_id,
        ConductApiKey.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(row)
    db.commit()
