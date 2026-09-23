"""Unified pricing service (issue #2209, Session 2).

Wraps ``app/runtime/pricing.py`` — the workspace's pricing registry — with:

1. Explicit ``PricingCompleteness`` semantics. Unknown models are UNPRICED,
   never silently priced as another model (invariant #9). The legacy
   ``strict=False`` silent-fallback behavior stays available for compat
   wrappers, but is signalled distinctly so Session 4 shadow can detect it.
2. Integer microdollar arithmetic. All monetary math in the new engine goes
   through this service; float USD is a display-only concern.
3. Reasoning tokens are **never** priced separately (invariant #5). Callers
   that pass a reasoning breakdown get it back untouched; cost is computed
   against ``output_tokens`` in full.
4. Cache tier breakdown. Cache reads and per-tier cache writes are priced
   from the same rate card that already exists in ``runtime/pricing.py``.

Session 2 compat wrappers use ``strict=False`` to preserve today's behavior.
Session 4+ new callers use ``strict=True``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Optional

from app.runtime.accounting.contracts import (
    MICRODOLLARS_PER_USD,
    PricingCompleteness,
)
from app.runtime.pricing import (
    UnknownModelPricing,
    freeze_pricing_snapshot,
    get_model_rates,
)

_DEC_1M = Decimal(1_000_000)


@dataclass(frozen=True)
class RateCard:
    """Priced rates for one (provider, model) pair.

    All rates are per-1M-token USD as Decimal. ``cache_write_per_1m_usd``
    remains as the single-tier fallback rate. Session 6J adds
    ``cache_write_by_tier_per_1m_usd`` for providers that price different
    cache-write durations differently (Anthropic ephemeral_5m vs
    ephemeral_1h). Empty map ⇒ every tier uses the single-tier rate.
    """

    provider: str
    model: str
    input_per_1m_usd: Decimal
    output_per_1m_usd: Decimal
    cache_read_per_1m_usd: Decimal
    cache_write_per_1m_usd: Decimal
    request_fee_usd: Decimal
    version: str
    completeness: PricingCompleteness
    cache_write_by_tier_per_1m_usd: Mapping[str, Decimal] = field(default_factory=dict)

    @classmethod
    def from_legacy_rates(
        cls,
        provider: str,
        model: str,
        rates: Mapping[str, Any],
        version: str,
        completeness: PricingCompleteness,
    ) -> "RateCard":
        # Reviewer #3 (#2221 review at bbcb5388): pricing snapshots can
        # now declare per-tier cache-write rates via a
        # ``cache_write_by_tier`` sub-map. Legacy snapshots keep the
        # single ``cache_write`` scalar and land with an empty tier map.
        tier_map: dict[str, Decimal] = {}
        tiered = rates.get("cache_write_by_tier")
        if isinstance(tiered, Mapping):
            for tier, rate in tiered.items():
                try:
                    tier_map[str(tier)] = Decimal(str(rate))
                except (ValueError, TypeError, ArithmeticError):
                    continue
        return cls(
            provider=provider,
            model=model,
            input_per_1m_usd=Decimal(str(rates.get("input", 0.0))),
            output_per_1m_usd=Decimal(str(rates.get("output", 0.0))),
            cache_read_per_1m_usd=Decimal(str(rates.get("cache_read", 0.0))),
            cache_write_per_1m_usd=Decimal(str(rates.get("cache_write", 0.0))),
            request_fee_usd=Decimal(str(rates.get("request_fee_usd", 0.0))),
            version=version,
            completeness=completeness,
            cache_write_by_tier_per_1m_usd=tier_map,
        )


@dataclass(frozen=True)
class PriceResult:
    """Result of pricing a token consumption record.

    ``microdollars`` is None only when the cost was not computable
    (no rate + no request fee, or explicit UNPRICED strict rejection).
    A returned zero is a legitimate zero (invariant #4).
    """

    microdollars: Optional[int]
    completeness: PricingCompleteness
    pricing_version: str
    provenance: Mapping[str, Any] = field(default_factory=dict)


class PricingService:
    """One canonical pricing service for the accounting engine.

    Wraps the workspace pricing snapshot. Callers that want the old silent-
    fallback behavior pass ``strict=False``; new callers pass ``strict=True``
    to get an UNPRICED result rather than a mis-attributed rate.
    """

    def __init__(self, pricing_snapshot: Optional[dict[str, Any]] = None) -> None:
        self._snapshot = pricing_snapshot or freeze_pricing_snapshot()
        self._version = str(self._snapshot.get("version") or "unknown")

    @property
    def pricing_version(self) -> str:
        return self._version

    @property
    def snapshot(self) -> dict[str, Any]:
        return self._snapshot

    def get_rate_card(self, provider: str, model: str, *, strict: bool = True) -> RateCard:
        """Look up rates for (provider, model). Raises UnknownModelPricing under strict.

        Under strict=False, falls back to the workspace default per the legacy
        ``get_model_rates`` behavior. This is a signaled fallback: the returned
        RateCard carries PricingCompleteness.OVERRIDE_APPLIED so the caller can
        detect it.
        """
        providers = self._snapshot.get("providers") or {}
        exact = isinstance(providers, dict) and isinstance(
            providers.get((provider or "").lower().strip()), dict
        ) and isinstance(
            providers[(provider or "").lower().strip()].get(model), dict
        )

        rates, version = get_model_rates(
            provider, model, pricing_snapshot=self._snapshot, strict=strict
        )
        # Reviewer #3 (#2221 review at bbcb5388): ``get_model_rates``
        # flattens the model dict to a fixed set of keys and drops
        # ``cache_write_by_tier``. Merge the raw model dict on top so
        # the tier map (if any) reaches RateCard.from_legacy_rates.
        if exact:
            raw_model = providers[(provider or "").lower().strip()].get(model, {})
            if isinstance(raw_model, dict) and "cache_write_by_tier" in raw_model:
                rates = {**rates, "cache_write_by_tier": raw_model["cache_write_by_tier"]}
        completeness = PricingCompleteness.PRICED if exact else PricingCompleteness.OVERRIDE_APPLIED
        return RateCard.from_legacy_rates(provider, model, rates, version, completeness)

    def price_tokens(
        self,
        provider: str,
        model: str,
        *,
        uncached_input_tokens: Optional[int],
        output_tokens: Optional[int],
        cache_read_tokens: Optional[int] = None,
        cache_write_tokens: Optional[int] = None,
        cache_write_tokens_by_tier: Optional[Mapping[str, int]] = None,
        request_fee: bool = True,
        strict: bool = True,
    ) -> PriceResult:
        """Compute the microdollar cost for one attempt.

        ``uncached_input_tokens`` is the FRESH input token count only. The
        cache buckets are priced separately at their own rates. Prior API
        accepted a ``total_input_tokens`` and subtracted ``cache_read``,
        but this was ambiguous across providers (Anthropic's ``input_tokens``
        excludes cache reads; OpenAI's ``prompt_tokens`` includes cached
        tokens). The reviewer at #2221 caught the resulting double-subtract.

        ``output_tokens`` is the FULL output count and already includes
        reasoning tokens — invariant #5. Callers must NOT add
        ``reasoning_output_tokens`` on top.

        Returns UNPRICED when strict=True and the model is unknown.
        """
        try:
            card = self.get_rate_card(provider, model, strict=strict)
        except UnknownModelPricing:
            return PriceResult(
                microdollars=None,
                completeness=PricingCompleteness.UNPRICED,
                pricing_version=self._version,
                provenance={"reason": "unknown_model", "provider": provider, "model": model},
            )

        # Explicit-per-bucket accounting. None → 0 for arithmetic; the
        # provenance dict below preserves the None vs 0 distinction for
        # downstream telemetry.
        uncached = int(uncached_input_tokens or 0)
        out_tok = int(output_tokens or 0)
        cache_r = int(cache_read_tokens or 0)

        # Reviewer #3 (#2221 review at bbcb5388): honor per-tier
        # cache-write rates when the caller passes a tier breakdown AND
        # the rate card declares tier-specific rates. Unknown tiers
        # under strict mode → PricingCompleteness.INCOMPLETE (never
        # silently priced at the default rate). Legacy path keeps the
        # summed × single rate behavior.
        tier_completeness_penalty = False
        cache_w_cost = Decimal(0)
        cache_w_total = 0
        cache_w_provenance: dict[str, Any] = {}
        if cache_write_tokens_by_tier and card.cache_write_by_tier_per_1m_usd:
            for tier, tokens in cache_write_tokens_by_tier.items():
                tokens_int = int(tokens or 0)
                cache_w_total += tokens_int
                if tokens_int <= 0:
                    continue
                tier_rate = card.cache_write_by_tier_per_1m_usd.get(tier)
                if tier_rate is None:
                    if strict:
                        tier_completeness_penalty = True
                        cache_w_provenance[f"tier_{tier}_unpriced"] = tokens_int
                        continue
                    # Non-strict: fall back to single-tier rate but still
                    # mark provenance so callers can see it happened.
                    tier_rate = card.cache_write_per_1m_usd
                    cache_w_provenance[f"tier_{tier}_fallback"] = tokens_int
                cache_w_cost += Decimal(tokens_int) * tier_rate
        else:
            cache_w_total = int(cache_write_tokens or 0)
            cache_w_cost = Decimal(cache_w_total) * card.cache_write_per_1m_usd

        token_cost = (
            (Decimal(uncached) * card.input_per_1m_usd)
            + (Decimal(cache_r) * card.cache_read_per_1m_usd)
            + cache_w_cost
            + (Decimal(out_tok) * card.output_per_1m_usd)
        ) / _DEC_1M

        fee = card.request_fee_usd if request_fee else Decimal(0)
        total_usd = token_cost + fee

        if uncached == 0 and out_tok == 0 and cache_r == 0 and cache_w_total == 0 and fee == 0:
            # Nothing to charge, nothing to record. Preserves
            # ``_compute_cost`` returning None for empty calls.
            return PriceResult(
                microdollars=None,
                completeness=card.completeness,
                pricing_version=card.version,
                provenance={"reason": "no_billable_tokens"},
            )

        microdollars = int((total_usd * MICRODOLLARS_PER_USD).to_integral_value())
        # If any tier was unpriced under strict mode, downgrade the
        # completeness on the result — the cost figure is a lower bound.
        final_completeness = (
            PricingCompleteness.INCOMPLETE
            if tier_completeness_penalty
            else card.completeness
        )
        provenance = {
            "uncached_input_tokens": uncached,
            "cache_read_tokens": cache_r,
            "cache_write_tokens": cache_w_total,
            "output_tokens": out_tok,
            "request_fee_applied": bool(request_fee and fee),
        }
        if cache_w_provenance:
            provenance["cache_write_tiers"] = cache_w_provenance
        return PriceResult(
            microdollars=microdollars,
            completeness=final_completeness,
            pricing_version=card.version,
            provenance=provenance,
        )


_default_service: Optional[PricingService] = None


def default_pricing_service() -> PricingService:
    """Lazy module-level instance. Session 4 wires per-workspace overrides."""
    global _default_service
    if _default_service is None:
        _default_service = PricingService()
    return _default_service


def reset_default_pricing_service() -> None:
    """For tests + snapshot reloads."""
    global _default_service
    _default_service = None
