"""Client-reported usage estimates, deliberately outside the billing ledger."""
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.runtime.accounting.pricing import default_pricing_service

Count = Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)]
Identifier = Annotated[str, Field(max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")]


class UsageSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Identifier | None = None
    provider: Identifier | None = None
    gateway_request_id: UUID | None = None
    provider_response_id: Annotated[str, Field(max_length=160, pattern=r"^(?:msg[_-]|resp[_-]|chatcmpl-)[A-Za-z0-9_-]+$")] | None = None
    uncached_input_tokens: Count
    cache_read_tokens: Count
    cache_write_tokens: Count
    output_tokens: Count
    reasoning_output_tokens: Count | None = None

    @model_validator(mode="after")
    def reasoning_is_included(self):
        if self.reasoning_output_tokens is not None and self.reasoning_output_tokens > self.output_tokens:
            raise ValueError("reasoning tokens must be included in output tokens")
        return self

    @property
    def input_tokens(self):
        return self.uncached_input_tokens + self.cache_read_tokens + self.cache_write_tokens


def usage_evidence(report) -> dict:
    """No client-supplied costs, approval states, or billing claims are accepted."""
    pricing = default_pricing_service()
    slices = []
    for part in report.usage or []:
        estimate = None
        status = "unpriced"
        reason = "missing_model_or_provider"
        if part.model and part.provider:
            # Missing cache rates and cache-write durations cannot be priced as zero.
            rates = pricing.snapshot.get("providers", {}).get(part.provider, {}).get(part.model)
            if not rates:
                reason = "unknown_model"
            elif part.cache_write_tokens:
                reason = "cache_write_tier_unavailable"
            elif part.cache_read_tokens and "cache_read" not in rates:
                reason = "cache_read_rate_unavailable"
            elif rates.get("request_fee_usd"):
                reason = "request_count_unavailable"
            else:
                result = pricing.price_tokens(
                    part.provider, part.model, uncached_input_tokens=part.uncached_input_tokens,
                    cache_read_tokens=part.cache_read_tokens, cache_write_tokens=0,
                    output_tokens=part.output_tokens, request_fee=False, strict=True,
                )
                estimate = result.microdollars
                if estimate is not None:
                    status, reason = "estimated", None
        slices.append({**part.model_dump(mode="json"), "estimated_microdollars": estimate,
                       "cost_status": status, "unpriced_reason": reason})
    complete = bool(slices) and all(p["cost_status"] == "estimated" for p in slices)
    known = [p["estimated_microdollars"] for p in slices if p["estimated_microdollars"] is not None]
    return {
        "version": 1, "source": "client_reported", "observed_at": report.observed_at.isoformat(),
        "reconciliation": "unreconciled", "budget_eligible": False,
        "pricing_version": pricing.pricing_version,
        "cost_status": "estimated" if complete else "partial" if known else "unpriced",
        "estimated_microdollars": sum(known) if known else None,
        "slices": slices,
    }
