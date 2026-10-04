"""Resolve the current credential rather than inferring identity from config."""
from __future__ import annotations

from . import api


def current_identity(cfg: dict) -> dict | None:
    workspace = cfg.get("workspace_id") or cfg.get("workspace")
    server = cfg.get("api_url") or cfg.get("server")
    token = cfg.get("agent_token")
    if not workspace or not server or not token:
        return None
    try:
        response = api.req("GET", f"{server.rstrip('/')}/auth/whoami",
                           api.headers(workspace, token), timeout=5)
        if not isinstance(response, dict):
            return None
        identity = response.get("identity")
        if response.get("workspace_id") != workspace or not isinstance(identity, dict):
            return None
        if not isinstance(identity.get("id"), str) or not identity["id"]:
            return None
        return {"id": identity["id"], "name": identity.get("name") or "Agent"}
    except (Exception, SystemExit):
        return None


def identity_label(cfg: dict) -> str:
    identity = current_identity(cfg)
    return f"{identity['name']} ({identity['id']})" if identity else "unavailable"
