"""POST /oauth/token — grant-type dispatcher.

Accepts all three grant types Conduct supports via one endpoint (the RFC 8414
metadata advertises this URL as the single `token_endpoint`):

- authorization_code
- refresh_token
- urn:ietf:params:oauth:grant-type:token-exchange (kept for CLI + Canvas)

Each grant lives in its own module under `.grants/`; this file is just the
form-body router.
"""
from __future__ import annotations

from fastapi import Depends, Form, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.oauth.grants import (
    authorization_code as _grant_ac,
    refresh_token as _grant_rt,
    token_exchange as _grant_te,
)

_GRANT_AC = "authorization_code"
_GRANT_RT = "refresh_token"
_GRANT_TE = "urn:ietf:params:oauth:grant-type:token-exchange"


def dispatch(
    *,
    grant_type: str,
    # authorization_code
    code: str | None = None,
    code_verifier: str | None = None,
    client_id: str | None = None,
    redirect_uri: str | None = None,
    # refresh_token
    refresh_token: str | None = None,
    # token-exchange (RFC 8693)
    subject_token: str | None = None,
    subject_token_type: str | None = None,
    resource: str | None = None,
    db: Session,
) -> dict:
    """Route the form body to the right grant handler.

    Called by BOTH `/oauth/token` and `/token` (legacy alias) — the two routes
    share one implementation. Callers that omit grant-specific params get a
    400; each grant handler validates its own inputs beyond presence.
    """
    if grant_type == _GRANT_AC:
        return _grant_ac.handle(
            code=code or "",
            code_verifier=code_verifier or "",
            client_id=client_id or "",
            redirect_uri=redirect_uri or "",
            db=db,
        )

    if grant_type == _GRANT_RT:
        return _grant_rt.handle(refresh_token=refresh_token or "", db=db)

    if grant_type == _GRANT_TE:
        if not (subject_token and subject_token_type and resource):
            raise HTTPException(400, detail="invalid_request: token-exchange requires subject_token, subject_token_type, resource")
        return _grant_te.handle(
            subject_token=subject_token,
            subject_token_type=subject_token_type,
            resource=resource,
            db=db,
        )

    raise HTTPException(400, detail=f"unsupported_grant_type: {grant_type!r}")


async def form_dispatch(
    grant_type: str = Form(...),
    code: str | None = Form(None),
    code_verifier: str | None = Form(None),
    client_id: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    refresh_token: str | None = Form(None),
    subject_token: str | None = Form(None),
    subject_token_type: str | None = Form(None),
    resource: str | None = Form(None),
    db: Session = Depends(get_db),
) -> dict:
    """FastAPI form-body wrapper. Uses standard get_db dependency so tests can
    override with app.dependency_overrides[get_db]."""
    return dispatch(
        grant_type=grant_type,
        code=code,
        code_verifier=code_verifier,
        client_id=client_id,
        redirect_uri=redirect_uri,
        refresh_token=refresh_token,
        subject_token=subject_token,
        subject_token_type=subject_token_type,
        resource=resource,
        db=db,
    )
