"""
Credentials CRUD — scoped to the dev workspace for now.
POST   /credentials                                  — upsert a credential by handle
GET    /credentials                                  — list all (no secret values)
DELETE /credentials/:handle                          — remove
GET    /integrations/github/repos                    — list repos via stored token
GET    /integrations/github/repos/{owner}/{repo}/branches — list branches via stored token
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.models.workflow import Workflow

GITHUB_API = "https://api.github.com"
VERCEL_API = "https://api.vercel.com"

router = APIRouter(prefix="/credentials", tags=["credentials"])

KNOWN_SERVICES = {
    "github":       {"fields": ["token"],        "label": "GitHub",       "hint": "Personal access token or OAuth token"},
    "slack":        {"fields": ["token"],        "label": "Slack",        "hint": "Bot OAuth token (xoxb-…)"},
    "linear":       {"fields": ["api_key"],      "label": "Linear",       "hint": "Personal API key from Linear settings"},
    "digitalocean": {"fields": ["token"],        "label": "DigitalOcean", "hint": "Personal access token"},
    "vercel":       {"fields": ["token"],        "label": "Vercel",       "hint": "Personal access token"},
}


class CredentialUpsert(BaseModel):
    service: str
    handle: str                         # short name used in blocks, e.g. "github", "slack-prod"
    credentials: dict                   # raw key/value, will be encrypted
    environment_id: str | None = None   # optional environment scoping


class CredentialOut(BaseModel):
    handle: str
    service: str
    auth_method: str
    fields: list[str]  # field names present (no values)

    class Config:
        from_attributes = True


@router.get("", response_model=list[CredentialOut])
def list_credentials(db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "editor", "viewer"))):
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id
    ).order_by(Integration.created_at).all()

    return [
        CredentialOut(
            handle=r.handle,
            service=r.service,
            auth_method=r.auth_method,
            fields=list(decrypt(r.encrypted_credentials).keys()) if r.encrypted_credentials else [],
        )
        for r in rows
    ]


@router.post("", status_code=201)
def upsert_credential(body: CredentialUpsert, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "editor"))):
    if not body.credentials:
        raise HTTPException(status_code=422, detail="credentials dict must not be empty")

    auth_method = "api_key" if "api_key" in body.credentials else "oauth"

    # Resolve environment: explicit ID > Default environment > error
    if body.environment_id:
        env_id = body.environment_id
    else:
        from app.models.environment import Environment
        default_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
            Environment.name == "Default",
        ).first()
        if not default_env:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=422,
                detail="No Default environment found. Create an environment first in Settings → Environments.",
            )
        env_id = str(default_env.id)

    # Upsert keyed on (workspace, handle, environment) — same handle can exist
    # in multiple environments since the constraint changed in migration 0015.
    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == body.handle,
        Integration.environment_id == env_id,
    ).first()

    if existing:
        existing.service = body.service
        existing.auth_method = auth_method
        existing.encrypted_credentials = encrypt(body.credentials)
        existing.environment_id = env_id
    else:
        row = Integration(
            workspace_id=workspace_id,
            service=body.service,
            handle=body.handle,
            auth_method=auth_method,
            encrypted_credentials=encrypt(body.credentials),
            environment_id=env_id,
        )
        db.add(row)

    db.commit()
    return {"handle": body.handle, "service": body.service, "saved": True}


@router.delete("/{handle}", status_code=204)
def delete_credential(handle: str, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin"))):
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == handle,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Block deletion if this integration's environment is assigned to any workflow
    if row.environment_id:
        agents = (
            db.query(Workflow)
            .filter(Workflow.environment_id == row.environment_id)
            .all()
        )
        if agents:
            names = ", ".join(a.name for a in agents)
            raise HTTPException(
                status_code=409,
                detail=f"This credential's environment is used by {len(agents)} agent(s): {names}. Remove the environment from those agents first.",
            )

    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Environment-scoped credential listing
# ---------------------------------------------------------------------------

@router.get("/by-environment/{env_id}", response_model=list[CredentialOut])
def list_credentials_by_environment(
    env_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """List credentials scoped to a specific environment."""
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
    ).order_by(Integration.created_at).all()

    return [
        CredentialOut(
            handle=r.handle,
            service=r.service,
            auth_method=r.auth_method,
            fields=list(decrypt(r.encrypted_credentials).keys()) if r.encrypted_credentials else [],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Flat key-value env-var interface (admin only)
# Maps between standard env var names and internal (handle, field) storage.
# ---------------------------------------------------------------------------

# Standard env var name → (handle, field)
_ENV_VAR_MAP: dict[str, tuple[str, str]] = {
    # Git (unified handle — provider stored as a field within the credential)
    "GIT_TOKEN":          ("git",          "token"),
    "GITHUB_TOKEN":       ("git",          "token"),   # alias
    "GITHUB_PAT":         ("git",          "token"),   # alias
    "GITLAB_TOKEN":       ("git",          "token"),   # alias
    "BITBUCKET_TOKEN":    ("git",          "token"),   # alias
    "GIT_PROVIDER":       ("git",          "provider"),
    # Collaboration
    "SLACK_TOKEN":        ("slack",        "token"),
    "SLACK_BOT_TOKEN":    ("slack",        "token"),
    "LINEAR_API_KEY":     ("linear",       "api_key"),
    # Cloud / infra
    "DIGITALOCEAN_TOKEN": ("digitalocean", "token"),
    "DO_TOKEN":           ("digitalocean", "token"),
    "VERCEL_TOKEN":       ("vercel",       "token"),
    "MODAL_TOKEN_ID":     ("modal",        "token_id"),
    "MODAL_TOKEN_SECRET": ("modal",        "token_secret"),
    # AI
    "ANTHROPIC_API_KEY":  ("anthropic",    "api_key"),
    # Email
    "RESEND_API_KEY":     ("email",        "resend_api_key"),
    "SENDGRID_API_KEY":   ("email",        "sendgrid_api_key"),
    "EMAIL_FROM_NAME":    ("email",        "from_name"),
    "EMAIL_FROM_EMAIL":   ("email",        "from_email"),
}
# Reverse: (handle, field) → canonical env var name
_ENV_VAR_REVERSE: dict[tuple[str, str], str] = {v: k for k, v in _ENV_VAR_MAP.items() if k == k.upper()}


@router.get("/env-vars/{env_id}")
def list_env_vars(
    env_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Return all credentials for an environment as flat key-value pairs."""
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
    ).order_by(Integration.created_at).all()

    result = []
    for row in rows:
        if not row.encrypted_credentials:
            continue
        creds = decrypt(row.encrypted_credentials)
        for field, value in creds.items():
            key = _ENV_VAR_REVERSE.get((row.handle, field)) or f"{row.handle.upper()}_{field.upper()}"
            result.append({"key": key, "value": value, "handle": row.handle, "field": field})
    return result


class EnvVarUpsert(BaseModel):
    key: str
    value: str


@router.put("/env-vars/{env_id}", status_code=200)
def save_env_vars(
    env_id: str,
    body: list[EnvVarUpsert],
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Save a full list of env vars for an environment — groups by handle and upserts."""
    from app.models.environment import Environment as _Env
    env = db.query(_Env).filter(_Env.id == env_id, _Env.workspace_id == workspace_id).first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Group by handle, merging fields
    grouped: dict[str, dict[str, str]] = {}
    for item in body:
        handle, field = _ENV_VAR_MAP.get(item.key, ("env_vars", item.key.lower()))
        grouped.setdefault(handle, {})[field] = item.value

    for handle, creds in grouped.items():
        existing = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.handle == handle,
            Integration.environment_id == env_id,
        ).first()
        if existing:
            existing.encrypted_credentials = encrypt(creds)
        else:
            db.add(Integration(
                workspace_id=workspace_id,
                service=handle,
                handle=handle,
                auth_method="api_key",
                encrypted_credentials=encrypt(creds),
                environment_id=env_id,
            ))

    # Remove handles that were deleted (not present in new list)
    new_handles = set(grouped.keys())
    for row in db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
    ).all():
        if row.handle not in new_handles:
            db.delete(row)

    db.commit()
    return {"saved": len(body)}


# ---------------------------------------------------------------------------
# Reveal — decrypt and return credential values (admin only)
# ---------------------------------------------------------------------------

@router.get("/reveal/{handle}")
def reveal_credential(
    handle: str,
    environment_id: str | None = None,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Return decrypted credential fields — admin only."""
    q = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == handle,
    )
    if environment_id:
        q = q.filter(Integration.environment_id == environment_id)
    row = q.first()
    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail="Credential not found")
    return decrypt(row.encrypted_credentials)


# ---------------------------------------------------------------------------
# GitHub proxy — canvas dropdowns for repo/branch selection
# ---------------------------------------------------------------------------

def _git_token(workspace_id: str, db: Session, environment_id: str | None = None) -> tuple[str, str]:
    """Fetch and decrypt the git token + provider for the workspace.

    Lookup order:
    1. `git` handle scoped to environment_id (if provided)
    2. Any `git` handle for the workspace
    3. Legacy `github` handle (backward compat)

    Returns (token, provider) where provider is 'github' | 'gitlab' | 'bitbucket'.
    """
    def _resolve(service: str) -> Integration | None:
        q = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.service == service,
        )
        if environment_id:
            row = q.filter(Integration.environment_id == environment_id).first()
            if row:
                return row
        return q.order_by(Integration.environment_id.nullslast()).first()

    row = _resolve("git") or _resolve("github")
    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail="Git credentials not connected — add them in Settings → Environments")
    creds = decrypt(row.encrypted_credentials)
    token = creds.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Git credential is missing a 'token' field")
    provider = creds.get("provider", "github")
    return token, provider


def _github_token(workspace_id: str, db: Session, environment_id: str | None = None) -> str:
    """Backward-compat shim — returns just the token."""
    token, _ = _git_token(workspace_id, db, environment_id)
    return token


def _vercel_token(workspace_id: str, db: Session) -> str:
    """Fetch and decrypt the Vercel token for the workspace."""
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "vercel",
    ).first()
    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail="Vercel credentials not connected — add them in Settings → Integrations")
    creds = decrypt(row.encrypted_credentials)
    token = creds.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Vercel credential is missing a 'token' field")
    return token


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@router.get("/github/issues")
def list_github_issues(
    repo: str,
    label: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return open issues in repo with the given label using the stored GitHub token."""
    token = _github_token(workspace_id, db)
    owner, repo_name = repo.split("/", 1)
    try:
        r = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/issues",
            headers=_gh_headers(token),
            params={"state": "open", "labels": label, "per_page": 100},
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text[:200]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub API")

    return [
        {
            "number":    issue["number"],
            "title":     issue["title"],
            "body":      issue.get("body") or "",
            "url":       issue["html_url"],
            "author":    issue["user"]["login"],
            "labels":    [lb["name"] for lb in issue.get("labels", [])],
            "clone_url": f"https://github.com/{repo}.git",
        }
        for issue in r.json()
        if "pull_request" not in issue  # exclude PRs
    ]


@router.get("/github/repos")
def list_github_repos(
    environment_id: str | None = None,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return repos the workspace's git token can access (provider-aware)."""
    token, provider = _git_token(workspace_id, db, environment_id)
    try:
        if provider == "gitlab":
            r = httpx.get(
                "https://gitlab.com/api/v4/projects",
                headers={"PRIVATE-TOKEN": token},
                params={"membership": True, "per_page": 100, "order_by": "last_activity_at"},
                timeout=10,
            )
            r.raise_for_status()
            return [
                {"full_name": p["path_with_namespace"], "owner": p["namespace"]["path"], "name": p["path"]}
                for p in r.json()
            ]
        elif provider == "bitbucket":
            r = httpx.get(
                "https://api.bitbucket.org/2.0/repositories",
                headers={"Authorization": f"Bearer {token}"},
                params={"pagelen": 100, "sort": "-updated_on", "role": "member"},
                timeout=10,
            )
            r.raise_for_status()
            return [
                {"full_name": repo["full_name"], "owner": repo["workspace"]["slug"], "name": repo["slug"]}
                for repo in r.json().get("values", [])
            ]
        else:
            r = httpx.get(
                f"{GITHUB_API}/user/repos",
                headers=_gh_headers(token),
                params={"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"},
                timeout=10,
            )
            r.raise_for_status()
            return [
                {"full_name": repo["full_name"], "owner": repo["owner"]["login"], "name": repo["name"]}
                for repo in r.json()
            ]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Git API error: {e.response.text[:200]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach git provider API")


@router.get("/github/repos/{owner}/{repo}/branches")
def list_github_branches(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return branch names for the given repo (provider-aware)."""
    token, provider = _git_token(workspace_id, db)
    try:
        if provider == "gitlab":
            from urllib.parse import quote
            encoded = quote(f"{owner}/{repo}", safe="")
            r = httpx.get(
                f"https://gitlab.com/api/v4/projects/{encoded}/repository/branches",
                headers={"PRIVATE-TOKEN": token},
                params={"per_page": 100},
                timeout=10,
            )
            r.raise_for_status()
            return [{"name": b["name"]} for b in r.json()]
        elif provider == "bitbucket":
            r = httpx.get(
                f"https://api.bitbucket.org/2.0/repositories/{owner}/{repo}/refs/branches",
                headers={"Authorization": f"Bearer {token}"},
                params={"pagelen": 100},
                timeout=10,
            )
            r.raise_for_status()
            return [{"name": b["name"]} for b in r.json().get("values", [])]
        else:
            r = httpx.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/branches",
                headers=_gh_headers(token),
                params={"per_page": 100},
                timeout=10,
            )
            r.raise_for_status()
            return [{"name": b["name"]} for b in r.json()]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Git API error: {e.response.text[:200]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach git provider API")


@router.post("/github/repos/{owner}/{repo}/webhook")
def register_github_webhook(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """
    Register a GitHub webhook on the given repo pointing at this Delegator instance.
    Idempotent — if the hook URL already exists, returns the existing hook.
    """
    from app.core.config import settings

    token = _github_token(workspace_id, db)
    webhook_url = f"{settings.api_base_url.rstrip('/')}/webhooks/github?workspace_id={workspace_id}"
    secret = settings.github_webhook_secret or ""

    # Check for existing hook with same URL to stay idempotent
    try:
        existing = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/hooks",
            headers=_gh_headers(token),
            timeout=10,
        )
        if existing.ok:
            hooks = existing.json()
            if isinstance(hooks, list):
                for hook in hooks:
                    if isinstance(hook, dict) and hook.get("config", {}).get("url") == webhook_url:
                        return {"registered": True, "hook_id": hook["id"], "url": webhook_url, "existing": True}
    except Exception:
        pass

    payload = {
        "name": "web",
        "active": True,
        "events": ["issues"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "secret": secret,
            "insecure_ssl": "0",
        },
    }

    try:
        r = httpx.post(
            f"{GITHUB_API}/repos/{owner}/{repo}/hooks",
            headers=_gh_headers(token),
            json=payload,
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text[:300]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub API")

    hook = r.json()
    return {"registered": True, "hook_id": hook["id"], "url": webhook_url, "existing": False}


# ---------------------------------------------------------------------------
# Vercel webhook auto-registration
# ---------------------------------------------------------------------------

VERCEL_TRIGGER_EVENTS = {"deployment.succeeded", "deployment.ready", "deployment.failed", "deployment.error"}


class VercelWebhookRequest(BaseModel):
    event_type: str  # e.g. "deployment.succeeded"


@router.post("/vercel/webhook")
def register_vercel_webhook(
    body: VercelWebhookRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """
    Register a Vercel webhook scoped to this workspace using the stored Vercel token.
    Idempotent — returns the existing webhook if already registered for this URL.
    """
    from app.core.config import settings

    if body.event_type not in VERCEL_TRIGGER_EVENTS:
        raise HTTPException(status_code=400, detail=f"Unsupported event_type '{body.event_type}'. Valid: {sorted(VERCEL_TRIGGER_EVENTS)}")

    token = _vercel_token(workspace_id, db)
    webhook_url = f"{settings.api_base_url.rstrip('/')}/webhooks/vercel?workspace_id={workspace_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Check for existing webhook with same URL to stay idempotent
    try:
        existing_resp = httpx.get(f"{VERCEL_API}/v1/webhooks", headers=headers, timeout=10)
        if existing_resp.ok:
            for hook in existing_resp.json():
                if isinstance(hook, dict) and hook.get("url") == webhook_url:
                    return {"registered": True, "hook_id": hook["id"], "url": webhook_url, "existing": True}
    except Exception:
        pass

    try:
        r = httpx.post(
            f"{VERCEL_API}/v1/webhooks",
            headers=headers,
            json={"url": webhook_url, "events": list(VERCEL_TRIGGER_EVENTS)},
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Vercel API error: {e.response.text[:300]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach Vercel API")

    hook = r.json()
    return {"registered": True, "hook_id": hook.get("id"), "url": webhook_url, "existing": False}
