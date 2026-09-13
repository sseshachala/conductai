"""Runtime resolution for canonical Gateway Profiles."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.credentials import get_credential
from app.core.crypto import decrypt
from app.models.gateway_profile import GatewayProfile as GatewayProfileRow
from app.modules.guard.gateway_config import GatewayProfile as GatewayProfileConfig


def resolve_profile_runtime(
    db: Session,
    workspace_id: str,
    provider: str,
    environment_id: str | None,
) -> tuple[str | None, str | None, GatewayProfileConfig | None]:
    """Return canonical upstream URL, gateway key, and profile if configured.

    Environment-specific profiles win over workspace defaults. Credential values
    are read from encrypted Vault integrations and never from profile JSON.
    """
    query = db.query(GatewayProfileRow).filter(GatewayProfileRow.workspace_id == workspace_id)
    rows = query.order_by(GatewayProfileRow.name).all()
    selected = next((r for r in rows if environment_id and str(r.environment_id) == str(environment_id)), None)
    selected = selected or next((r for r in rows if r.environment_id is None), None)
    if not selected:
        return None, None, None
    config = GatewayProfileConfig.model_validate({"name": selected.name, "environment_id": selected.environment_id, **(selected.config or {})})
    if config.provider not in {provider, "litellm"}:
        return None, None, None

    key = ""
    if environment_id:
        env = get_credential(db, workspace_id, "env_vars", environment_id)
        key = env.get("PROXY_CONFIG_LLM_UPSTREAM_API_KEY") or ""
    if not key and config.credential_ref:
        handle = config.credential_ref.removeprefix("vault://").strip("/").split("/")[-1]
        for env_id in (environment_id, None):
            creds = get_credential(db, workspace_id, handle, env_id)
            key = creds.get("LLM_UPSTREAM_API_KEY") or creds.get("api_key") or creds.get(f"{provider.upper()}_API_KEY") or ""
            if key:
                break
    return config.upstream_url, key or None, config
