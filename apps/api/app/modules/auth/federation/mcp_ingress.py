"""MCP compatibility exports and transport-specific action selection."""
from .ingress import CONNECTION_HEADER, TOKEN_HEADER, authenticate_context, failure, provenance, tool_failure
from .resolver import FederationDenied


def prepare(request, workspace_id, token, body):
    action = "mcp." + str((body.get("params") or {}).get("name", "")) if body.get("method") == "tools/call" else None
    try:
        return authenticate_context(request, workspace_id, token, action=action, resource_type="mcp_request")
    except FederationDenied as error:
        return failure(error, body.get("id"))
