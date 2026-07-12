"""CLI auth endpoints — PKCE exchange → agent_token + refresh_token."""
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id
from app.core.crypto import encrypt
from app.core.database import get_db
from app.modules.agent_identity.adapters import TOKEN_PREFIX
from app.modules.agent_identity.models import AgentIdentity

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_PREFIX = "cond_ref_"
_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4
_AGENT_TOKEN_TTL = timedelta(hours=8)
_REFRESH_TOKEN_TTL = timedelta(days=30)


def _mint_agent_token() -> tuple[str, str]:
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    return raw, raw[: _DISPLAY_PREFIX_LEN]


def _mint_refresh_token() -> tuple[str, str]:
    raw = _REFRESH_PREFIX + os.urandom(32).hex()
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _upsert_identity(
    db: Session, workspace_id: str, clerk_user_id: str
) -> tuple[AgentIdentity, str, str]:
    """Find or create AgentIdentity for this user, rotate agent_token + refresh_token."""
    now = datetime.now(timezone.utc)

    # Find existing identity linked via guard_member_config
    row = db.execute(
        text("""
            SELECT ai.id FROM agent_identities ai
            JOIN guard_member_config gmc ON gmc.agent_identity_id = ai.id
            WHERE gmc.workspace_id = :ws AND gmc.clerk_user_id = :uid
            LIMIT 1
        """),
        {"ws": workspace_id, "uid": clerk_user_id},
    ).fetchone()

    agent_raw, agent_prefix = _mint_agent_token()
    refresh_raw, refresh_hash = _mint_refresh_token()

    if row:
        identity = db.query(AgentIdentity).filter(AgentIdentity.id == row.id).first()
        if not identity:
            raise HTTPException(status_code=500, detail="Agent identity row missing")
        identity.token_prefix = agent_prefix
        identity.token_encrypted = encrypt({"token": agent_raw})
        identity.expires_at = now + _AGENT_TOKEN_TTL
        identity.refresh_token_hash = refresh_hash
        identity.refresh_token_expires_at = now + _REFRESH_TOKEN_TTL
        identity.last_used_at = now
    else:
        identity = AgentIdentity(
            id=str(uuid.uuid4()),
            workspace_id=uuid.UUID(workspace_id),
            name=f"{clerk_user_id} (CLI)",
            provider="conduct",
            token_prefix=agent_prefix,
            token_encrypted=encrypt({"token": agent_raw}),
            environment_id=None,
            created_at=now,
            last_used_at=now,
            expires_at=now + _AGENT_TOKEN_TTL,
            refresh_token_hash=refresh_hash,
            refresh_token_expires_at=now + _REFRESH_TOKEN_TTL,
        )
        db.add(identity)
        db.flush()
        # Link to guard_member_config if it exists
        db.execute(
            text("""
                UPDATE guard_member_config
                SET agent_identity_id = :aid
                WHERE workspace_id = :ws AND clerk_user_id = :uid
            """),
            {"aid": identity.id, "ws": workspace_id, "uid": clerk_user_id},
        )

    db.commit()
    return identity, agent_raw, refresh_raw


class CliTokenResponse(BaseModel):
    agent_token: str
    refresh_token: str
    expires_in: int  # seconds
    workspace_id: str
    user_id: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/cli-token", response_model=CliTokenResponse)
def issue_cli_token(
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Exchange a Clerk JWT (from PKCE flow) for an agent_token + refresh_token."""
    _, agent_raw, refresh_raw = _upsert_identity(db, workspace_id, user_id)
    return CliTokenResponse(
        agent_token=agent_raw,
        refresh_token=refresh_raw,
        expires_in=int(_AGENT_TOKEN_TTL.total_seconds()),
        workspace_id=workspace_id,
        user_id=user_id,
    )


@router.post("/refresh", response_model=CliTokenResponse)
def refresh_cli_token(
    body: RefreshRequest,
    db: Session = Depends(get_db),
):
    """Rotate a refresh_token → new agent_token + new refresh_token (no browser needed)."""
    if not body.refresh_token.startswith(_REFRESH_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    hashed = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.refresh_token_hash == hashed
    ).first()

    if not identity:
        raise HTTPException(status_code=401, detail="Refresh token not found")

    now = datetime.now(timezone.utc)
    if identity.refresh_token_expires_at and identity.refresh_token_expires_at < now:
        raise HTTPException(status_code=401, detail="Refresh token expired — run `conduct login`")

    agent_raw, agent_prefix = _mint_agent_token()
    refresh_raw, refresh_hash = _mint_refresh_token()

    identity.token_prefix = agent_prefix
    identity.token_encrypted = encrypt({"token": agent_raw})
    identity.expires_at = now + _AGENT_TOKEN_TTL
    identity.refresh_token_hash = refresh_hash
    identity.refresh_token_expires_at = now + _REFRESH_TOKEN_TTL
    identity.last_used_at = now
    db.commit()

    return CliTokenResponse(
        agent_token=agent_raw,
        refresh_token=refresh_raw,
        expires_in=int(_AGENT_TOKEN_TTL.total_seconds()),
        workspace_id=str(identity.workspace_id),
        user_id=None,
    )
