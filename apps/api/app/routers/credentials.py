"""
Credentials CRUD — scoped to the dev workspace for now.
POST   /credentials                                  — upsert a credential by handle
GET    /credentials                                  — list all (no secret values)
DELETE /credentials/:handle                          — remove
GET    /integrations/github/repos                    — list repos via stored token
GET    /integrations/github/repos/{owner}/{repo}/branches — list branches via stored token
"""
import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.credentials import retrieve_credential
from app.core.database import get_db


# ---------------------------------------------------------------------------
# Flat key-value env-var interface (admin only)
# Maps between standard env var names and internal (handle, field) storage.
# ---------------------------------------------------------------------------
# Env-var editor endpoints live in app.routers.env_vars — extracted in the
# #2054 Phase 1 fix. ``_ENV_VAR_MAP`` and ``_ENV_VAR_REVERSE`` are re-exported
# here so existing callers (``runtime/mcp_credentials.py``) don't need to
# change their imports.
from app.routers.env_vars import _ENV_VAR_MAP, _ENV_VAR_REVERSE  # noqa: E402,F401


from app.runtime.integrations.github import _github_headers as _gh_headers
from app.routers.credentials_integrations import router

# Re-exported for callers that import these names from this module.
from app.routers.credentials_integrations import (  # noqa: E402,F401
    _git_token,
    _github_token,
)


# ---------------------------------------------------------------------------
# Credential connection test — lightweight liveness check per service
# ---------------------------------------------------------------------------

class CredentialTestRequest(BaseModel):
    service: str        # github | slack | anthropic | linear | digitalocean | email
    credentials: dict   # raw field values to test — never persisted


@router.post("/test")
def test_credential(
    body: CredentialTestRequest,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """
    Test whether the supplied credentials can reach the named service.
    Credentials are used for this request only and are never stored.
    Returns {"ok": true} or {"ok": false, "error": "<reason>"}.
    """
    svc = body.service.lower().strip()
    creds = body.credentials

    try:
        if svc in ("github", "git"):
            token = creds.get("token") or creds.get("api_key", "")
            if not token:
                return {"ok": False, "error": "Missing 'token' field"}
            r = httpx.get(
                "https://api.github.com/user",
                headers=_gh_headers(token),
                timeout=10,
            )
            if r.status_code == 200:
                return {"ok": True, "user": r.json().get("login", "")}
            return {"ok": False, "error": f"GitHub returned {r.status_code}: {r.text[:200]}"}

        elif svc == "slack":
            token = creds.get("token") or creds.get("bot_token", "")
            if not token:
                return {"ok": False, "error": "Missing 'token' field"}
            r = httpx.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            data = r.json()
            if data.get("ok"):
                return {"ok": True, "team": data.get("team"), "user": data.get("user")}
            return {"ok": False, "error": data.get("error", "auth.test failed")}

        elif svc == "anthropic":
            api_key = creds.get("api_key", "")
            if not api_key:
                return {"ok": False, "error": "Missing 'api_key' field"}
            r = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            if r.status_code == 200:
                return {"ok": True}
            return {"ok": False, "error": f"Anthropic returned {r.status_code}: {r.text[:200]}"}

        elif svc == "linear":
            api_key = creds.get("api_key", "")
            if not api_key:
                return {"ok": False, "error": "Missing 'api_key' field"}
            r = httpx.post(
                "https://api.linear.app/graphql",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": "{ viewer { id name } }"},
                timeout=10,
            )
            data = r.json()
            if "errors" not in data and data.get("data", {}).get("viewer"):
                return {"ok": True, "user": data["data"]["viewer"].get("name", "")}
            err = (
                data.get("errors", [{}])[0].get("message", "GraphQL error")
                if "errors" in data
                else f"HTTP {r.status_code}"
            )
            return {"ok": False, "error": err}

        elif svc in ("digitalocean", "do"):
            token = creds.get("token") or creds.get("api_key", "")
            if not token:
                return {"ok": False, "error": "Missing 'token' field"}
            r = httpx.get(
                "https://api.digitalocean.com/v2/account",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if r.status_code == 200:
                return {"ok": True, "email": r.json().get("account", {}).get("email", "")}
            return {"ok": False, "error": f"DigitalOcean returned {r.status_code}: {r.text[:200]}"}

        elif svc in ("email", "resend"):
            resend_key = creds.get("resend_api_key") or creds.get("api_key", "")
            if not resend_key:
                return {"ok": False, "error": "Missing 'resend_api_key' field"}
            r = httpx.get(
                "https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {resend_key}"},
                timeout=10,
            )
            if r.status_code == 200:
                return {"ok": True}
            return {"ok": False, "error": f"Resend returned {r.status_code}: {r.text[:200]}"}

        elif svc == "perplexity":
            api_key = creds.get("api_key", "")
            if not api_key:
                return {"ok": False, "error": "Missing 'api_key' field"}
            r = httpx.get(
                "https://api.perplexity.ai/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if r.status_code == 200:
                return {"ok": True}
            return {"ok": False, "error": f"Perplexity returned {r.status_code}: {r.text[:200]}"}

        else:
            return {
                "ok": False,
                "error": (
                    f"Unknown service '{svc}'. "
                    "Supported: github, slack, anthropic, linear, digitalocean, email, perplexity"
                ),
            }

    except httpx.TimeoutException:
        return {"ok": False, "error": f"Connection to {svc} timed out"}
    except httpx.RequestError as exc:
        return {"ok": False, "error": f"Could not reach {svc}: {exc}"}


# ── Credential broker ─────────────────────────────────────────────────────────

class _RetrieveRequest(BaseModel):
    handle: str


@router.post("/creds/retrieve")
def retrieve_cred(
    body: _RetrieveRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Broker endpoint for run subprocesses and sandboxes.
    Accepts a short-lived cond_cred_* token (not a user JWT) and returns
    the decrypted credential for the requested handle if it's in the allowlist.
    """
    cred_token = request.headers.get("X-Cred-Token", "")
    if not cred_token or not cred_token.startswith("cond_cred_"):
        raise HTTPException(status_code=401, detail="missing or invalid cred token")
    result = retrieve_credential(db, cred_token, body.handle)
    if result is None:
        raise HTTPException(status_code=403, detail="token invalid, expired, or handle not permitted")
    return result
