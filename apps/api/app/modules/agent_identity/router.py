import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.modules.agent_identity.adapters import TOKEN_PREFIX
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.schemas import (
    AgentIdentityCreate,
    AgentIdentityCreated,
    AgentIdentityOut,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/agent-identities",
    tags=["agent-identities"],
)

_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4


def _generate_token() -> tuple[str, str]:
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    return raw, raw[:_DISPLAY_PREFIX_LEN]


def _write_token_to_env(db: Session, workspace_id: str, environment_id: str, plaintext: str) -> None:
    """Upsert CONDUCT_AGENT_TOKEN into the environment's credentials."""
    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "CONDUCT_AGENT_TOKEN",
        Integration.environment_id == environment_id,
    ).first()

    if existing:
        existing.encrypted_credentials = encrypt({"value": plaintext})
    else:
        stmt = (
            pg_insert(Integration)
            .values(
                workspace_id=workspace_id,
                service="agent_identity",
                handle="CONDUCT_AGENT_TOKEN",
                auth_method="api_key",
                encrypted_credentials=encrypt({"value": plaintext}),
                environment_id=environment_id,
            )
            .on_conflict_do_update(
                constraint="uq_integrations_workspace_handle_env",
                set_=dict(encrypted_credentials=encrypt({"value": plaintext})),
            )
        )
        db.execute(stmt)
    db.commit()


@router.post("", response_model=AgentIdentityCreated, status_code=201)
def create_agent_identity(
    workspace_id: str,
    body: AgentIdentityCreate,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be empty")

    plaintext, prefix = _generate_token()
    encrypted = encrypt({"token": plaintext})

    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=body.name.strip(),
        provider="conduct",
        token_prefix=prefix,
        token_encrypted=encrypted,
        environment_id=body.environment_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if body.environment_id:
        _write_token_to_env(db, workspace_id, body.environment_id, plaintext)

    return AgentIdentityCreated(
        id=row.id, name=row.name, provider=row.provider,
        token_prefix=row.token_prefix, created_at=row.created_at,
        last_used_at=row.last_used_at, environment_id=row.environment_id,
        token=plaintext,
    )


@router.get("", response_model=list[AgentIdentityOut])
def list_agent_identities(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AgentIdentity)
        .filter(AgentIdentity.workspace_id == workspace_id)
        .order_by(AgentIdentity.created_at.desc())
        .all()
    )
    return [AgentIdentityOut(
        id=r.id, name=r.name, provider=r.provider, token_prefix=r.token_prefix,
        created_at=r.created_at, last_used_at=r.last_used_at, environment_id=r.environment_id,
    ) for r in rows]


@router.delete("/{identity_id}", status_code=204)
def delete_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    db.delete(row)
    db.commit()


@router.post("/{identity_id}/regenerate", response_model=AgentIdentityCreated)
def regenerate_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")

    plaintext, prefix = _generate_token()
    row.token_prefix = prefix
    row.token_encrypted = encrypt({"token": plaintext})
    db.commit()
    db.refresh(row)

    if row.environment_id:
        _write_token_to_env(db, workspace_id, row.environment_id, plaintext)

    return AgentIdentityCreated(
        id=row.id, name=row.name, provider=row.provider,
        token_prefix=row.token_prefix, created_at=row.created_at,
        last_used_at=row.last_used_at, environment_id=row.environment_id,
        token=plaintext,
    )
