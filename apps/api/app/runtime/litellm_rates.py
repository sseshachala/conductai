"""LiteLLM price-table fallback for models the Conduct registry does not list.

Consulted only AFTER ``_DEFAULT_PRICING`` and ``pricing_overrides_json``; it fills
unlisted models and never overrides a registry rate. Returns the registry's own
rate shape (per-1M USD, ``cache_write_by_tier``) so there is one pricing path.

The table is read without importing ``litellm`` (a heavy import) unless the
process already loaded it, and never touches the network.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from functools import lru_cache
from importlib import metadata
from pathlib import Path
from typing import Any

_PROVIDERS = {"google": {"gemini", "vertex_ai-language-models"}}
_PER_1M = Decimal(1_000_000)


@lru_cache(maxsize=1)
def _cost_map() -> dict[str, Any]:
    loaded = sys.modules.get("litellm")
    if loaded is not None and isinstance(getattr(loaded, "model_cost", None), dict):
        return loaded.model_cost
    spec = importlib.util.find_spec("litellm")  # locates the package without importing it
    if spec is None or not spec.submodule_search_locations:
        return {}
    path = Path(spec.submodule_search_locations[0]) / "model_prices_and_context_window_backup.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def litellm_version() -> str:
    try:
        return metadata.version("litellm")
    except metadata.PackageNotFoundError:
        return "unknown"


def _per_1m(entry: dict[str, Any], key: str) -> float | None:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(Decimal(str(value)) * _PER_1M)


def litellm_rates(provider: str, model: str) -> dict[str, Any] | None:
    entry = _cost_map().get(model)
    p = (provider or "").lower().strip()
    if not isinstance(entry, dict) or entry.get("litellm_provider") not in ({p} | _PROVIDERS.get(p, set())):
        return None
    rates: dict[str, Any] = {}
    for ours, theirs in (("input", "input_cost_per_token"), ("output", "output_cost_per_token"),
                         ("cache_read", "cache_read_input_token_cost"),
                         ("cache_write", "cache_creation_input_token_cost")):
        value = _per_1m(entry, theirs)
        if value is not None:
            rates[ours] = value
    if "input" not in rates or "output" not in rates:
        return None
    if "cache_write" in rates:
        tiers = {"ephemeral_5m": rates["cache_write"]}
        one_hour = _per_1m(entry, "cache_creation_input_token_cost_above_1hr")
        if one_hour is not None:
            tiers["ephemeral_1h"] = one_hour
        rates["cache_write_by_tier"] = tiers
    return rates
