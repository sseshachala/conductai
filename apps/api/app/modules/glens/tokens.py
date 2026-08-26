"""Session-scoped Lens tokens — #1218 Step 3b.

Mint / validate / revoke helpers for cond_lens_* tokens bound to one
glens_chat_sessions row. Blast radius = one chat session.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.modules.glens.models import GlensChatSession

TOKEN_PREFIX = "cond_lens_"
IDLE_TIMEOUT = timedelta(hours=24)
SESSION_TTL = timedelta(days=7)


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def mint_for_session(db: Session, session: GlensChatSession) -> str:
    """Mint a fresh cond_lens_* token, store hash on the session row, return raw.

    Called once when a session is created. Raw token flows back to the request
    context; never persisted, never logged."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(24)
    session.token_hash = _hash(raw)
    session.token_revoked_at = None
    db.add(session)
    db.commit()
    return raw


def validate_token(db: Session, raw: str) -> GlensChatSession | None:
    """Look up the session by token hash. Returns None if not found, revoked,
    or idle/TTL expired. Never raises."""
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None

    session = (
        db.query(GlensChatSession)
        .filter(GlensChatSession.token_hash == _hash(raw))
        .first()
    )
    if session is None:
        return None
    if session.token_revoked_at is not None:
        return None

    now = datetime.now(timezone.utc)
    if session.updated_at and (now - session.updated_at) > IDLE_TIMEOUT:
        return None
    if session.created_at and (now - session.created_at) > SESSION_TTL:
        return None

    return session


def revoke(db: Session, session_id: uuid.UUID) -> bool:
    """Ops kill-switch — mark this session's token revoked. Returns True if
    the session existed."""
    session = db.get(GlensChatSession, session_id)
    if session is None:
        return False
    session.token_revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True
