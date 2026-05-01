"""
Credentials CRUD — scoped to the dev workspace for now.
POST   /credentials          — upsert a credential by handle
GET    /credentials          — list all (no secret values)
DELETE /credentials/:handle  — remove
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration

router = APIRouter(prefix="/credentials", tags=["credentials"])

DEV_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")

KNOWN_SERVICES = {
    "github":       {"fields": ["token"],        "label": "GitHub",       "hint": "Personal access token or OAuth token"},
    "slack":        {"fields": ["token"],        "label": "Slack",        "hint": "Bot OAuth token (xoxb-…)"},
    "linear":       {"fields": ["api_key"],      "label": "Linear",       "hint": "Personal API key from Linear settings"},
    "digitalocean": {"fields": ["token"],        "label": "DigitalOcean", "hint": "Personal access token"},
    "vercel":       {"fields": ["token"],        "label": "Vercel",       "hint": "Personal access token"},
}


class CredentialUpsert(BaseModel):
    service: str
    handle: str        # short name used in blocks, e.g. "github", "slack-prod"
    credentials: dict  # raw key/value, will be encrypted


class CredentialOut(BaseModel):
    handle: str
    service: str
    auth_method: str
    fields: list[str]  # field names present (no values)

    class Config:
        from_attributes = True


@router.get("", response_model=list[CredentialOut])
def list_credentials(db: Session = Depends(get_db)):
    rows = db.query(Integration).filter(
        Integration.workspace_id == DEV_WORKSPACE
    ).order_by(Integration.created_at).all()

    return [
        CredentialOut(
            handle=r.handle,
            service=r.service,
            auth_method=r.auth_method,
            fields=list(decrypt(r.encrypted_credentials).keys()) if r.encrypted_credentials else [],
        )
        for r in rows
    ]


@router.post("", status_code=201)
def upsert_credential(body: CredentialUpsert, db: Session = Depends(get_db)):
    if not body.credentials:
        raise HTTPException(status_code=422, detail="credentials dict must not be empty")

    existing = db.query(Integration).filter(
        Integration.workspace_id == DEV_WORKSPACE,
        Integration.handle == body.handle,
    ).first()

    service_meta = KNOWN_SERVICES.get(body.service, {})
    auth_method = "api_key" if "api_key" in body.credentials else "oauth"

    if existing:
        existing.service = body.service
        existing.auth_method = auth_method
        existing.encrypted_credentials = encrypt(body.credentials)
    else:
        row = Integration(
            workspace_id=DEV_WORKSPACE,
            service=body.service,
            handle=body.handle,
            auth_method=auth_method,
            encrypted_credentials=encrypt(body.credentials),
        )
        db.add(row)

    db.commit()
    return {"handle": body.handle, "service": body.service, "saved": True}


@router.delete("/{handle}", status_code=204)
def delete_credential(handle: str, db: Session = Depends(get_db)):
    row = db.query(Integration).filter(
        Integration.workspace_id == DEV_WORKSPACE,
        Integration.handle == handle,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(row)
    db.commit()
