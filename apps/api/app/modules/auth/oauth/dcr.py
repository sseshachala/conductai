"""RFC 7591 Dynamic Client Registration — POST /oauth/register.

Public clients only for now (no client_secret, no confidential auth). PKCE is
the sole client-auth mechanism at token exchange. Enforced here by rejecting
any `token_endpoint_auth_method` other than 'none'.

Minted client_id: `oauth_cli_<24 hex chars>`. Namespaced so it's grep-friendly
and distinguishable from cond_agt_ / cond_ref_ tokens.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.oauth import OauthClient

_CLIENT_ID_PREFIX = "oauth_cli_"
_ALLOWED_GRANTS = {"authorization_code", "refresh_token"}
_ALLOWED_RESPONSE_TYPES = {"code"}


class RegisterRequest(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=200)
    redirect_uris: list[str] = Field(..., min_length=1, max_length=10)
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    token_endpoint_auth_method: str = "none"
    scope: str | None = None


def _mint_client_id() -> str:
    return _CLIENT_ID_PREFIX + os.urandom(12).hex()


def _validate_redirect_uris(uris: list[str]) -> None:
    for u in uris:
        if not (u.startswith("http://") or u.startswith("https://") or u.startswith("mcp://")):
            raise HTTPException(400, detail=f"invalid_redirect_uri: {u!r}")
        # Localhost http is fine for CLI / dev clients; everything else must be https/mcp.
        if u.startswith("http://") and "://localhost" not in u and "://127.0.0.1" not in u:
            raise HTTPException(400, detail=f"insecure_redirect_uri: {u!r}")


def register_client(
    body: RegisterRequest,
    db: Session,
    created_by_clerk_user_id: str | None = None,
) -> dict[str, Any]:
    _validate_redirect_uris(body.redirect_uris)

    grants = body.grant_types or ["authorization_code", "refresh_token"]
    for g in grants:
        if g not in _ALLOWED_GRANTS:
            raise HTTPException(400, detail=f"unsupported_grant_type: {g!r}")

    response_types = body.response_types or ["code"]
    for rt in response_types:
        if rt not in _ALLOWED_RESPONSE_TYPES:
            raise HTTPException(400, detail=f"unsupported_response_type: {rt!r}")

    if body.token_endpoint_auth_method != "none":
        raise HTTPException(400, detail="only public clients (token_endpoint_auth_method='none') supported")

    now = datetime.now(timezone.utc)
    client = OauthClient(
        client_id=_mint_client_id(),
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=grants,
        token_endpoint_auth_method="none",
        scope=body.scope,
        created_by_clerk_user_id=created_by_clerk_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(client)
    db.commit()

    return {
        "client_id": client.client_id,
        "client_id_issued_at": int(now.timestamp()),
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": client.grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
    }
