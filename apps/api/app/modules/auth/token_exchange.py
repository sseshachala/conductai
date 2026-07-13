"""RFC 8693 Token Exchange endpoint — POST /token.

Accepts a Clerk JWT (subject_token) and issues a cond_agt_* token.
grant_type: urn:ietf:params:oauth:grant-type:token-exchange
subject_token_type: urn:ietf:params:oauth:token-type:jwt
resource: <workspace_id>
"""
from fastapi import APIRouter, Form, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends
from app.core.auth import _verify_clerk_token
from app.core.database import get_db
from app.modules.auth.cli_token import _upsert_identity, _AGENT_TOKEN_TTL

router = APIRouter(tags=["auth"])

_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"
_TOKEN_TYPE_JWT = "urn:ietf:params:oauth:token-type:jwt"
_TOKEN_TYPE_ACCESS = "urn:ietf:params:oauth:token-type:access_token"


@router.post("/token")
def token_exchange(
    grant_type: str = Form(...),
    subject_token: str = Form(...),
    subject_token_type: str = Form(...),
    resource: str = Form(...),  # workspace_id
    db: Session = Depends(get_db),
):
    """RFC 8693 token exchange: Clerk JWT → cond_agt_* + cond_ref_*."""
    if grant_type != _GRANT_TYPE:
        raise HTTPException(status_code=400, detail=f"unsupported_grant_type: {grant_type}")
    if subject_token_type != _TOKEN_TYPE_JWT:
        raise HTTPException(status_code=400, detail=f"unsupported_token_type: {subject_token_type}")

    claims = _verify_clerk_token(subject_token)
    if not claims:
        raise HTTPException(status_code=401, detail="invalid_subject_token: Clerk JWT invalid or expired")

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="invalid_subject_token: missing sub claim")

    _, agent_raw, refresh_raw = _upsert_identity(db, resource, clerk_user_id)

    return {
        "access_token": agent_raw,
        "issued_token_type": _TOKEN_TYPE_ACCESS,
        "token_type": "Bearer",
        "expires_in": int(_AGENT_TOKEN_TTL.total_seconds()),
        "refresh_token": refresh_raw,
        "workspace_id": resource,
    }
