from __future__ import annotations

import json
import structlog
from copy import deepcopy
from typing import Any

from app.core.config import settings

log = structlog.get_logger(__name__)

_DEFAULT_PRICING: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-sonnet-4-6": {
            "input": 3.00,
            "output": 15.00,
            "cache_read": 0.30,
            "cache_write": 3.75,
        },
        "claude-opus-4-7": {
            "input": 15.00,
            "output": 75.00,
            "cache_read": 1.50,
            "cache_write": 18.75,
        },
        "claude-haiku-4-5-20251001": {
            "input": 0.80,
            "output": 4.00,
            "cache_read": 0.08,
            "cache_write": 1.00,
        },
    },
    "openai": {
        "gpt-4.1": {
            "input": 2.00,
            "output": 8.00,
        },
        "gpt-4.1-mini": {
            "input": 0.40,
            "output": 1.60,
        },
    },
}

_DEFAULTS_BY_PROVIDER: dict[str, str] = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4.1-mini",
}


def _merge_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    providers = overrides.get("providers")
    if not isinstance(providers, dict):
        return out

    for provider, models in providers.items():
        if not isinstance(provider, str) or not isinstance(models, dict):
            continue
        p = provider.lower().strip()
        out.setdefault(p, {})
        for model, rates in models.items():
            if not isinstance(model, str) or not isinstance(rates, dict):
                continue
            clean_rates: dict[str, float] = {}
            for key in ("input", "output", "cache_read", "cache_write"):
                if key in rates:
                    try:
                        clean_rates[key] = float(rates[key])
                    except (TypeError, ValueError):
                        continue
            if clean_rates:
                out[p][model] = clean_rates
    return out


def freeze_pricing_snapshot() -> dict[str, Any]:
    pricing = deepcopy(_DEFAULT_PRICING)
    version = settings.pricing_registry_version or "unknown"

    raw = (settings.pricing_overrides_json or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                pricing = _merge_overrides(pricing, parsed)
                parsed_version = parsed.get("version")
                if isinstance(parsed_version, str) and parsed_version.strip():
                    version = parsed_version.strip()
        except Exception as e:
            log.warning("pricing.override_parse_failed", error=str(e))

    return {
        "version": version,
        "providers": pricing,
    }


def get_model_rates(
    provider: str,
    model: str,
    pricing_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, float], str]:
    snap = pricing_snapshot or freeze_pricing_snapshot()
    version = str(snap.get("version") or "unknown")

    providers = snap.get("providers") or {}
    if not isinstance(providers, dict):
        providers = {}

    p = (provider or "anthropic").lower().strip()
    provider_map = providers.get(p)
    if not isinstance(provider_map, dict):
        provider_map = {}

    rates = provider_map.get(model)
    if not isinstance(rates, dict):
        default_model = _DEFAULTS_BY_PROVIDER.get(p)
        if default_model:
            rates = provider_map.get(default_model)
        if not isinstance(rates, dict):
            fallback_provider = p if p in _DEFAULT_PRICING else "anthropic"
            fallback_model = _DEFAULTS_BY_PROVIDER.get(fallback_provider, "claude-sonnet-4-6")
            rates = _DEFAULT_PRICING[fallback_provider][fallback_model]

    out = {
        "input": float(rates.get("input", 0.0)),
        "output": float(rates.get("output", 0.0)),
        "cache_read": float(rates.get("cache_read", 0.0)),
        "cache_write": float(rates.get("cache_write", 0.0)),
    }
    return out, version


def pricing_note(provider: str, model: str, rates: dict[str, float], version: str) -> str:
    p = (provider or "").lower().strip() or "unknown"
    return (
        f"{p}/{model} @ v{version} — "
        f"input ${rates.get('input', 0):.2f}/1M, output ${rates.get('output', 0):.2f}/1M"
    )
