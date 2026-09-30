"""Short-lived console credentials; authorization is always resolved from the DB."""
import hmac
import time
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from .models import ConsoleIdentityMapping
from .trust import ConsoleTrust

SESSION_ISSUER = "urn:conduct:console"
SESSION_AUDIENCE = "conduct-console-api"
SESSION_TTL = 60
SESSION_TYPE = "conduct-console+jwt"


def configured_trust() -> ConsoleTrust:
    return ConsoleTrust(issuer=settings.console_oidc_issuer, audience=settings.console_oidc_client_id,
                        jwks_uri=settings.console_oidc_jwks_url, ca_file=settings.console_oidc_ca_file)


def signing_key() -> bytes:
    secret = settings.console_proxy_secret
    if len(secret.encode()) < 32:
        raise HTTPException(503, "Console authentication is not configured")
    return hmac.digest(secret.encode(), b"conduct-console-session-v1", "sha256")


def resolve_mapping(db: Session, issuer: str, subject: str) -> ConsoleIdentityMapping:
    mapping = db.query(ConsoleIdentityMapping).filter_by(issuer=issuer, subject=subject, active=True).first()
    if mapping is None:
        raise HTTPException(403, "Console identity is not provisioned")
    return mapping


def mint_session(mapping: ConsoleIdentityMapping, identity_expiry: int) -> dict:
    now = int(time.time())
    expires = min(now + SESSION_TTL, identity_expiry)
    if expires <= now:
        raise HTTPException(401, "Console identity expired")
    claims = {"iss": SESSION_ISSUER, "aud": SESSION_AUDIENCE, "sub": mapping.user_id,
              "mapping_id": str(mapping.id), "oidc_issuer": mapping.issuer,
              "iat": now, "exp": expires, "jti": str(uuid4())}
    token = jwt.encode(claims, signing_key(), algorithm="HS256", headers={"typ": SESSION_TYPE})
    return {"token": token, "expires_at": expires,
            "user": {"id": mapping.user_id, "name": mapping.display_name or mapping.user_id}}


def verify_session(token: str, db: Session) -> dict:
    if settings.auth_mode != "proxy":
        raise HTTPException(401, "Invalid console session")
    try:
        if len(token) > 16384:
            raise ValueError
        header = jwt.get_unverified_header(token)
        if header != {"alg": "HS256", "typ": SESSION_TYPE}:
            raise ValueError
        claims = jwt.decode(token, signing_key(), algorithms=["HS256"], issuer=SESSION_ISSUER,
                            audience=SESSION_AUDIENCE,
                            options={"require": ["sub", "exp", "iat", "jti", "mapping_id", "oidc_issuer"]})
        if (claims["oidc_issuer"] != settings.console_oidc_issuer
                or type(claims["iat"]) is not int or type(claims["exp"]) is not int
                or not 0 < claims["exp"] - claims["iat"] <= SESSION_TTL):
            raise ValueError
        mapping_id = UUID(claims["mapping_id"])
    except (jwt.PyJWTError, TypeError, ValueError, KeyError):
        raise HTTPException(401, "Invalid or expired console session") from None
    mapping = db.query(ConsoleIdentityMapping).filter_by(
        id=mapping_id, user_id=claims["sub"], issuer=settings.console_oidc_issuer, active=True,
    ).first()
    if mapping is None:
        raise HTTPException(401, "Console identity is no longer active")
    return {"sub": mapping.user_id, "external_subject": mapping.subject, "external_issuer": mapping.issuer}
