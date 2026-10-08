"""GitHub / Vercel / Slack integration proxy endpoints backed by stored credentials
(split from credentials.py).

Second link of the route-registration chain (see credentials_crud).
"""
import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.runtime.integrations.github import _github_headers as _gh_headers
from app.routers.credentials_crud import (
    GITHUB_API,
    VERCEL_API,
    router,
)


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


def _translate_git_error(status_code: int, response_text: str) -> str:
    """Map raw GitHub/GitLab/Bitbucket API errors to actionable user-facing text."""
    body = response_text or ""
    if "Bad credentials" in body:
        return "Git token rejected as invalid or expired. Reconnect in Settings → Environments."
    if "Resource not accessible by personal access token" in body:
        return "Git token does not have permission for this resource. Re-issue the PAT with the correct scopes (Repository → Read for repos, Issues → Read for issues), then reconnect in Settings → Environments."
    if "API rate limit exceeded" in body or "secondary rate limit" in body.lower():
        return "Git API rate limit reached. Wait a few minutes or use a token with higher limits."
    if status_code == 404 and ("Not Found" in body or '"message":"Not Found"' in body):
        return "Resource not found, or your token can't see it. Check the repo/owner and PAT scope."
    if status_code == 401:
        return "Git token rejected (HTTP 401). Reconnect in Settings → Environments."
    if status_code == 403:
        return "Git request forbidden (HTTP 403). Token likely lacks the required scope."
    return f"Git API error (HTTP {status_code}): {body[:200]}"


@router.get("/github/issues")
def list_github_issues(
    repo: str,
    label: str,
    environment_id: str | None = None,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Return open issues in repo with the given label using the stored GitHub token.

    Passes environment_id through to _git_token so a freshly-updated credential
    in a specific environment is honored rather than a stale workspace-level one.
    """
    token = _github_token(workspace_id, db, environment_id)
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
    _: str = Depends(require_permission("platform.credentials.manage")),
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
        raise HTTPException(status_code=e.response.status_code, detail=_translate_git_error(e.response.status_code, e.response.text))
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach git provider API")


@router.get("/github/repos/{owner}/{repo}/branches")
def list_github_branches(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
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
        raise HTTPException(status_code=e.response.status_code, detail=_translate_git_error(e.response.status_code, e.response.text))
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach git provider API")


@router.post("/github/repos/{owner}/{repo}/webhook")
def register_github_webhook(
    owner: str,
    repo: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
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
    _: str = Depends(require_permission("platform.credentials.manage")),
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


# ---------------------------------------------------------------------------
# Slack integrations listing — used by settings dropdowns
# ---------------------------------------------------------------------------

class SlackIntegrationOut(BaseModel):
    id: str
    handle: str
    environment_id: str | None
    environment_name: str | None


@router.get("/integrations/slack", response_model=list[SlackIntegrationOut])
def list_slack_integrations(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> list[SlackIntegrationOut]:
    """List all Slack integrations for the workspace — used by settings dropdowns."""
    from app.models.environment import Environment
    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.service == "slack",
    ).order_by(Integration.created_at).all()
    env_ids = [r.environment_id for r in rows if r.environment_id]
    env_names = {}
    if env_ids:
        envs = db.query(Environment).filter(Environment.id.in_(env_ids)).all()
        env_names = {str(e.id): e.name for e in envs}
    return [
        SlackIntegrationOut(
            id=str(r.id),
            handle=r.handle,
            environment_id=str(r.environment_id) if r.environment_id else None,
            environment_name=env_names.get(str(r.environment_id)) if r.environment_id else None,
        )
        for r in rows
    ]
