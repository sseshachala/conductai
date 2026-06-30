import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import encrypt
from app.core.database import get_db
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

_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4  # show "cond_agt_" + 4 random chars


def _generate_token() -> tuple[str, str]:
    """Return (plaintext, token_prefix_display).

    plaintext  — full token, returned to caller once, never stored.
    prefix     — first _DISPLAY_PREFIX_LEN chars for display (e.g. cond_agt_ab12••••).
    """
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    prefix = raw[:_DISPLAY_PREFIX_LEN]
    return raw, prefix


# ---------------------------------------------------------------------------
# POST / — create
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=AgentIdentityCreated,
    status_code=201,
)
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
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return AgentIdentityCreated(
        id=row.id,
        name=row.name,
        provider=row.provider,
        token_prefix=row.token_prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        token=plaintext,
    )


# ---------------------------------------------------------------------------
# GET / — list
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=list[AgentIdentityOut],
)
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
    return [
        AgentIdentityOut(
            id=r.id,
            name=r.name,
            provider=r.provider,
            token_prefix=r.token_prefix,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# DELETE /{identity_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{identity_id}",
    status_code=204,
)
def delete_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AgentIdentity)
        .filter(
            AgentIdentity.id == identity_id,
            AgentIdentity.workspace_id == workspace_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# POST /{identity_id}/regenerate
# ---------------------------------------------------------------------------

@router.post(
    "/{identity_id}/regenerate",
    response_model=AgentIdentityCreated,
)
def regenerate_agent_identity(
    workspace_id: str,
    identity_id: str,
    _ws: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AgentIdentity)
        .filter(
            AgentIdentity.id == identity_id,
            AgentIdentity.workspace_id == workspace_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent identity not found")

    plaintext, prefix = _generate_token()
    encrypted = encrypt({"token": plaintext})

    row.token_prefix = prefix
    row.token_encrypted = encrypted
    db.commit()
    db.refresh(row)

    return AgentIdentityCreated(
        id=row.id,
        name=row.name,
        provider=row.provider,
        token_prefix=row.token_prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        token=plaintext,
    )
