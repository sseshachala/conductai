"""
Shared MCP credential resolution.

Single source of truth for resolving a token for an MCP server, used by:
- mcp_block._execute_mcp  (playbook type:mcp blocks)
- output_block._resolve_slack_mcp  (type:output via:slack)
- routers/mcp_servers.test_mcp_connection  (Integrations test button)
"""
from __future__ import annotations

# server_name → (integration handle, field) — mirrors _ENV_VAR_MAP in credentials.py
_SERVER_CRED_MAP: dict[str, tuple[str, str]] = {
    "github":  ("git",    "token"),
    "slack":   ("slack",  "token"),
    "linear":  ("linear", "api_key"),
    "vercel":  ("vercel", "token"),
    "sentry":  ("sentry", "token"),
    "datadog": ("datadog","api_key"),
}


def resolve_mcp_server(
    *,
    server_name: str = "",
    server_id: str = "",
    workspace_id: str,
    environment_id: str | None = None,
    db,
) -> tuple[str, str, str | None] | None:
    """
    Return (url, transport, token) for the named or UUID-identified MCP server,
    resolving the token from encrypted_auth first, then the Integration store.
    Returns None if the server isn't registered.
    """
    from sqlalchemy import text as _text
    from app.core.crypto import decrypt as _decrypt

    if server_id:
        row = db.execute(
            _text("SELECT url, transport, encrypted_auth, name, environment_id FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
            {"id": server_id, "ws": workspace_id},
        ).fetchone()
    elif server_name:
        row = db.execute(
            _text("SELECT url, transport, encrypted_auth, name, environment_id FROM mcp_servers WHERE name = :name AND workspace_id = :ws"),
            {"name": server_name, "ws": workspace_id},
        ).fetchone()
    else:
        return None

    if not row:
        return None

    token: str | None = None

    # 1. Prefer token stored directly on the MCP server row
    if row.encrypted_auth:
        token = _decrypt(row.encrypted_auth).get("token") or None

    # 2. Fall back to Integration store (system-seeded servers have no encrypted_auth)
    if not token:
        effective_name = server_name or (row.name or "")
        handle_field = _SERVER_CRED_MAP.get(effective_name)
        if handle_field:
            handle, field = handle_field
            token = _resolve_from_integration(handle, field, workspace_id, environment_id or row.environment_id, db)

    return (row.url, row.transport or "http", token)


def _resolve_from_integration(
    handle: str, field: str, workspace_id: str, environment_id: str | None, db
) -> str | None:
    """Look up a credential from the Integration store."""
    try:
        from app.models.integration import Integration
        from app.core.crypto import decrypt as _decrypt

        q = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.handle == handle,
        )
        if environment_id:
            # prefer env-scoped row, fall back to workspace-wide
            env_row = q.filter(Integration.environment_id == environment_id).first()
            row = env_row or q.filter(Integration.environment_id.is_(None)).first()
        else:
            row = q.first()

        if not row or not row.encrypted_credentials:
            return None
        creds = _decrypt(row.encrypted_credentials) or {}
        return creds.get(field) or None
    except Exception:
        return None


def resolve_mcp_token_by_credential_key(
    credential_key: str, workspace_id: str, environment_id: str | None, db
) -> str | None:
    """Resolve a token by env-var name (e.g. GITHUB_TOKEN) from the Integration store."""
    from app.routers.credentials import _ENV_VAR_MAP
    entry = _ENV_VAR_MAP.get(credential_key)
    if not entry:
        return None
    handle, field = entry
    return _resolve_from_integration(handle, field, workspace_id, environment_id, db)
