"""Runtime resolution for canonical Gateway Profiles."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.gateway_profile import GatewayProfile as GatewayProfileRow
from app.modules.guard.gateway_config import GatewayProfile as GatewayProfileConfig
from app.modules.guard.gateway_credentials import resolve_gateway_key


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

    key = resolve_gateway_key(db, workspace_id, config.credential_ref, provider, environment_id)
    return config.upstream_url, key, config
