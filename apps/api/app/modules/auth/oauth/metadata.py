"""RFC 8414 Authorization Server Metadata + RFC 9728 Resource Metadata.

Published at /.well-known/oauth-authorization-server so MCP clients can
auto-discover the token / authorize / register endpoints.

`issuer` must match exactly what clients derive from the resource URL —
we serve at api.conductai.ai so that's the issuer.
"""
from __future__ import annotations

import os
from typing import Any


def _issuer() -> str:
    return os.getenv("CONDUCT_OAUTH_ISSUER") or "https://api.conductai.ai"


def build_authorization_server_metadata() -> dict[str, Any]:
    """RFC 8414 metadata document. Static — no per-request state."""
    base = _issuer()
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": [
            "authorization_code",
            "refresh_token",
            "urn:ietf:params:oauth:grant-type:token-exchange",
        ],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }
