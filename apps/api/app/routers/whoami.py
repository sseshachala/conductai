"""One endpoint: `GET /auth/whoami` — echoes what the current Bearer resolves to.

Cheap, boring, useful. Powers the `conduct guard simulate --as-okta-agent`
CLI command (#1057) and gives operators a way to sanity-check any token
without wiring up a real workload.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import _bearer, _resolve_agent_token, _resolve_okta_jwt, get_workspace_id
from app.core.database import get_db


router = APIRouter(prefix="/auth", tags=["auth"])


class WhoAmIOut(BaseModel):
    workspace_id: str
    token_kind: str  # "cond_agt" | "cond_api" | "cond_run" | "okta_jwt" | "clerk" | "unknown"
    identity: Optional[dict[str, Any]] = None


def _classify(token: str) -> str:
    if token.startswith("cond_agt_"):
        return "cond_agt"
    if token.startswith("cond_api_"):
        return "cond_api"
    if token.startswith("cond_run_"):
        return "cond_run"
    if token.count(".") == 2:
        return "jwt"
    return "unknown"


@router.get("/whoami", response_model=WhoAmIOut)
def whoami(
    workspace_id: str = Depends(get_workspace_id),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> WhoAmIOut:
    if not credentials:
        return WhoAmIOut(workspace_id=workspace_id, token_kind="unknown")

    token = credentials.credentials
    kind = _classify(token)
    identity: dict[str, Any] | None = None

    if kind in ("cond_agt", "cond_api"):
        try:
            ai, clerk_uid = _resolve_agent_token(token, db)
            identity = {
                "id": str(ai.id),
                "name": getattr(ai, "name", None),
                "source": getattr(ai, "source", None),
                "source_id": getattr(ai, "source_id", None),
                "lifecycle_state": getattr(ai, "lifecycle_state", None),
                "clerk_user_id": clerk_uid,
            }
        except Exception:
            pass
    elif kind == "jwt":
        okta = _resolve_okta_jwt(token, db)
        if okta is not None:
            ai, _ = okta
            identity = {
                "id": str(ai.id),
                "name": getattr(ai, "name", None),
                "source": getattr(ai, "source", None),
                "source_id": getattr(ai, "source_id", None),
                "lifecycle_state": getattr(ai, "lifecycle_state", None),
                "clerk_user_id": None,
            }
            kind = "okta_jwt"
        else:
            kind = "clerk"  # JWT that didn't match any Okta issuer

    return WhoAmIOut(workspace_id=workspace_id, token_kind=kind, identity=identity)
