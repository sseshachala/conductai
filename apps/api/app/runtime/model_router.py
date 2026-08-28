"""ModelRouter — resolves (provider, model, reason) from workspace primitives.

Reads WorkspaceLLMPrimitives (issue #1347) and answers "given a caller\'s
routing preference, which provider+model do we use for this workspace?"

The pure resolve() takes primitives already loaded, so it stays testable
without a DB. resolve_for_workspace() is the DB-fetching wrapper the
runtime callers use.

Priority (highest first):
  1. explicit_model on the block — user pinned a specific model
  2. explicit_provider on the block — use workspace tier_map for that
     provider, else that provider\'s global fallback
  3. workspace.preferred_provider + workspace.tier_map[preferred_provider]
  4. Global fallback (anthropic sonnet)
"""
from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# ── Canonical provider slugs (kept as-is; adapters key on these) ─────────────
ANTHROPIC  = "anthropic"
OPENAI     = "openai"
PERPLEXITY = "perplexity"
TOGETHER   = "together"

_KNOWN_PROVIDERS = {ANTHROPIC, OPENAI, PERPLEXITY, TOGETHER}

# ── Global fallbacks (used when primitives + tier_map miss) ──────────────────
# One model per provider — sensible balanced choice, used when the tier map
# does not have an entry for the requested tier. Not a substitute for the
# workspace primitives; only kicks in for legacy callers / empty maps.
_PROVIDER_FALLBACK: dict[str, str] = {
    ANTHROPIC:  "claude-sonnet-4-6",
    OPENAI:     "gpt-4.1-mini",
    PERPLEXITY: "sonar",
    TOGETHER:   "meta-llama/Llama-3.3-70B-Instruct-Turbo",
}
_GLOBAL_FALLBACK: tuple[str, str, str] = (ANTHROPIC, _PROVIDER_FALLBACK[ANTHROPIC], "global fallback")

# ── Tier normalisation ───────────────────────────────────────────────────────
# Callers pass routing_preference from block config. Historical preference
# names (quality/speed/cost/auto) map onto the primitives tier keys.
_PREF_TO_TIER: dict[str, str] = {
    "cheap":    "cheap",
    "balanced": "balanced",
    "smart":    "smart",
    # legacy names
    "quality":  "smart",
    "speed":    "cheap",
    "cost":     "cheap",
    "auto":     "balanced",
}


def _normalise_tier(pref: str | None) -> str:
    return _PREF_TO_TIER.get((pref or "balanced").strip().lower(), "balanced")


def _infer_provider(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return OPENAI
    if m.startswith("sonar"):
        return PERPLEXITY
    if m.startswith("meta-llama/") or m.startswith("mistralai/") or m.startswith("Qwen/"):
        return TOGETHER
    return ANTHROPIC


def resolve(
    preferred_provider: str,
    tier_map: dict[str, dict[str, str]],
    routing_preference: str | None,
    explicit_model: str | None = None,
    explicit_provider: str | None = None,
) -> tuple[str, str, str]:
    """Pure resolver — no DB access. See module docstring for priority."""
    try:
        if explicit_model:
            return _infer_provider(explicit_model), explicit_model, "user-pinned model"

        tier = _normalise_tier(routing_preference)

        req_provider = (explicit_provider or "").strip().lower()
        if req_provider in _KNOWN_PROVIDERS:
            model = (tier_map.get(req_provider) or {}).get(tier)
            if model:
                return req_provider, model, f"explicit provider {req_provider}: tier_map[{tier}]"
            fallback = _PROVIDER_FALLBACK[req_provider]
            return req_provider, fallback, f"explicit provider {req_provider}: fallback (no tier_map[{tier}])"

        provider = (preferred_provider or ANTHROPIC).strip().lower()
        if provider not in _KNOWN_PROVIDERS:
            provider = ANTHROPIC

        model = (tier_map.get(provider) or {}).get(tier)
        if model:
            return provider, model, f"workspace {provider}: tier_map[{tier}]"
        return provider, _PROVIDER_FALLBACK[provider], f"workspace {provider}: fallback (no tier_map[{tier}])"

    except Exception as e:
        log.warning("model_router.error", error=str(e))
        return _GLOBAL_FALLBACK


def _load_primitives(db: Session, workspace_id: str) -> tuple[str, dict[str, dict[str, str]]]:
    """Fetch workspace primitives, applying the same defaults as the API."""
    from app.models.workspace_llm_primitives import WorkspaceLLMPrimitives
    from app.routers.workspace_llm_primitives import (
        DEFAULT_PREFERRED_PROVIDER,
        DEFAULT_TIER_MAPS,
        _read_stored,
    )
    row = db.get(WorkspaceLLMPrimitives, workspace_id) if (db and workspace_id) else None
    if row is None:
        return DEFAULT_PREFERRED_PROVIDER, {k: dict(v) for k, v in DEFAULT_TIER_MAPS.items()}
    tier_map = _read_stored(row.tier_map)
    if not tier_map:
        tier_map = {k: dict(v) for k, v in DEFAULT_TIER_MAPS.items()}
    return (row.preferred_provider or DEFAULT_PREFERRED_PROVIDER), tier_map


def resolve_for_workspace(
    db: Session,
    workspace_id: str,
    routing_preference: str | None,
    explicit_model: str | None = None,
    explicit_provider: str | None = None,
) -> tuple[str, str, str]:
    """Runtime entry point — reads workspace primitives, delegates to resolve()."""
    preferred_provider, tier_map = _load_primitives(db, workspace_id)
    return resolve(
        preferred_provider=preferred_provider,
        tier_map=tier_map,
        routing_preference=routing_preference,
        explicit_model=explicit_model,
        explicit_provider=explicit_provider,
    )
