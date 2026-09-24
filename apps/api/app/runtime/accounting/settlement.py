"""Settlement-side entry point for the shared accounting engine (#2209 PR 4).

Publishes ``compute_settlement_micros`` — the microdollar amount to
charge for a given upstream response. Same math ``shadow_write`` performs
to populate ``calculated_cost_microdollars``; sharing the helper means
gateway_handler and shadow_writer can never drift.

Cutover (PR 4, Option A): ``gateway_handler`` calls this unconditionally.
No flag, no fallback to legacy ``_extract_token_counts``/``_compute_audit_cost``.
When the response has no usable usage, returns None and the caller records
the settlement as PENDING_RECONCILER (safe: the reconciler backfills it).
"""

from __future__ import annotations

import base64
from typing import Any, Mapping, Optional, Sequence

from app.runtime.accounting.contracts import (
    PricingCompleteness,
    UsageCompleteness,
)
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

    Returns None when the settlement cannot be a final charge:
    - no response bytes,
    - no extractable usage,
    - usage is PARTIAL (e.g. interrupted stream — later frames may add
      tokens we haven't seen),
    - pricing is INCOMPLETE (e.g. unknown cache-write tier — the number
      we'd return is a lower bound).

    Callers pass None to ``settle_reservations`` which records
    PENDING_RECONCILER (safe — reservation stays open, reconciler
    finalizes later from the receipt).

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
    if norm.completeness != UsageCompleteness.COMPLETE:
        # PARTIAL / UNAVAILABLE — settling now would charge a lower bound.
        # Leave PENDING_RECONCILER; reconciler re-normalizes when it can
        # see the full body (or writes the row unpriced honestly).
        return None
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
    if price.completeness not in (
        PricingCompleteness.PRICED,
        PricingCompleteness.OVERRIDE_APPLIED,
    ):
        # UNPRICED (unknown model, strict) or INCOMPLETE (unknown cache
        # tier — some tokens dropped from the total). Either case, the
        # number is not a defensible final charge.
        return None
    return price.microdollars


def settle_micros_for_attempts(
    *,
    attempts_meta: Optional[Sequence[Mapping[str, Any]]],
    request_provider: str,
    request_model: str,
    operation: str,
    winner_response_bytes: Optional[bytes],
    strict: bool = True,
) -> Optional[int]:
    """Aggregate settlement across every attempt the coordinator recorded.

    The failed attempts before the winning one may have consumed provider
    tokens (rate-limit responses, quota rejections, and mid-generation
    errors all still bill). Settling only from the winner would understate
    real spend and let the reconciler drift from live totals.

    Rules (all must hold for a definitive settle):
    - Every recorded attempt must have priceable bytes: the winner's
      response bytes, or a base64-decodable ``response_bytes_b64`` on the
      failed attempt (captured by the coordinator when the upstream
      returned an HTTPStatusError with a body).
    - Every attempt's usage + pricing must be COMPLETE / PRICED (or
      OVERRIDE_APPLIED). PARTIAL or INCOMPLETE anywhere → None →
      PENDING_RECONCILER.
    - Each attempt uses ITS OWN ``provider_or_integration`` + ``model``
      for pricing (mixed-target profiles route to different providers on
      fallback, and each has its own rate card).

    When ``attempts_meta`` is None or empty, falls back to the winner-only
    path (single dispatch, legacy behavior).

    Returns None to signal PENDING_RECONCILER so ``settle_reservations``
    leaves the reservation open — never releases and never charges a
    lower bound.
    """
    if not attempts_meta:
        return compute_settlement_micros(
            provider=request_provider,
            model=request_model,
            operation=operation,
            response_bytes=winner_response_bytes,
            strict=strict,
        )

    total = 0
    for attempt in attempts_meta:
        att_provider = attempt.get("provider_or_integration") or request_provider
        att_model = attempt.get("model") or request_model
        succeeded = bool(attempt.get("succeeded"))
        if succeeded:
            att_bytes = winner_response_bytes
        else:
            b64 = attempt.get("response_bytes_b64")
            if not b64:
                # Failed attempt with no captured bytes. Provider may have
                # billed anyway (partial output before disconnect). We
                # cannot honestly price this attempt — force PENDING.
                return None
            try:
                att_bytes = base64.b64decode(b64)
            except Exception:
                return None
        micros = compute_settlement_micros(
            provider=att_provider,
            model=att_model,
            operation=operation,
            response_bytes=att_bytes,
            strict=strict,
        )
        if micros is None:
            return None
        total += micros
    return total
