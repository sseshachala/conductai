"""
Vercel integration — REST API v13.
Actions: list_deployments, get_deployment, wait_for_deployment, get_project.
"""
import time

import httpx

BASE = "https://api.vercel.com"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def list_deployments(
    token: str,
    project_id: str | None = None,
    team_id: str | None = None,
    limit: int = 10,
) -> dict:
    params: dict = {"limit": limit}
    if project_id:
        params["projectId"] = project_id
    if team_id:
        params["teamId"] = team_id
    r = httpx.get(f"{BASE}/v6/deployments", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    deployments = r.json().get("deployments", [])
    return {
        "deployments": [
            {
                "uid": d["uid"],
                "name": d.get("name"),
                "state": d.get("readyState") or d.get("state"),
                "url": f"https://{d['url']}" if d.get("url") else None,
                "created": d.get("createdAt"),
            }
            for d in deployments
        ]
    }


def get_deployment(token: str, deployment_id: str, team_id: str | None = None) -> dict:
    params: dict = {}
    if team_id:
        params["teamId"] = team_id
    r = httpx.get(f"{BASE}/v13/deployments/{deployment_id}", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    d = r.json()
    return {
        "uid": d.get("uid"),
        "name": d.get("name"),
        "state": d.get("readyState") or d.get("state"),
        "url": f"https://{d['url']}" if d.get("url") else None,
        "alias": d.get("alias", []),
        "created": d.get("createdAt"),
        "ready": d.get("readyAt"),
    }


def wait_for_deployment(
    token: str,
    deployment_id: str,
    team_id: str | None = None,
    timeout_seconds: int = 300,
) -> dict:
    """Poll until deployment readyState == 'READY' or reaches a terminal error state."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = get_deployment(token=token, deployment_id=deployment_id, team_id=team_id)
        state = (info.get("state") or "").upper()
        if state == "READY":
            return info
        if state in ("ERROR", "CANCELED"):
            raise RuntimeError(f"Deployment {deployment_id} ended in state {state}")
        time.sleep(10)
    raise TimeoutError(f"Deployment {deployment_id} did not become READY within {timeout_seconds}s")


def get_project(token: str, project_id: str, team_id: str | None = None) -> dict:
    params: dict = {}
    if team_id:
        params["teamId"] = team_id
    r = httpx.get(f"{BASE}/v9/projects/{project_id}", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    p = r.json()
    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "framework": p.get("framework"),
        "link": p.get("link", {}).get("repo"),
    }


def get_latest_deployment(
    token: str,
    project_id: str,
    branch: str | None = None,
    team_id: str | None = None,
) -> dict:
    """Return the most recent deployment for a project, optionally filtered by branch."""
    params: dict = {"projectId": project_id, "limit": 5}
    if team_id:
        params["teamId"] = team_id
    if branch:
        params["meta-gitBranch"] = branch
    r = httpx.get(f"{BASE}/v6/deployments", headers=_headers(token), params=params, timeout=15)
    r.raise_for_status()
    deployments = r.json().get("deployments", [])
    if not deployments:
        raise ValueError(f"No deployments found for project {project_id}")
    d = deployments[0]
    return {
        "uid": d["uid"],
        "state": d.get("readyState") or d.get("state"),
        "url": f"https://{d['url']}" if d.get("url") else None,
    }


def redeploy(
    token: str,
    deployment_id: str,
    team_id: str | None = None,
) -> dict:
    """Trigger a redeploy of an existing deployment."""
    params: dict = {}
    if team_id:
        params["teamId"] = team_id
    r = httpx.post(
        f"{BASE}/v13/deployments/{deployment_id}/redeploy",
        headers=_headers(token),
        params=params,
        json={},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    return {
        "uid": d.get("uid"),
        "state": d.get("readyState") or d.get("state"),
        "url": f"https://{d['url']}" if d.get("url") else None,
    }


def create_deployment_from_git(
    token: str,
    project_id: str,
    ref: str = "main",
    team_id: str | None = None,
) -> dict:
    """Trigger a new deployment from a git ref (branch or commit SHA)."""
    params: dict = {}
    if team_id:
        params["teamId"] = team_id
    payload: dict = {
        "name": project_id,
        "gitSource": {"ref": ref, "type": "github"},
        "projectSettings": {},
    }
    r = httpx.post(
        f"{BASE}/v13/deployments",
        headers=_headers(token),
        params=params,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    return {
        "uid": d.get("uid") or d.get("id"),
        "state": d.get("readyState") or d.get("state"),
        "url": f"https://{d['url']}" if d.get("url") else None,
    }


TOOL_MAP = {
    "list_deployments": list_deployments,
    "get_deployment": get_deployment,
    "wait_for_deployment": wait_for_deployment,
    "get_project": get_project,
    "get_latest_deployment": get_latest_deployment,
    "redeploy": redeploy,
    "create_deployment_from_git": create_deployment_from_git,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    token = credentials.get("token") or credentials.get("api_key", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown Vercel action: {action}")
    return fn(token=token, **params)
