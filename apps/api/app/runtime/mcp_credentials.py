"""
Shared MCP credential resolution.

Single source of truth for resolving a token for an MCP server, used by:
- mcp_block._execute_mcp  (playbook type:mcp blocks)
- output_block._resolve_slack_mcp  (type:output via:slack)
- routers/mcp_servers.test_mcp_connection  (Integrations test button)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class McpRegistration:
    id: str
    workspace_id: str
    url: str = field(repr=False)
    transport: str
    token: str | None = field(repr=False)
    governance: dict | None = None

    def call_tool(self, tool_name, tool_input):
        from app.runtime.mcp_governance import response_mode
        if response_mode(self.governance) == "off":
            from app.runtime.integrations.mcp_client import call_tool
            return call_tool(self.url, self.token, tool_name, tool_input, transport=self.transport)
        from app.runtime.mcp_result_gate import call_inspected
        return call_inspected(self, tool_name, tool_input)

# server_name → (integration handle, field) — mirrors _ENV_VAR_MAP in credentials.py
_SERVER_CRED_MAP: dict[str, tuple[str, str]] = {
    "github":  ("git",    "token"),
    "slack":   ("slack",  "token"),
    "linear":  ("linear", "api_key"),
    "vercel":  ("vercel", "token"),
    "sentry":  ("sentry", "token"),
    "datadog": ("datadog","api_key"),
}


def resolve_mcp_registration(
    *,
    server_name: str = "",
    server_id: str = "",
    workspace_id: str,
    environment_id: str | None = None,
    db,
) -> McpRegistration | None:
    """
    Return registration and credentials for the named or UUID-identified MCP server,
    resolving the token from encrypted_auth first, then the Integration store.
    Returns None if the server isn't registered.
    """
    from sqlalchemy import text as _text

    from app.core.crypto import decrypt as _decrypt

    # ponytail: try UUID first (canvas path), then fall back to name lookup
    # if the UUID either wasn't set or points at a stale/deleted row. Old
    # ``if server_id: ... elif server_name: ...`` meant a wrong UUID
    # short-circuited without trying the name — masked stale block configs.
    row = None
    if server_id:
        row = db.execute(
            _text("SELECT id, url, transport, encrypted_auth, name, environment_id, governance FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
            {"id": server_id, "ws": workspace_id},
        ).fetchone()
    if not row and server_name:
        row = db.execute(
            _text("SELECT id, url, transport, encrypted_auth, name, environment_id, governance FROM mcp_servers WHERE name = :name AND workspace_id = :ws"),
            {"name": server_name, "ws": workspace_id},
        ).fetchone()

    if not row:
        return None

    from app.runtime.mcp_governance import (
        MCPGovernanceDenied,
        assert_callable,
        fingerprint,
    )
    governance = getattr(row, "governance", None)
    assert_callable(governance)

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

    if governance is not None:
        from app.runtime.integrations.mcp_client import list_tools
        try:
            tools, _ = list_tools(row.url, token, row.transport or "http")
        except Exception as exc:
            raise MCPGovernanceDenied("MCP catalog verification unavailable") from exc
        digest = fingerprint(tools)
        latest = db.execute(_text("SELECT governance FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
                            {"id": str(row.id), "ws": workspace_id}).fetchone()
        if not latest or not latest.governance or latest.governance != governance:
            raise MCPGovernanceDenied("MCP review changed during verification; retry required")
        assert_callable(latest.governance, digest)
    return McpRegistration(str(row.id), workspace_id, row.url, row.transport or "http", token, governance)


def resolve_mcp_server(**kwargs) -> tuple[str, str, str | None] | None:
    """Compatibility projection for discovery and credential-only callers."""
    registration = resolve_mcp_registration(**kwargs)
    if registration is None:
        return None
    return registration.url, registration.transport, registration.token


def _resolve_from_integration(
    handle: str, field: str, workspace_id: str, environment_id: str | None, db
) -> str | None:
    """Look up a credential from the Integration store."""
    try:
        from app.core.crypto import decrypt as _decrypt
        from app.models.integration import Integration

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
