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

from app.core.auth import get_workspace_id
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.models.integration import Integration

GITHUB_API = "https://api.github.com"

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
    handle: str        # short name used in blocks, e.g. "github", "slack-prod"
    credentials: dict  # raw key/value, will be encrypted


class CredentialOut(BaseModel):
    handle: str
    service: str
    auth_method: str
    fields: list[str]  # field names present (no values)

    class Config:
        from_attributes = True


@router.get("", response_model=list[CredentialOut])
def list_credentials(db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
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
def upsert_credential(body: CredentialUpsert, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    if not body.credentials:
        raise HTTPException(status_code=422, detail="credentials dict must not be empty")

    existing = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == body.handle,
    ).first()

    auth_method = "api_key" if "api_key" in body.credentials else "oauth"

    if existing:
        existing.service = body.service
        existing.auth_method = auth_method
        existing.encrypted_credentials = encrypt(body.credentials)
    else:
        row = Integration(
            workspace_id=workspace_id,
            service=body.service,
            handle=body.handle,
            auth_method=auth_method,
            encrypted_credentials=encrypt(body.credentials),
        )
        db.add(row)

    db.commit()
    return {"handle": body.handle, "service": body.service, "saved": True}


@router.delete("/{handle}", status_code=204)
def delete_credential(handle: str, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == handle,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# GitHub proxy — canvas dropdowns for repo/branch selection
# ---------------------------------------------------------------------------

def _github_token(workspace_id: str, db: Session) -> str:
    """Fetch and decrypt the GitHub token for the workspace."""
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "github",
    ).first()
    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail="GitHub credentials not connected — add them in Settings → Integrations")
    creds = decrypt(row.encrypted_credentials)
    token = creds.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="GitHub credential is missing a 'token' field")
    return token


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@router.get("/github/repos")
def list_github_repos(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return repos the stored GitHub token can access (up to 100, sorted by push date)."""
    token = _github_token(workspace_id, db)
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
