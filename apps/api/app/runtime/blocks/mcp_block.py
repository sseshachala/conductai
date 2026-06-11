"""
MCP block executor.

Executes MCP tool calls against a configured server.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_mcp(block: dict, state: dict, cred_store: object) -> dict:
    """Execute an MCP tool call. Config: credential_key, tool_name, transport, params."""
    from app.runtime.integrations.mcp_client import call_tool
    from app.runtime.executor import _resolve_refs

    data   = block.get("data", {})
    config = data.get("config", {}) or {}

    credential_key = config.get("credential_key", "")
    tool_name      = config.get("tool_name", "")
    transport      = config.get("transport", "auto")
    raw_params     = config.get("params", {}) or {}
    params         = _resolve_refs(raw_params, state)

    if not credential_key:
        return {"skipped": True, "reason": "No MCP credential configured"}
    if not tool_name:
        return {"skipped": True, "reason": "No MCP tool configured"}

    # server_url may come from block config (panel-set) or from the credential vault entry
    server_url = config.get("server_url") or None

    creds = cred_store.get(credential_key) if cred_store else {}
    if not creds:
        return {"skipped": True, "reason": f"Credential '{credential_key}' not found"}

    if not server_url:
        server_url = creds.get("server_url") or creds.get("url")
    token = creds.get("token") or creds.get("api_key") or (creds if isinstance(creds, str) else None)

    if not server_url:
        return {"skipped": True, "reason": f"Credential '{credential_key}' missing server_url"}

    if state.get("__dry_run"):
        return {"dry_run": True, "credential_key": credential_key, "tool_name": tool_name, "params": params}

    result = call_tool(server_url, token, tool_name, params, transport=transport)

    if isinstance(result, dict):
        return {"tool": tool_name, **result}
    return {"tool": tool_name, "output": str(result)}
