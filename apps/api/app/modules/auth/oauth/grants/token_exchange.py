"""OAuth 2.1 unified endpoint — RFC 8693 token-exchange grant.

Same behavior as the standalone /token route (kept as alias for CLI compat):
Clerk JWT (subject_token) → cond_agt_* + cond_ref_* via _upsert_identity.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.auth import _verify_clerk_token
from app.modules.auth.cli_token import _AGENT_TOKEN_TTL, _upsert_identity

_TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"
_TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"


def handle(
    subject_token: str,
    subject_token_type: str,
    resource: str,
    db: Session,
) -> dict:
    if subject_token_type != _TOKEN_TYPE_JWT:
        raise HTTPException(400, detail=f"unsupported_token_type: {subject_token_type}")

    claims = _verify_clerk_token(subject_token)
    if not claims:
        raise HTTPException(401, detail="invalid_subject_token")

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(401, detail="invalid_subject_token: missing sub claim")

    _, agent_raw, refresh_raw = _upsert_identity(db, resource, clerk_user_id)

    return {
        "access_token": agent_raw,
        "issued_token_type": _TOKEN_TYPE_ACCESS,
        "token_type": "Bearer",
        "expires_in": int(_AGENT_TOKEN_TTL.total_seconds()),
        "refresh_token": refresh_raw,
        "workspace_id": resource,
    }
