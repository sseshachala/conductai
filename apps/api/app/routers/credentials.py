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

    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == body.handle,
    ).first()

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
# GitHub proxy — canvas dropdowns for repo/branch selection
# ---------------------------------------------------------------------------

def _github_token(workspace_id: str, db: Session, environment_id: str | None = None) -> str:
    """Fetch and decrypt the GitHub token for the workspace.

    Lookup order:
    1. Environment-scoped credential matching environment_id (if provided)
    2. Any environment-scoped GitHub credential for the workspace
    3. Legacy global credential with handle == 'github'
    """
    q = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.service == "github",
    )

    row = None
    if environment_id:
        row = q.filter(Integration.environment_id == environment_id).first()
    if not row:
        # prefer env-scoped over global
        row = q.order_by(Integration.environment_id.nullslast()).first()

    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail="GitHub credentials not connected — add them in Settings → Environments")
    creds = decrypt(row.encrypted_credentials)
    token = creds.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="GitHub credential is missing a 'token' field")
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
    """Return repos the stored GitHub token can access (up to 100, sorted by push date)."""
    token = _github_token(workspace_id, db, environment_id)
    try:
        r = httpx.get(
            f"{GITHUB_API}/user/repos",
            headers=_gh_headers(token),
            params={"per_page": 100, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"},
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text[:200]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub API")

    return [
        {"full_name": repo["full_name"], "owner": repo["owner"]["login"], "name": repo["name"]}
        for repo in r.json()
    ]


@router.get("/github/repos/{owner}/{repo}/branches")
def list_github_branches(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return branch names for the given repo using the workspace's GitHub token."""
    token = _github_token(workspace_id, db)
    try:
        r = httpx.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_gh_headers(token),
            params={"per_page": 100},
            timeout=10,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text[:200]}")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub API")

    return [{"name": b["name"]} for b in r.json()]


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
