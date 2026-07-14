"""
MCP block executor.

Executes MCP tool calls against a configured server.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_mcp(block: dict, state: dict, cred_store: object) -> dict:
    """Execute an MCP tool call.

    Config may specify the server via either:
    - ``credential_key``: legacy path — looks up the credential vault for server_url + token.
    - ``provider``: new canvas path — a UUID from the ``mcp_servers`` table; server_url and
      encrypted_auth are fetched directly from the DB, decrypted at point of use.
    """
    from app.runtime.integrations.mcp_client import call_tool
    from app.runtime.tool_engine import _resolve_refs

    data   = block.get("data", {})
    config = data.get("config", {}) or {}

    credential_key = config.get("credential_key", "")
    server_id      = config.get("provider", "")  # UUID stored by canvas MCP block
    tool_name      = config.get("tool_name", "")
    transport      = config.get("transport", "auto")
    raw_params     = config.get("params", {}) or {}
    params         = _resolve_refs(raw_params, state)

    if not tool_name:
        return {"skipped": True, "reason": "No MCP tool configured"}

    server_url: str | None = config.get("server_url") or None
    token: str | None = None

    if server_id and not credential_key:
        # New path: resolve server from mcp_servers table.
        from sqlalchemy import text as _text
        from app.core.database import get_db as _get_db
        from app.core.crypto import decrypt as _decrypt

        db = next(_get_db())
        try:
            row = db.execute(
                _text("SELECT url, transport, encrypted_auth FROM mcp_servers WHERE id = :id"),
                {"id": server_id},
            ).fetchone()
        finally:
            db.close()

        if not row:
            return {"error": f"MCP server '{server_id}' not found"}

        server_url = row.url
        transport  = row.transport or transport
        token = _decrypt(row.encrypted_auth).get("token") if row.encrypted_auth else None

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
