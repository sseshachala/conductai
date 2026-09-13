"""Runtime resolution for canonical Gateway Profiles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.gateway_profile import GatewayProfile as GatewayProfileRow
from app.modules.guard.gateway_config import GatewayProfile as GatewayProfileConfig
from app.modules.guard.gateway_credentials import resolve_gateway_key
from app.runtime.provider_transport import (
    ProviderTransport,
    ProviderTransportRegistry,
    get_provider_transport_registry,
)


@dataclass(frozen=True)
class GatewayTransportRuntime:
    """Secret-at-point-of-use runtime selected from a Gateway Profile."""

    upstream_url: str | None
    api_key: str | None
    profile: GatewayProfileConfig
    transport: ProviderTransport

    def create_client(
        self,
        *,
        provider: str,
        pricing_snapshot: dict[str, Any] | None = None,
    ) -> Any:
        """Build the normalized LLM client from this resolved profile runtime."""
        if not self.api_key:
            raise ValueError("Gateway profile credential is unavailable")
        return self.transport.create_client(
            provider=provider,
            api_key=self.api_key,
            pricing_snapshot=pricing_snapshot,
            base_url=self.upstream_url,
        )


class TransportResolver:
    """Resolve profile, Vault credential, and provider transport together."""

    def __init__(self, registry: ProviderTransportRegistry | None = None) -> None:
        self._registry = registry or get_provider_transport_registry()

    def resolve_profile(
        self,
        db: Session,
        workspace_id: str,
        provider: str,
        environment_id: str | None,
    ) -> GatewayProfileConfig | None:
        """Resolve the active secret-free profile for one provider surface."""
        query = db.query(GatewayProfileRow).filter(GatewayProfileRow.workspace_id == workspace_id)
        rows = query.order_by(GatewayProfileRow.name).all()
        selected = next(
            (r for r in rows if environment_id and str(r.environment_id) == str(environment_id)),
            None,
        )
        selected = selected or next((r for r in rows if r.environment_id is None), None)
        if not selected:
            return None
        config = GatewayProfileConfig.model_validate(
            {
                "name": selected.name,
                "environment_id": selected.environment_id,
                **(selected.config or {}),
            }
        )
        if config.provider not in {provider, "litellm"}:
            return None
        return config

    def resolve(
        self,
        db: Session,
        workspace_id: str,
        provider: str,
        environment_id: str | None,
    ) -> GatewayTransportRuntime | None:
        config = self.resolve_profile(db, workspace_id, provider, environment_id)
        if config is None:
            return None

        key = resolve_gateway_key(
            db,
            workspace_id,
            config.credential_ref,
            provider,
            environment_id,
        )
        return GatewayTransportRuntime(
            upstream_url=config.upstream_url,
            api_key=key,
            profile=config,
            transport=self._registry.for_provider(config.provider),
        )


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
    runtime = TransportResolver().resolve(db, workspace_id, provider, environment_id)
    if runtime is None:
        return None, None, None
    return runtime.upstream_url, runtime.api_key, runtime.profile
