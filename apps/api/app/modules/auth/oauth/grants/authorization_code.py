"""OAuth 2.1 authorization_code grant — PKCE-verified code → token pair.

Called after the browser round-trip completes: the client has an authz code
minted by /oauth/authorize/confirm and the code_verifier it generated at
/authorize time. We verify the S256 challenge, the client_id and redirect_uri
bindings, then mint the token pair via _upsert_identity.

Codes are single-use — status flips to 'consumed' with a timestamp so replay
is detectable via SIEM even after the row is retained past used_at.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.oauth import OauthAuthCode
from app.modules.auth.cli_token import _AGENT_TOKEN_TTL, _upsert_identity
from app.modules.auth.oauth.pkce import verify_s256


def handle(
    code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
    db: Session,
) -> dict:
    if not code or not code_verifier or not client_id or not redirect_uri:
        raise HTTPException(400, detail="invalid_request: missing required parameter")

    code_hash = hashlib.sha256(code.encode()).hexdigest()
    row: OauthAuthCode | None = db.query(OauthAuthCode).filter(
        OauthAuthCode.code_hash == code_hash
    ).first()
    if row is None:
        raise HTTPException(400, detail="invalid_grant: code not recognized")

    now = datetime.now(timezone.utc)
    if row.status != "issued":
        # 'consumed' is a replay attempt; 'pending' means /confirm never ran.
        raise HTTPException(400, detail=f"invalid_grant: code {row.status}")
    if row.expires_at < now:
        raise HTTPException(400, detail="invalid_grant: code expired")
    if row.client_id != client_id:
        raise HTTPException(400, detail="invalid_grant: client_id mismatch")
    if row.redirect_uri != redirect_uri:
        raise HTTPException(400, detail="invalid_grant: redirect_uri mismatch")
    if row.code_challenge_method != "S256":
        raise HTTPException(400, detail="invalid_grant: unsupported code_challenge_method")
    if not verify_s256(code_verifier, row.code_challenge):
        raise HTTPException(400, detail="invalid_grant: PKCE verification failed")
    if row.clerk_user_id is None or row.workspace_id is None:
        raise HTTPException(400, detail="invalid_grant: code has no identity binding")

    # Flip status BEFORE minting — otherwise a mint failure rolls back the
    # consume too and the code becomes replayable. Fail-safe direction is
    # deny-legitimate-use on error, never privilege-escalation.
    row.status = "consumed"
    row.used_at = now
    db.commit()

    _, agent_raw, refresh_raw = _upsert_identity(db, str(row.workspace_id), row.clerk_user_id)

    return {
        "access_token": agent_raw,
        "token_type": "Bearer",
        "expires_in": int(_AGENT_TOKEN_TTL.total_seconds()),
        "refresh_token": refresh_raw,
        "workspace_id": str(row.workspace_id),
        "scope": row.scope,
    }
