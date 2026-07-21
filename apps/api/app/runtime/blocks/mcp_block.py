"""
MCP block executor.

Executes MCP tool calls against a configured server.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_mcp(block: dict, state: dict, cred_store: object, workspace_id: str = "") -> dict:
    """Execute an MCP tool call.

    Config may specify the server via either:
    - ``server_name``: playbook path — logical name matched against mcp_servers.name for the workspace.
    - ``provider``: canvas path — UUID from the mcp_servers table.
    - ``credential_key``: legacy path — credential vault lookup for server_url + token.
    """
    from app.runtime.integrations.mcp_client import call_tool
    from app.runtime.tool_engine import _resolve_refs

    data   = block.get("data", {})
    config = data.get("config", {}) or {}

    credential_key = config.get("credential_key", "")
    server_id      = config.get("provider", "")  # UUID stored by canvas MCP block
    server_name    = config.get("server_name", "")  # logical name used in playbooks
    tool_name      = config.get("tool_name", "")
    transport      = config.get("transport", "auto")
    raw_params     = config.get("params", {}) or {}
    params         = _resolve_refs(raw_params, state)

    if not tool_name:
        return {"skipped": True, "reason": "No MCP tool configured"}

    server_url: str | None = config.get("server_url") or None
    token: str | None = None

    if (server_name or server_id) and not credential_key:
        from app.core.database import get_db as _get_db
        from app.runtime.mcp_credentials import resolve_mcp_server

        db = next(_get_db())
        try:
            resolved = resolve_mcp_server(
                server_name=server_name,
                server_id=server_id,
                workspace_id=workspace_id,
                db=db,
            )
        finally:
            db.close()

        if not resolved:
            label = server_name or server_id
            return {"skipped": True, "reason": f"MCP server '{label}' not registered in workspace"}

        server_url, transport, token = resolved

    elif credential_key:
        # Legacy path: resolve server from credential vault.
        creds = cred_store.get(credential_key) if cred_store else {}
        if not creds:
            return {"skipped": True, "reason": f"Credential '{credential_key}' not found"}
        if not server_url:
            server_url = creds.get("server_url") or creds.get("url")
        token = (
            creds.get("token")
            or creds.get("api_key")
            or (creds if isinstance(creds, str) else None)
        )
    else:
        return {"skipped": True, "reason": "MCP block missing server_id (provider) or credential_key"}

    if not server_url:
        return {"skipped": True, "reason": "MCP server URL could not be resolved"}

    if state.get("__dry_run"):
        return {
            "dry_run": True,
            "server_id": server_id or None,
            "credential_key": credential_key or None,
            "tool_name": tool_name,
            "params": params,
        }

    result = call_tool(server_url, token, tool_name, params, transport=transport)

    if isinstance(result, dict):
        return {"tool": tool_name, **result}
    return {"tool": tool_name, "output": str(result)}
