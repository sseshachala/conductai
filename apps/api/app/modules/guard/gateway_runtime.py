"""Runtime resolution for canonical Gateway Profiles.

Two resolver paths live here, selected per request by the
``guard_gateway_profile_v2`` flag:

- **v1** — ``TransportResolver.resolve_profile`` walks the mutable
  ``gateway_profiles.config`` column, matched to the URL's provider
  surface. This is the historical path; kept alive for workspaces that
  haven't yet published a v2 profile.
- **v2** — ``resolve_v2()`` looks up the immutable
  ``gateway_profile_bindings`` row for
  ``(workspace_id, environment_id, model_alias)`` and follows to the
  pinned revision. Zero alphabetical fallback. The revision id is
  returned so callers can pin it through every attempt of the same
  request.

The v1 path also carries a bug fix in this commit: the historical
selector picked by name-then-environment BEFORE checking provider
compatibility, which meant an alphabetically-earlier incompatible row
prevented a later compatible row from ever being tried. Fix:
provider-compatibility becomes the primary filter, env preference is
applied afterwards. Traffic that used to 503 with "no matching profile"
now resolves — a strict improvement.
"""
from __future__ import annotations

import structlog
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.gateway_profile import (
    GatewayProfile as GatewayProfileRow,
    GatewayProfileBinding,
    GatewayProfileRevision,
)
from app.modules.guard.gateway_config import (
    GatewayProfile as GatewayProfileConfig,
    GatewayProfileV2,
)
from app.modules.guard.gateway_credentials import resolve_gateway_key
from app.runtime.provider_transport import (
    ProviderTransport,
    ProviderTransportRegistry,
    get_provider_transport_registry,
)


log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GatewayTransportRuntime:
    """Secret-at-point-of-use runtime selected from a v1 Gateway Profile."""

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


@dataclass(frozen=True)
class ResolvedV2:
    """v2 resolver output — the pinned revision + parsed profile.

    Callers must pin ``revision_id`` in ``routing_meta`` and use the
    same profile object for every attempt of the same request. Never
    re-resolve mid-request; the binding could flip under us if a
    concurrent publish lands.
    """
    revision_id: UUID
    profile: GatewayProfileV2


# ─── v1 resolver (legacy path — bug fixed in this commit) ──────────────


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
        """Resolve the active secret-free v1 profile for one provider surface.

        Selection order (#2001 fix — was: name → env-match → env=NULL,
        THEN provider check, which lost compatible rows behind
        incompatible alphabetically-earlier ones):

        1. Filter to rows compatible with ``provider`` — i.e.
           ``config.provider in {provider, "litellm"}``. Any row that
           can't serve the requested surface is dropped.
        2. Among the compatible rows, prefer an exact environment match.
        3. Fall back to environment=NULL among the compatible rows.
        4. Break ties by profile name (stable, deterministic).
        """
        # Load all workspace rows; filter+order in Python because we need
        # to parse config JSONB to know the effective provider anyway
        # (workspaces rarely have more than a handful of profiles).
        rows = (
            db.query(GatewayProfileRow)
            .filter(GatewayProfileRow.workspace_id == workspace_id)
            .order_by(GatewayProfileRow.name)
            .all()
        )
        if not rows:
            return None

        compatible: list[tuple[GatewayProfileRow, GatewayProfileConfig]] = []
        for row in rows:
            try:
                config = GatewayProfileConfig.model_validate({
                    "name": row.name,
                    "environment_id": row.environment_id,
                    **(row.config or {}),
                })
            except Exception:  # noqa: BLE001 — corrupt row must not poison sibling profiles
                log.warning(
                    "gateway.resolve.corrupt_v1_row",
                    workspace_id=workspace_id, profile_id=str(row.id),
                )
                continue
            if config.provider in {provider, "litellm"}:
                compatible.append((row, config))

        if not compatible:
            return None

        # 2. Env exact match wins.
        if environment_id:
            for row, config in compatible:
                if row.environment_id and str(row.environment_id) == str(environment_id):
                    return config

        # 3. Workspace-default fallback (env=NULL). This is intentionally
        #    the ONLY fallback path — falling to a profile bound to a
        #    different environment would cross the isolation boundary
        #    (staging config serving prod traffic, or vice versa).
        for row, config in compatible:
            if row.environment_id is None:
                return config

        # 4. No env match and no workspace default → no match. Falling
        #    back to some other environment's profile was the bug that
        #    review flagged; the caller sees the fail-closed 503 path,
        #    which is safer than silently routing across environments.
        return None

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


# ─── v2 resolver (#2001) ──────────────────────────────────────────────


def resolve_v2(
    db: Session,
    *,
    workspace_id: str,
    environment_id: str,
    model_alias: str,
) -> ResolvedV2 | None:
    """Look up the published v2 revision for a (workspace, env, alias) triple.

    Exact match only — no alphabetical fallback, no cross-environment
    lookup, no "closest alias." If the binding doesn't exist, the caller
    gets None and (with the fail-closed 503 posture) the client gets a
    clear "unknown model" error.

    The returned ``revision_id`` MUST be pinned in ``routing_meta`` so
    every attempt of the same request uses the same immutable snapshot —
    if a concurrent publish flips the binding mid-request, we do not
    switch under the client.
    """
    binding = (
        db.query(GatewayProfileBinding)
        .filter(
            GatewayProfileBinding.workspace_id == workspace_id,
            GatewayProfileBinding.environment_id == environment_id,
            GatewayProfileBinding.model_alias == model_alias,
        )
        .one_or_none()
    )
    if binding is None:
        return None

    revision = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.id == binding.revision_id)
        .one_or_none()
    )
    if revision is None:
        # A binding pointing at a missing revision means data corruption
        # (ondelete=RESTRICT should have prevented this). Log loud and
        # fail closed rather than fall back to v1.
        log.error(
            "gateway.resolve_v2.orphan_binding",
            workspace_id=workspace_id,
            environment_id=environment_id,
            model_alias=model_alias,
            revision_id=str(binding.revision_id),
        )
        return None

    try:
        profile = GatewayProfileV2.model_validate(revision.snapshot)
    except Exception as exc:  # noqa: BLE001
        # A published snapshot that can't parse is a bug in publish-time
        # validation — no client should suffer from it. Log + fail closed.
        log.error(
            "gateway.resolve_v2.snapshot_invalid",
            revision_id=str(revision.id),
            err=str(exc),
        )
        return None

    return ResolvedV2(revision_id=binding.revision_id, profile=profile)
