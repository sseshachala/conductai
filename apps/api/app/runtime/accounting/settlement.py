"""Settlement-side entry point for the shared accounting engine (#2209 PR 4).

Publishes a single function ``compute_settlement_micros`` that returns
the microdollar amount to charge for a given upstream response. It's
the same math ``shadow_write`` performs to populate
``calculated_cost_microdollars``; sharing the helper means gateway_handler
and shadow_writer can never drift.

Purpose:

- ``gateway_handler`` calls it when
  ``settings.new_engine_settles_for_workspace(workspace_id)`` is True.
  Legacy ``_extract_token_counts`` + ``_compute_audit_cost`` are bypassed.
- ``shadow_writer`` calls it internally (existing behavior).

Returns None when the response has no usable usage (no bytes, empty
usage payload, or unpriced model under strict mode). Callers fall back
to legacy math OR leave ``actual_micros=None`` so ``settle_reservations``
records the row as PENDING_RECONCILER (safe: the reconciler handles it).
"""

from __future__ import annotations

from typing import Optional

from app.runtime.accounting.normalizers import (
    ProviderFamily,
    normalize_json,
    normalize_sse,
)
from app.runtime.accounting.pricing import default_pricing_service


_FAMILY_BY_PROVIDER: dict[str, ProviderFamily] = {
    "anthropic": ProviderFamily.ANTHROPIC_MESSAGES,
    "openai": ProviderFamily.OPENAI_CHAT,
    "perplexity": ProviderFamily.OPENAI_CHAT,
    "litellm": ProviderFamily.LITELLM,
}


def _family_for(provider: str, operation: str) -> ProviderFamily:
    if operation and "responses" in operation.lower():
        return ProviderFamily.OPENAI_RESPONSES
    return _FAMILY_BY_PROVIDER.get((provider or "").lower(), ProviderFamily.OPENAI_CHAT)


def _looks_like_sse(response_bytes: bytes) -> bool:
    if not response_bytes:
        return False
    head = response_bytes[:64].lstrip()
    return head.startswith((b"event:", b"data:", b":"))


def compute_settlement_micros(
    *,
    provider: str,
    model: str,
    operation: str,
    response_bytes: Optional[bytes],
    strict: bool = True,
) -> Optional[int]:
    """Compute the microdollar cost of one upstream inference response.

    Same normalizer + pricing path shadow_write uses. Returns None when
    usage isn't extractable — caller falls back to legacy math OR
    marks the settlement PENDING_RECONCILER.

    ``strict=True`` (default) means an unknown model returns None instead
    of silently taking a fallback rate. Preserves invariant #9 end-to-end.
    """
    if not response_bytes:
        return None
    family = _family_for(provider, operation)
    if _looks_like_sse(response_bytes):
        norm = normalize_sse(family, response_bytes)
    else:
        norm = normalize_json(family, response_bytes)
    tokens = norm.tokens
    if (
        tokens.total_input_tokens is None
        and tokens.total_output_tokens is None
        and tokens.cache_read_tokens is None
        and not tokens.cache_write_tokens_by_tier
    ):
        return None
    price = default_pricing_service().price_tokens(
        provider,
        model,
        uncached_input_tokens=tokens.uncached_input_tokens,
        output_tokens=tokens.total_output_tokens,
        cache_read_tokens=tokens.cache_read_tokens,
        cache_write_tokens_by_tier=dict(tokens.cache_write_tokens_by_tier or {}) or None,
        strict=strict,
    )
    return price.microdollars
