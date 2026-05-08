"""
Railway integration — GraphQL API v2.
Actions: trigger_deployment, get_deployment, wait_for_deployment, list_services, get_service_status.
"""
import time

import httpx

GQL = "https://backboard.railway.app/graphql/v2"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _gql(token: str, query: str, variables: dict | None = None) -> dict:
    r = httpx.post(
        GQL,
        headers=_headers(token),
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"Railway GraphQL error: {body['errors']}")
    return body.get("data", {})


def trigger_deployment(
    token: str,
    service_id: str,
    environment_id: str,
) -> dict:
    """Redeploy a Railway service in an environment."""
    query = """
    mutation ServiceInstanceRedeploy($serviceId: String!, $environmentId: String!) {
      serviceInstanceRedeploy(serviceId: $serviceId, environmentId: $environmentId)
    }
    """
    data = _gql(token, query, {"serviceId": service_id, "environmentId": environment_id})
    return {
        "triggered": True,
        "service_id": service_id,
        "environment_id": environment_id,
        "result": data.get("serviceInstanceRedeploy"),
    }


def list_services(token: str, project_id: str) -> dict:
    """List services in a Railway project."""
    query = """
    query Project($projectId: String!) {
      project(id: $projectId) {
        id
        name
        services {
          edges {
            node {
              id
              name
            }
          }
        }
      }
    }
    """
    data = _gql(token, query, {"projectId": project_id})
    project = data.get("project", {})
    services = [
        {"id": e["node"]["id"], "name": e["node"]["name"]}
        for e in project.get("services", {}).get("edges", [])
    ]
    return {"project_id": project_id, "project_name": project.get("name"), "services": services}


def get_deployment(token: str, deployment_id: str) -> dict:
    """Get status of a specific deployment."""
    query = """
    query Deployment($id: String!) {
      deployment(id: $id) {
        id
        status
        createdAt
        url
        meta
      }
    }
    """
    data = _gql(token, query, {"id": deployment_id})
    d = data.get("deployment", {})
    return {
        "id": d.get("id"),
        "status": d.get("status"),
        "url": d.get("url"),
        "created_at": d.get("createdAt"),
    }


def get_service_deployments(token: str, service_id: str, environment_id: str, limit: int = 5) -> dict:
    """Get recent deployments for a service."""
    query = """
    query ServiceDeployments($serviceId: String!, $environmentId: String!) {
      deployments(input: { serviceId: $serviceId, environmentId: $environmentId }) {
        edges {
          node {
            id
            status
            createdAt
            url
          }
        }
      }
    }
    """
    data = _gql(token, query, {"serviceId": service_id, "environmentId": environment_id})
    edges = data.get("deployments", {}).get("edges", [])[:limit]
    deployments = [
        {
            "id": e["node"]["id"],
            "status": e["node"].get("status"),
            "url": e["node"].get("url"),
            "created_at": e["node"].get("createdAt"),
        }
        for e in edges
    ]
    return {"deployments": deployments}


def list_environments(token: str, project_id: str) -> dict:
    """List environments in a Railway project."""
    query = """
    query Project($projectId: String!) {
      project(id: $projectId) {
        environments {
          edges {
            node {
              id
              name
            }
          }
        }
      }
    }
    """
    data = _gql(token, query, {"projectId": project_id})
    envs = [
        {"id": e["node"]["id"], "name": e["node"]["name"]}
        for e in data.get("project", {}).get("environments", {}).get("edges", [])
    ]
    # Expose the first (production) environment_id at the top level for easy template access.
    return {
        "environments": envs,
        "environment_id": envs[0]["id"] if envs else None,
        "environment_name": envs[0]["name"] if envs else None,
    }


def trigger_and_get_deployment(
    token: str,
    service_id: str,
    environment_id: str,
) -> dict:
    """
    Trigger a redeployment and return the resulting deployment ID.
    Waits up to 15 seconds for Railway to create the new deployment record.
    """
    trigger_deployment(token=token, service_id=service_id, environment_id=environment_id)

    # Railway creates the deployment asynchronously — poll for it.
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(3)
        result = get_service_deployments(token=token, service_id=service_id, environment_id=environment_id, limit=1)
        deployments = result.get("deployments", [])
        if deployments and deployments[0].get("id"):
            d = deployments[0]
            return {
                "deployment_id": d["id"],
                "status": d.get("status"),
                "service_id": service_id,
                "environment_id": environment_id,
            }

    return {"deployment_id": None, "service_id": service_id, "environment_id": environment_id}


def wait_for_deployment(
    token: str,
    deployment_id: str,
    timeout_seconds: int = 300,
) -> dict:
    """Poll until deployment reaches a terminal state. Returns status dict (never raises)."""
    if not deployment_id:
        return {"status": "FAILED", "error": "No deployment_id provided", "healthy": False}

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = get_deployment(token=token, deployment_id=deployment_id)
        status = (info.get("status") or "").upper()
        if status == "SUCCESS":
            return {**info, "healthy": True}
        if status in ("FAILED", "CRASHED", "REMOVED"):
            return {**info, "healthy": False, "error": f"Deployment ended with status {status}"}
        time.sleep(10)

    return {
        "status": "TIMEOUT",
        "deployment_id": deployment_id,
        "healthy": False,
        "error": f"Deployment did not finish within {timeout_seconds}s",
    }


TOOL_MAP = {
    "trigger_deployment": trigger_deployment,
    "trigger_and_get_deployment": trigger_and_get_deployment,
    "list_services": list_services,
    "list_environments": list_environments,
    "get_deployment": get_deployment,
    "get_service_deployments": get_service_deployments,
    "wait_for_deployment": wait_for_deployment,
}


def execute(action: str, params: dict, credentials: dict) -> dict:
    token = credentials.get("token") or credentials.get("api_key", "")
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown Railway action: {action}")

    # Fall back to credential-stored values for project_id and environment_id
    # so workflow blocks that omit these params still work when they're saved
    # in the Railway credentials vault via Settings.
    merged = dict(params)
    for field in ("project_id", "environment_id"):
        if not merged.get(field) and credentials.get(field):
            merged[field] = credentials[field]

    return fn(token=token, **merged)
