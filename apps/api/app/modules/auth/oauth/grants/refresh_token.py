"""OAuth 2.1 refresh_token grant — rotate on every use.

Spec: refresh tokens SHOULD be rotated (invalidate old, issue new pair). Our
AgentIdentity row holds one refresh_token_hash at a time; overwriting it is
the rotation.

All lookup / mint / commit / workspace-user-defense lives in
`cli_token.rotate_identity_by_refresh` — this grant is a shape-adapter that
maps that helper's return onto the OAuth 2.1 token-response body.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.auth.cli_token import _AGENT_TOKEN_TTL, rotate_identity_by_refresh


def handle(refresh_token: str, db: Session) -> dict:
    """Rotate refresh → new (access, refresh) pair. Raises 401 on any failure
    (delegated to `rotate_identity_by_refresh`)."""
    identity, agent_raw, refresh_raw = rotate_identity_by_refresh(refresh_token, db)
    return {
        "access_token": agent_raw,
        "token_type": "Bearer",
        "expires_in": int(_AGENT_TOKEN_TTL.total_seconds()),
        "refresh_token": refresh_raw,
        "workspace_id": str(identity.workspace_id),
    }
