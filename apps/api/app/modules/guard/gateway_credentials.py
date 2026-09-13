"""Shared Vault credential resolution for canonical gateway profiles."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.credentials import get_credential


def resolve_gateway_key(
    db: Session,
    workspace_id: str,
    credential_ref: str | None,
    provider: str,
    environment_id: str | None,
) -> str | None:
    """Resolve a gateway key from environment Vault data, never profile JSON."""
    if environment_id:
        env = get_credential(db, workspace_id, "env_vars", environment_id)
        key = env.get("PROXY_CONFIG_LLM_UPSTREAM_API_KEY")
        if key:
            return key
    if not credential_ref:
        return None
    handle = credential_ref.removeprefix("vault://").strip("/").split("/")[-1]
    for env_id in (environment_id, None):
        creds = get_credential(db, workspace_id, handle, env_id)
        key = (
            creds.get("LLM_UPSTREAM_API_KEY")
            or creds.get("api_key")
            or creds.get(f"{provider.upper()}_API_KEY")
            or creds.get(f"{provider.lower()}_api_key")
        )
        if key:
            return key
    return None
