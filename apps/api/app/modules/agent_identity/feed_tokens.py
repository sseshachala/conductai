"""Workspace-owned, read-only audit-feed service tokens (``cond_feed_*``).

Reuses the agent-identity tables: one ``AgentIdentity`` (``token_type='feed'``)
plus one ``AgentCredentialSession`` holding only the SHA-256 of the token, so
the plaintext exists once, in the issue response. The token is not tied to a
member's login: it keeps working when the person who issued it leaves, and
stops only when an admin revokes it (or it expires).

Scope is enforced in the MCP dispatcher (``FEED_TOKEN_TOOLS``) and the prefix
is deliberately absent from every other token resolver, so ``cond_feed_*``
is rejected everywhere else.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.crypto import encrypt
from app.modules.agent_identity.credentials import token_hash
from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity

FEED_TOKEN_PREFIX = "cond_feed_"
FEED_TOKEN_TYPE = "feed"
FEED_TOKEN_SOURCE = "conduct_feed"
FEED_SCOPE = "audit_feed"
FEED_PERMISSION = "platform.audit_log.view"
# The only MCP tool a feed token may call. Everything else is refused.
FEED_TOKEN_TOOLS = frozenset({"get_audit_feed"})
_DISPLAY_PREFIX_LEN = len(FEED_TOKEN_PREFIX) + 4


def mint(db: Session, workspace_id: str, name: str, created_by: str | None,
         expires_at: datetime | None = None) -> tuple[AgentIdentity, str]:
    """Create the identity + hashed credential. Returns (identity, plaintext)."""
    plaintext = FEED_TOKEN_PREFIX + os.urandom(32).hex()
    now = datetime.now(timezone.utc)
    identity = AgentIdentity(
        id=str(uuid.uuid4()), workspace_id=uuid.UUID(str(workspace_id)),
        name=f"SIEM feed: {name}"[:100], provider="conduct", source=FEED_TOKEN_SOURCE,
        token_prefix=plaintext[:_DISPLAY_PREFIX_LEN], token_encrypted=encrypt({}),
        token_type=FEED_TOKEN_TYPE, token_name=name, created_by_clerk_user_id=created_by,
        created_at=now, expires_at=expires_at,
    )
    db.add(identity)
    db.flush()
    db.add(AgentCredentialSession(
        id=str(uuid.uuid4()), agent_identity_id=identity.id,
        access_token_hash=token_hash(plaintext),
        refresh_token_hash=token_hash("unused:" + os.urandom(32).hex()),  # NOT NULL/unique; never issued
        expires_at=expires_at or datetime(9999, 12, 31, tzinfo=timezone.utc),
        refresh_token_expires_at=now, created_at=now,
    ))
    db.commit()
    return identity, plaintext


def resolve(token: str, db: Session) -> AgentIdentity | None:
    """Return the active feed identity for ``token`` or None."""
    if not token.startswith(FEED_TOKEN_PREFIX):
        return None
    session = db.query(AgentCredentialSession).filter(
        AgentCredentialSession.access_token_hash == token_hash(token),
        AgentCredentialSession.revoked_at.is_(None),
    ).first()
    if session is None:
        return None
    identity = db.query(AgentIdentity).filter(AgentIdentity.id == session.agent_identity_id).first()
    if (identity is None or identity.token_type != FEED_TOKEN_TYPE
            or identity.lifecycle_state in ("deactivated", "expired")):
        return None
    expiry = identity.expires_at
    if expiry is not None:
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            return None
    return identity


def revoke(db: Session, identity: AgentIdentity) -> None:
    now = datetime.now(timezone.utc)
    db.query(AgentCredentialSession).filter(
        AgentCredentialSession.agent_identity_id == identity.id,
        AgentCredentialSession.revoked_at.is_(None),
    ).update({"revoked_at": now})
    identity.lifecycle_state = "deactivated"
    identity.deactivated_at = now
    db.commit()
