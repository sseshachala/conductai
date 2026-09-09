"""OAuth 2.1 authorization endpoint — browser round-trip through Clerk.

Flow:
  1. GET /oauth/authorize?client_id=&redirect_uri=&code_challenge=&state=&response_type=code
     - Validate params against the registered client
     - Insert oauth_auth_codes row (status='pending') keyed by an opaque id
     - 302 to `${web_url}/oauth-authorize?request_id=<id>`
  2. Web page runs Clerk sign-in, then POSTs Clerk JWT + workspace_id back to
     POST /oauth/authorize/confirm with the same request_id.
  3. Confirm handler verifies Clerk JWT, mints a raw authz code, flips row to
     status='issued' with code_hash + clerk_user_id + workspace_id + short TTL,
     returns the redirect URL the browser should follow to close the loop:
     `<redirect_uri>?code=<raw>&state=<state>`
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import _verify_clerk_token
from app.models.oauth import OauthAuthCode, OauthClient

_PENDING_TTL = timedelta(minutes=5)   # time user has to complete Clerk sign-in
_ISSUED_TTL = timedelta(seconds=60)   # window between /confirm and /token


def _web_url() -> str:
    return os.getenv("CONDUCT_WEB_URL") or "https://app.conductai.ai"


def _issuer() -> str:
    return os.getenv("CONDUCT_OAUTH_ISSUER") or "https://api.conductai.ai"


def _hash_code(raw: str) -> str:
    import hashlib
    return hashlib.sha256(raw.encode()).hexdigest()


def start_authorize(
    *,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    state: str,
    scope: str | None,
    db: Session,
) -> str:
    """Validate params, insert pending row, return the URL to 302 to."""
    if response_type != "code":
        raise HTTPException(400, detail="unsupported_response_type")
    if code_challenge_method != "S256":
        raise HTTPException(400, detail="unsupported_code_challenge_method (S256 only)")
    if not (client_id and redirect_uri and code_challenge and state):
        raise HTTPException(400, detail="invalid_request: missing required parameter")

    client: OauthClient | None = db.query(OauthClient).filter(
        OauthClient.client_id == client_id
    ).first()
    if client is None:
        raise HTTPException(400, detail="unauthorized_client")
    if redirect_uri not in (client.redirect_uris or []):
        raise HTTPException(400, detail="invalid_redirect_uri")

    now = datetime.now(timezone.utc)
    row = OauthAuthCode(
        id=uuid.uuid4(),
        code_hash=None,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        state=state,
        scope=scope,
        status="pending",
        created_at=now,
        expires_at=now + _PENDING_TTL,
    )
    db.add(row)
    db.commit()

    return f"{_web_url()}/oauth-authorize?request_id={row.id}"


class ConfirmRequest(BaseModel):
    request_id: str
    clerk_token: str
    workspace_id: str


def confirm_authorize(body: ConfirmRequest, db: Session) -> dict:
    """Web page calls this after Clerk sign-in. Mints an authz code and returns
    the final redirect URL for the browser to load."""
    try:
        req_uuid = uuid.UUID(body.request_id)
    except (ValueError, TypeError):
        raise HTTPException(400, detail="invalid_request: request_id must be a UUID")

    claims = _verify_clerk_token(body.clerk_token)
    if not claims:
        raise HTTPException(401, detail="invalid_clerk_token")
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(401, detail="invalid_clerk_token: missing sub")

    row: OauthAuthCode | None = db.query(OauthAuthCode).filter(
        OauthAuthCode.id == req_uuid
    ).first()
    if row is None:
        raise HTTPException(400, detail="invalid_request: unknown request_id")

    now = datetime.now(timezone.utc)
    if row.status != "pending":
        raise HTTPException(400, detail=f"invalid_request: state is {row.status}")
    if row.expires_at < now:
        raise HTTPException(400, detail="invalid_request: authorization request expired")

    try:
        ws_uuid = uuid.UUID(body.workspace_id)
    except (ValueError, TypeError):
        raise HTTPException(400, detail="invalid_request: workspace_id must be a UUID")

    raw_code = "oauth_code_" + secrets.token_urlsafe(32)
    row.code_hash = _hash_code(raw_code)
    row.clerk_user_id = clerk_user_id
    row.workspace_id = ws_uuid
    row.status = "issued"
    row.expires_at = now + _ISSUED_TTL
    db.commit()

    final_url = f"{row.redirect_uri}?" + urlencode({
        "code": raw_code,
        "state": row.state,
    })
    return {"redirect_url": final_url}
