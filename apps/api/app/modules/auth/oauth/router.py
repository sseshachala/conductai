"""OAuth 2.1 + DCR FastAPI routes — thin wrappers over the handlers.

The three routers exported here:

- `router`               → /oauth/* endpoints (register, authorize, token)
- `well_known_router`    → /.well-known/oauth-authorization-server metadata
- `legacy_token_router`  → /token alias so existing CLIs keep working

`app/main.py` includes all three.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auth.oauth import authorize as _authorize
from app.modules.auth.oauth import dcr as _dcr
from app.modules.auth.oauth import metadata as _metadata
from app.modules.auth.oauth import token as _token

router = APIRouter(prefix="/oauth", tags=["oauth"])
well_known_router = APIRouter(tags=["oauth"])
legacy_token_router = APIRouter(tags=["oauth"])


@well_known_router.get("/.well-known/oauth-authorization-server")
async def oauth_metadata() -> dict:
    return _metadata.build_authorization_server_metadata()


@router.post("/register")
def dcr_register(
    body: _dcr.RegisterRequest,
    db: Session = Depends(get_db),
) -> dict:
    return _dcr.register_client(body, db, created_by_clerk_user_id=None)


@router.get("/authorize")
def authorize(
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: str = Query(...),
    scope: str | None = Query(None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Validate params, stash pending row, 302 to the web sign-in page."""
    url = _authorize.start_authorize(
        response_type=response_type,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
        scope=scope,
        db=db,
    )
    return RedirectResponse(url=url, status_code=302)


@router.post("/authorize/confirm")
def authorize_confirm(
    body: _authorize.ConfirmRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Called by the web /oauth-authorize page after Clerk sign-in.
    Returns {"redirect_url": "<client_redirect_uri>?code=...&state=..."} so the
    page can `window.location.href = redirect_url`."""
    return _authorize.confirm_authorize(body, db)


@router.post("/token")
async def oauth_token(response: dict = Depends(_token.form_dispatch)) -> dict:
    return response


@legacy_token_router.post("/token")
async def legacy_token(response: dict = Depends(_token.form_dispatch)) -> dict:
    """Backwards-compat alias for the installed CLI base. Same handler as
    /oauth/token; delete after ~60 days of zero traffic."""
    return response
