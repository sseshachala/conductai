"""Credential lookup shared by HTTP, MCP, Gateway and identity attribution."""
import hashlib

from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity

SESSION_ACCESS_PREFIX = "cond_agt_s1_"
SESSION_REFRESH_PREFIX = "cond_ref_s1_"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def find_session_credential(token, db):
    """Return (identity, credential expiry), never treating a session as legacy."""
    session = db.query(AgentCredentialSession).filter(
        AgentCredentialSession.access_token_hash == token_hash(token),
        AgentCredentialSession.revoked_at.is_(None),
    ).first()
    if session is None:
        return None
    identity = db.query(AgentIdentity).filter(
        AgentIdentity.id == session.agent_identity_id,
    ).first()
    return (identity, session.expires_at) if identity is not None else None
