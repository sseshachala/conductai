"""Agent-identity router helpers (split from router.py).

Token generation, workspace-scoped environment / identity lookups, identity
minting, env-var token write-through and credential-session serialisation.
"""
import os
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from app.core.crypto import encrypt
from app.models.environment import Environment
from app.models.integration import Integration
from app.modules.agent_identity.adapters import TOKEN_PREFIX
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.schemas import (
    CredentialSessionOut,
)


_DISPLAY_PREFIX_LEN = len(TOKEN_PREFIX) + 4


def _generate_token() -> tuple[str, str]:
    raw = TOKEN_PREFIX + os.urandom(32).hex()
    return raw, raw[:_DISPLAY_PREFIX_LEN]


def _require_workspace_environment(db: Session, workspace_id: str, environment_id: str) -> None:
    try:
        environment_uuid = uuid.UUID(environment_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Environment not found") from None
    row = db.query(Environment).filter(
        Environment.id == environment_uuid,
        Environment.workspace_id == uuid.UUID(workspace_id),
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Environment not found")


def _require_workspace_identity(db: Session, workspace_id: str, identity_id: str) -> AgentIdentity:
    row = db.query(AgentIdentity).filter(
        AgentIdentity.id == identity_id,
        AgentIdentity.workspace_id == workspace_id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent identity not found")
    return row


def mint_agent_identity(db: Session, workspace_id: str, name: str, source: str = "conduct_auto") -> tuple[AgentIdentity, str]:
    """Internal helper — mint an Agent Identity for a user without auth checks.

    Returns (AgentIdentity row, plaintext token). Caller must commit if needed.
    Used by guard join flow to auto-mint on invite accept (default source).
    """
    plaintext, prefix = _generate_token()
    now = datetime.now(timezone.utc)
    row = AgentIdentity(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        name=name,
        provider="conduct",
        source=source,
        token_prefix=prefix,
        token_encrypted=encrypt({"token": plaintext}),
        environment_id=None,
        created_at=now,
        last_used_at=None,
        expires_at=now + __import__("datetime").timedelta(hours=8),
    )
    db.add(row)
    return row, plaintext


def _write_token_to_env(db: Session, workspace_id: str, environment_id: str, plaintext: str) -> None:
    """Merge CONDUCT_AGENT_TOKEN into the env_vars credential blob for the environment."""
    _require_workspace_environment(db, workspace_id, environment_id)
    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "env_vars",
        Integration.environment_id == environment_id,
    ).first()

    # Insert-if-absent, then always merge. If we lost the existence race
    # to a concurrent writer, ON CONFLICT DO NOTHING leaves their row
    # intact and merge_and_write then patches our token in without
    # overwriting whatever fields they were writing.
    if not existing:
        stmt = (
            pg_insert(Integration)
            .values(
                workspace_id=workspace_id,
                service="agent_identity",
                handle="env_vars",
                auth_method="api_key",
                encrypted_credentials=encrypt({}),
                environment_id=environment_id,
            )
            .on_conflict_do_nothing(
                constraint="uq_integrations_workspace_handle_env",
            )
        )
        db.execute(stmt)
        existing = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.handle == "env_vars",
            Integration.environment_id == environment_id,
        ).first()
    # Read → merge one field → conditional write. Idempotent — safe
    # regardless of which of the two racing writers created the row.
    from app.core.integration_writer import merge_and_write
    merge_and_write(
        db,
        existing.id,
        lambda prev: {**prev, "CONDUCT_AGENT_TOKEN": plaintext},
    )
    db.commit()


def _credential_session_member_active(db, identity) -> bool:
    from sqlalchemy import text
    return db.execute(text(
        "SELECT 1 FROM guard_member_config gmc JOIN workspace_users wu "
        "ON wu.workspace_id = gmc.workspace_id AND wu.clerk_user_id = gmc.clerk_user_id "
        "WHERE gmc.agent_identity_id = :aid AND gmc.workspace_id = :ws AND gmc.active = true LIMIT 1"
    ), {"aid": identity.id, "ws": str(identity.workspace_id)}).fetchone() is not None


def _credential_session_out(row, identity, request: Request, member_active: bool) -> CredentialSessionOut:
    from app.modules.agent_identity.credentials import token_hash

    now = datetime.now(timezone.utc)
    if row.revoked_at:
        status = "revoked"
    elif not member_active or identity.lifecycle_state in ("deactivated", "expired"):
        status = "blocked"
    elif row.refresh_token_expires_at <= now:
        status = "expired"
    elif row.expires_at <= now:
        status = "refreshable"
    else:
        status = "active"
    authorization = request.headers.get("authorization", "")
    bearer = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    return CredentialSessionOut(
        id=row.id, created_at=row.created_at, expires_at=row.expires_at,
        refresh_token_expires_at=row.refresh_token_expires_at, revoked_at=row.revoked_at,
        status=status, is_current=bool(bearer and token_hash(bearer) == row.access_token_hash),
    )
