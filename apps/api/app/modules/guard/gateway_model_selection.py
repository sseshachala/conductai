"""Resolve client selections to published, workspace-scoped Gateway revisions."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.gateway_profile import GatewayProfile, GatewayProfileRevision
from app.modules.guard.gateway_config import GatewayProfileV2
from app.modules.guard.gateway_runtime import ResolvedV2

TIERS = frozenset({"cheap", "balanced", "smart"})


@dataclass(frozen=True)
class ModelSelection:
    cond_code: str
    resolved: ResolvedV2
    metadata: dict

    @property
    def model_id(self) -> str:
        return f"cond-{self.cond_code}-{self.resolved.profile.model_alias}"


def select_model(db, workspace_id: str, requested: object, operation: str) -> ModelSelection:
    if not isinstance(requested, str) or not requested.strip():
        raise HTTPException(400, "Select a published Gateway model ID, model alias, or tier.")
    model = requested.strip()
    provider = None
    metadata = {"requested_model": model, "resolution_source": "published_gateway_profile"}
    prefix, separator, tail = model.partition("/")
    tier = model if model in TIERS else tail if separator and tail in TIERS else None
    if tier:
        from app.runtime.model_router import _KNOWN_PROVIDERS, resolve_for_workspace
        if separator and prefix not in _KNOWN_PROVIDERS:
            raise HTTPException(400, "Unknown tier provider. Use a configured LLM Model Primitives provider.")
        provider, model, reason = resolve_for_workspace(
            db, workspace_id, tier, explicit_provider=prefix if separator else None,
        )
        metadata.update(tier_form=requested, resolved_model=model, resolved_provider=provider,
                        resolution_source="workspace_primitives", reason=reason)

    # Join the active pointer and profile ownership in one read. Never match a
    # working copy, or resolve the pointer again after selecting a candidate.
    rows = (
        db.query(GatewayProfile, GatewayProfileRevision)
        .join(GatewayProfileRevision,
              (GatewayProfileRevision.id == GatewayProfile.active_revision_id)
              & (GatewayProfileRevision.profile_id == GatewayProfile.id))
        .filter(GatewayProfile.workspace_id == workspace_id,
                GatewayProfile.schema_version == "2")
        .all()
    )
    matches = []
    incompatible = False
    for row, revision in rows:
        try:
            profile = GatewayProfileV2.model_validate(revision.snapshot)
        except ValidationError:
            continue
        # An alias intentionally selects a routing profile, including its
        # fallback policy. A concrete model must not silently select another
        # model through a mixed-model profile; use its full cond ID instead.
        alias_match = not tier and profile.model_alias == model
        model_match = bool(profile.targets) and all(
            getattr(target, "model", None) == model
            and (provider is None or getattr(target, "provider", None) == provider)
            for target in profile.targets
        )
        if not (alias_match or model_match):
            continue
        if operation not in profile.accepts:
            incompatible = True
            continue
        matches.append(ModelSelection(row.cond_code, ResolvedV2(revision.id, profile), metadata))
    if len(matches) > 1:
        raise HTTPException(409, "Multiple published Gateway profiles match. Select the full cond-<code>-<alias> ID.")
    if not matches:
        if incompatible:
            raise HTTPException(400, f"No matching published profile accepts {operation}. Select a compatible Gateway profile; cross-provider conversion is not available for this selection.")
        raise HTTPException(404, "No published Gateway profile matches this model in your workspace. Publish a matching profile or select its full cond-<code>-<alias> ID. LLM Model Primitives alone do not authorize routing.")
    return matches[0]


def select_model_owned(workspace_id: str, requested: object, provider: str, upstream_path: str) -> ModelSelection:
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.runtime.gateway_v2_bridge import map_operation
    operation = map_operation(provider, upstream_path)
    if operation is None:
        raise HTTPException(501, "This Gateway operation does not support published model selection.")
    with SessionLocal() as db:
        set_workspace_rls(db, workspace_id)
        return select_model(db, workspace_id, requested, operation)
