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

from app.core.auth import _assert_workspace_member, get_user_id, get_workspace_id
from app.core.crypto import encrypt
from app.core.database import get_db
from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity
from app.modules.agent_identity.credentials import SESSION_ACCESS_PREFIX, SESSION_REFRESH_PREFIX, token_hash

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_PREFIX = "cond_ref_"
_DISPLAY_PREFIX_LEN = len(SESSION_ACCESS_PREFIX) + 4
_AGENT_TOKEN_TTL = timedelta(hours=8)
_REFRESH_TOKEN_TTL = timedelta(days=30)


def _mint_agent_token() -> tuple[str, str]:
    raw = SESSION_ACCESS_PREFIX + os.urandom(32).hex()
    return raw, raw[: _DISPLAY_PREFIX_LEN]


def _mint_refresh_token() -> tuple[str, str]:
    raw = SESSION_REFRESH_PREFIX + os.urandom(32).hex()
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def _upsert_identity(
    db: Session, workspace_id: str, clerk_user_id: str
) -> tuple[AgentIdentity, str, str]:
    """Keep the user's identity stable; each authorization gets its own session."""
    _assert_workspace_member(db, workspace_id, clerk_user_id)
    workspace_id = str(uuid.UUID(workspace_id))
    now = datetime.now(timezone.utc)

    # Serialize first-time provisioning as well as issuance for an existing user.
    # The lock lives for this transaction and does not grant membership.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
               {"key": f"credential:{workspace_id}:{clerk_user_id}"})

    # Find existing identity linked via guard_member_config
    row = db.execute(
        text("""
            SELECT ai.id FROM agent_identities ai
            JOIN guard_member_config gmc ON gmc.agent_identity_id = ai.id
            WHERE gmc.workspace_id = :ws AND gmc.clerk_user_id = :uid
              AND ai.workspace_id = :ws
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
        if identity.lifecycle_state in ("deactivated", "expired") or identity.token_type != "cli":
            raise HTTPException(status_code=401, detail="Agent identity is inactive")
        identity.last_used_at = now
    else:
        identity = AgentIdentity(
            id=str(uuid.uuid4()),
            workspace_id=uuid.UUID(workspace_id),
            name=f"{clerk_user_id} (CLI)",
            provider="conduct",
            source="conduct_cli",
            token_prefix=agent_prefix,
            token_encrypted=encrypt({}),
            environment_id=None,
            created_at=now,
            last_used_at=now,
            expires_at=now + _AGENT_TOKEN_TTL,
            token_type="cli",
        )
        db.add(identity)
        db.flush()
        # Upsert GMC row so _resolve_agent_token can find clerk_user_id on first sync
        import secrets as _sec
        db.execute(
            text("""
                INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, agent_identity_id, active, joined_at)
                VALUES (:ws, :uid, :mt, :aid, true, now())
                ON CONFLICT (workspace_id, clerk_user_id) DO UPDATE SET agent_identity_id = EXCLUDED.agent_identity_id
            """),
            {"ws": workspace_id, "uid": clerk_user_id, "mt": _sec.token_hex(32), "aid": identity.id},
        )

    db.add(AgentCredentialSession(
        id=str(uuid.uuid4()), agent_identity_id=identity.id,
        access_token_hash=token_hash(agent_raw), refresh_token_hash=refresh_hash,
        expires_at=now + _AGENT_TOKEN_TTL,
        refresh_token_expires_at=now + _REFRESH_TOKEN_TTL, created_at=now,
    ))
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


def rotate_identity_by_refresh(
    refresh_token: str,
    db: Session,
) -> tuple[AgentIdentity, str, str]:
    """Look up a login by refresh-token hash, rotate only its token pair,
    verify existing workspace membership, and commit.

    Shared by /auth/refresh (CLI, this file) and the OAuth 2.1 refresh_token
    grant (app/modules/auth/oauth/grants/refresh_token.py). Both callers
    accept an opaque cond_ref_* token from the client and issue a fresh
    (access, refresh) pair. Legacy pairs upgrade to a session on first refresh.

    Raises HTTPException(401) on unknown / expired / malformed refresh token.
    """
    if not refresh_token or not refresh_token.startswith(_REFRESH_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    hashed = hashlib.sha256(refresh_token.encode()).hexdigest()
    if refresh_token.startswith(SESSION_REFRESH_PREFIX):
        return _rotate_session(hashed, db)
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.refresh_token_hash == hashed
    ).with_for_update().first()

    if not identity:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    if identity.lifecycle_state in ("deactivated", "expired") or identity.token_type != "cli":
        raise HTTPException(status_code=401, detail="Agent identity is inactive")

    now = datetime.now(timezone.utc)
    if identity.refresh_token_expires_at and identity.refresh_token_expires_at < now:
        raise HTTPException(status_code=401, detail="Refresh token expired — run `conduct login`")

    # A refresh token is not authority to recreate a removed membership.
    gmc = db.execute(
        text("""
            SELECT clerk_user_id FROM guard_member_config
            WHERE agent_identity_id = :aid AND workspace_id = :ws AND active = true
            LIMIT 1
        """),
        {"aid": str(identity.id), "ws": str(identity.workspace_id)},
    ).fetchone()
    if not gmc or not gmc.clerk_user_id:
        raise HTTPException(status_code=401, detail="Refresh token has no linked user")
    _assert_workspace_member(db, str(identity.workspace_id), gmc.clerk_user_id)

    agent_raw, _ = _mint_agent_token()
    refresh_raw, refresh_hash = _mint_refresh_token()

    # Upgrade a still-valid legacy refresh pair without another browser login.
    identity.token_encrypted = encrypt({})
    identity.refresh_token_hash = None
    identity.refresh_token_expires_at = None
    identity.last_used_at = now
    db.add(AgentCredentialSession(
        id=str(uuid.uuid4()), agent_identity_id=identity.id,
        access_token_hash=token_hash(agent_raw), refresh_token_hash=refresh_hash,
        expires_at=now + _AGENT_TOKEN_TTL,
        refresh_token_expires_at=now + _REFRESH_TOKEN_TTL, created_at=now,
    ))

    db.commit()
    return identity, agent_raw, refresh_raw


def _rotate_session(hashed: str, db: Session) -> tuple[AgentIdentity, str, str]:
    session = db.query(AgentCredentialSession).filter(
        AgentCredentialSession.refresh_token_hash == hashed,
        AgentCredentialSession.revoked_at.is_(None),
    ).with_for_update().first()
    if session is None:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    now = datetime.now(timezone.utc)
    if session.refresh_token_expires_at <= now:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    identity = db.query(AgentIdentity).filter(AgentIdentity.id == session.agent_identity_id).first()
    if identity is None or identity.token_type != "cli" or identity.lifecycle_state in ("deactivated", "expired"):
        raise HTTPException(status_code=401, detail="Agent identity is inactive")
    member = db.execute(text(
        "SELECT clerk_user_id FROM guard_member_config "
        "WHERE agent_identity_id = :aid AND workspace_id = :ws AND active = true LIMIT 1"
    ), {"aid": identity.id, "ws": str(identity.workspace_id)}).fetchone()
    if not member:
        raise HTTPException(status_code=401, detail="Refresh token has no linked user")
    _assert_workspace_member(db, str(identity.workspace_id), member.clerk_user_id)
    access, _ = _mint_agent_token()
    refresh, refresh_hash = _mint_refresh_token()
    session.access_token_hash = token_hash(access)
    session.refresh_token_hash = refresh_hash
    session.expires_at = now + _AGENT_TOKEN_TTL
    session.refresh_token_expires_at = now + _REFRESH_TOKEN_TTL
    identity.last_used_at = now
    db.commit()
    return identity, access, refresh


@router.post("/refresh", response_model=CliTokenResponse)
def refresh_cli_token(
    body: RefreshRequest,
    db: Session = Depends(get_db),
):
    """Rotate a refresh_token → new agent_token + new refresh_token (no browser needed)."""
    identity, agent_raw, refresh_raw = rotate_identity_by_refresh(body.refresh_token, db)
    return CliTokenResponse(
        agent_token=agent_raw,
        refresh_token=refresh_raw,
        expires_in=int(_AGENT_TOKEN_TTL.total_seconds()),
        workspace_id=str(identity.workspace_id),
        user_id=None,
    )


# ─── Fix A: switch-workspace — re-mint token bound to different workspace ───

class SwitchWorkspaceRequest(BaseModel):
    workspace_id: str


@router.post("/switch-workspace", response_model=CliTokenResponse)
def switch_workspace(
    body: SwitchWorkspaceRequest,
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Mint a fresh agent_token bound to a different workspace the caller is a member of.

    Called by `conduct switch <name>` so the CLI's server-side context follows
    the local workspace_id change. Without this, `conduct switch` only flips
    the local config label — subsequent POSTs still attribute to the workspace
    the token was originally minted for.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Machine token cannot switch workspaces")
    # Membership check reuses the same helper as get_workspace_id — 403 if not a member.
    from app.core.auth import _assert_workspace_member
    _assert_workspace_member(db, body.workspace_id, user_id)

    _, agent_raw, refresh_raw = _upsert_identity(db, body.workspace_id, user_id)
    db.commit()

    return CliTokenResponse(
        agent_token=agent_raw,
        refresh_token=refresh_raw,
        expires_in=int(_AGENT_TOKEN_TTL.total_seconds()),
        workspace_id=body.workspace_id,
        user_id=user_id,
    )
