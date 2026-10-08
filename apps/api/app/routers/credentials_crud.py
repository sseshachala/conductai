"""Credentials CRUD + reveal endpoints (split from credentials.py).

Owns the shared ``/credentials`` APIRouter. Route registration order is part
of the public contract, so the endpoint modules form an import chain:
credentials_crud -> credentials_integrations -> credentials. Each module
imports ``router`` from its predecessor.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, require_permission, audit
from app.core.credentials import get_credential
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.models.workflow import Workflow


def _credential_field_names(blob: str) -> list[str]:
    """Decrypt a credential blob, return only the field names, and immediately
    discard the plaintext values.

    Used by list endpoints that need to show which fields are present without
    exposing their values.  Decryption is still required (the format doesn't
    have a plaintext envelope), but values are dropped as early as possible.
    """
    creds = decrypt(blob)
    keys = list(creds.keys())
    # Explicitly drop references to plaintext values before returning.
    for k in keys:
        creds[k] = None
    del creds
    return keys

GITHUB_API = "https://api.github.com"
VERCEL_API = "https://api.vercel.com"

router = APIRouter(prefix="/credentials", tags=["credentials"])

KNOWN_SERVICES = {
    "github":       {"fields": ["token"],        "label": "GitHub",       "hint": "Personal access token or OAuth token"},
    "slack":        {"fields": ["token"],        "label": "Slack",        "hint": "Bot OAuth token (xoxb-…)"},
    "linear":       {"fields": ["api_key"],      "label": "Linear",       "hint": "Personal API key from Linear settings"},
    "digitalocean": {"fields": ["token"],        "label": "DigitalOcean", "hint": "Personal access token"},
    "vercel":       {"fields": ["token"],        "label": "Vercel",       "hint": "Personal access token"},
}


class CredentialUpsert(BaseModel):
    service: str
    handle: str                         # short name used in blocks, e.g. "github", "slack-prod"
    credentials: dict                   # raw key/value, will be encrypted
    environment_id: str | None = None   # optional environment scoping


class CredentialOut(BaseModel):
    handle: str
    service: str
    auth_method: str
    fields: list[str]  # field names present (no values)

    class Config:
        from_attributes = True


@router.get("", response_model=list[CredentialOut])
def list_credentials(db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _: str = Depends(require_permission("platform.credentials.manage"))):
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id
    ).order_by(Integration.created_at).all()

    return [
        CredentialOut(
            handle=r.handle,
            service=r.service,
            auth_method=r.auth_method,
            fields=_credential_field_names(r.encrypted_credentials) if r.encrypted_credentials else [],
        )
        for r in rows
    ]


@router.post("", status_code=201)
def upsert_credential(body: CredentialUpsert, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _: str = Depends(require_permission("platform.credentials.manage"))):
    if not body.credentials:
        raise HTTPException(status_code=422, detail="credentials dict must not be empty")

    auth_method = "api_key" if "api_key" in body.credentials else "oauth"

    # Resolve environment: explicit ID > Default environment > error.
    # Always verify workspace ownership of the resolved env, otherwise a
    # cross-workspace environment_id in the payload would write a row
    # against another tenant's environment.
    from app.models.environment import Environment
    if body.environment_id:
        env = db.query(Environment).filter(
            Environment.id == body.environment_id,
            Environment.workspace_id == workspace_id,
        ).first()
        if not env:
            # 404 leaks nothing about whether the env exists elsewhere.
            raise HTTPException(status_code=404, detail="Environment not found")
        env_id = str(env.id)
    else:
        default_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
            Environment.name == "Default",
        ).first()
        if not default_env:
            raise HTTPException(
                status_code=422,
                detail="No Default environment found. Create an environment first in Settings → Environments.",
            )
        env_id = str(default_env.id)

    # Single atomic upsert keyed on the unique constraint
    # uq_integrations_workspace_handle_env — avoids the TOCTOU race where two
    # concurrent saves both see no existing row and both try to INSERT, causing
    # one to fail with a UniqueConstraintViolation 500.
    from sqlalchemy.dialects.postgresql import insert as _pg_insert
    encrypted = encrypt(body.credentials)
    stmt = (
        _pg_insert(Integration)
        .values(
            workspace_id=workspace_id,
            service=body.service,
            handle=body.handle,
            auth_method=auth_method,
            encrypted_credentials=encrypted,
            environment_id=env_id,
        )
        .on_conflict_do_update(
            constraint="uq_integrations_workspace_handle_env",
            set_=dict(
                service=body.service,
                auth_method=auth_method,
                encrypted_credentials=encrypted,
                # Bump revision so any editor holding an older value is
                # refused on its next save. Without this, a rotation via
                # this endpoint is invisible to the env-vars editor's
                # optimistic-concurrency check.
                revision=Integration.revision + 1,
            ),
        )
    )
    db.execute(stmt)
    db.commit()
    audit(db, workspace_id, "credential.upserted",
          resource_type="credential", resource_id=body.handle,
          metadata={"service": body.service, "handle": body.handle})
    return {"handle": body.handle, "service": body.service, "saved": True}


@router.delete("/{handle}", status_code=204)
def delete_credential(handle: str, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _: str = Depends(require_permission("platform.credentials.manage"))):
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == handle,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Block deletion if this integration's environment is assigned to any workflow
    if row.environment_id:
        agents = (
            db.query(Workflow)
            .filter(Workflow.environment_id == row.environment_id)
            .all()
        )
        if agents:
            names = ", ".join(a.name for a in agents)
            raise HTTPException(
                status_code=409,
                detail=f"This credential's environment is used by {len(agents)} agent(s): {names}. Remove the environment from those agents first.",
            )

    service = row.service
    db.delete(row)
    db.commit()
    audit(db, workspace_id, "credential.deleted",
          resource_type="credential", resource_id=handle,
          metadata={"service": service, "handle": handle})


# ---------------------------------------------------------------------------
# Environment-scoped credential listing
# ---------------------------------------------------------------------------

@router.get("/by-environment/{env_id}", response_model=list[CredentialOut])
def list_credentials_by_environment(
    env_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """List credentials scoped to a specific environment."""
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
    ).order_by(Integration.created_at).all()

    return [
        CredentialOut(
            handle=r.handle,
            service=r.service,
            auth_method=r.auth_method,
            fields=_credential_field_names(r.encrypted_credentials) if r.encrypted_credentials else [],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Reveal — decrypt and return credential values (admin only)
# ---------------------------------------------------------------------------

@router.get("/reveal/{handle}")
def reveal_credential(
    handle: str,
    environment_id: str | None = None,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Return decrypted credential fields — admin only. Every access is audit-logged."""
    creds = get_credential(db, workspace_id, handle, environment_id)
    if not creds:
        raise HTTPException(status_code=404, detail="Credential not found")
    audit(db, workspace_id, "credential.revealed",
          resource_type="credential", resource_id=handle,
          metadata={"handle": handle, "environment_id": environment_id})
    return creds
