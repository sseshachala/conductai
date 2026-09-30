"""Server-only OIDC evidence exchange. No cookie or unverified-header authentication."""
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.federation.network import VerificationUnavailable
from app.modules.auth.federation.verifier import InvalidIdentity
from .session import configured_trust, mint_session, resolve_mapping
from .trust import verify_proxy_identity

router = APIRouter(prefix="/auth/console", tags=["console-auth"])


class IdentityExchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity_token: str = Field(min_length=1, max_length=16384)


@router.post("/session")
def exchange_identity(body: IdentityExchange, response: Response,
                      x_conduct_proxy_secret: str = Header(default=""), db: Session = Depends(get_db)):
    if settings.auth_mode != "proxy":
        raise HTTPException(404, "Not found")
    secret = settings.console_proxy_secret
    if len(secret.encode()) < 32:
        raise HTTPException(503, "Console authentication is not configured")
    if not hmac.compare_digest(secret.encode(), x_conduct_proxy_secret.encode()):
        raise HTTPException(401, "Trusted console exchange required")
    try:
        claims = verify_proxy_identity(body.identity_token, configured_trust())
    except InvalidIdentity:
        raise HTTPException(401, "Invalid console identity evidence") from None
    except VerificationUnavailable:
        raise HTTPException(503, "Console signing keys unavailable") from None
    mapping = resolve_mapping(db, claims["iss"], claims["sub"])
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return mint_session(mapping, claims["exp"])
