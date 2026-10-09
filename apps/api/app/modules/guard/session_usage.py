"""Client-reported usage estimates, deliberately outside the billing ledger."""
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.runtime.accounting.pricing import default_pricing_service
from app.runtime.provider_inference import infer_provider_from_model

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


SESSION_USAGE_TOOL_CALL = "session_usage"


def _unpriced(reason: str, notes: dict) -> dict:
    return {"estimate": None, "reason": reason, "notes": notes}


def _price_slice(pricing, part: dict) -> dict:
    """Price one slice: estimate (or unpriced reason), evidence notes, pricing version."""
    provider = part.get("provider") or infer_provider_from_model(part.get("model"))
    if not part.get("model") or not provider:
        return _unpriced("missing_model_or_provider", {})
    notes = {} if part.get("provider") else {"provider_inferred": provider}
    # Missing cache rates and cache-write durations cannot be priced as zero.
    rates, version = pricing.rates_for(provider, part["model"])
    if not rates:
        return _unpriced("unknown_model", notes)
    if "+litellm-" in version:
        notes["pricing_source"] = "litellm"
    write = part.get("cache_write_tokens") or 0
    by_tier = {}
    if write:
        # Clients do not report the cache TTL; assume the 5-minute tier and say so.
        if "ephemeral_5m" in (rates.get("cache_write_by_tier") or {}):
            by_tier = {"cache_write_tokens_by_tier": {"ephemeral_5m": write}}
        elif "cache_write" not in rates:
            return _unpriced("cache_write_tier_unavailable", notes)
        notes["cache_write_tier_assumed"] = "5m"
    if part.get("cache_read_tokens") and "cache_read" not in rates:
        return _unpriced("cache_read_rate_unavailable", notes)
    if rates.get("request_fee_usd"):
        return _unpriced("request_count_unavailable", notes)
    result = pricing.price_tokens(
        provider, part["model"], uncached_input_tokens=part["uncached_input_tokens"],
        cache_read_tokens=part["cache_read_tokens"], cache_write_tokens=0 if by_tier else write,
        output_tokens=part["output_tokens"], request_fee=False, strict=True, **by_tier,
    )
    return {"estimate": result.microdollars, "version": version, "notes": notes,
            "reason": None if result.microdollars is not None else "unpriced"}


def build_evidence(parts: list[dict], observed_at: str, coverage=None) -> dict:
    """Price reported slices; Gateway-covered slices keep tokens but add no cost.

    Shared by ingest and the one-shot backfill so both apply identical math.
    """
    pricing = default_pricing_service()
    slices, versions = [], set()
    for raw in parts:
        part = {k: raw.get(k) for k in UsageSlice.model_fields}
        priced = _price_slice(pricing, part)
        versions.add(priced.get("version", pricing.pricing_version))
        estimate = priced["estimate"]
        entry = {**part, **priced["notes"], "estimated_microdollars": estimate,
                 "cost_status": "estimated" if estimate is not None else "unpriced",
                 "unpriced_reason": priced["reason"]}
        covered = coverage.classify(part) if coverage else None
        if covered:
            entry.update(coverage_rule=covered[0], covered_by=covered[1], gateway_priced_microdollars=estimate,
                         estimated_microdollars=0, cost_status="covered_by_gateway", unpriced_reason=None)
        slices.append(entry)
    counted = [p for p in slices if "covered_by" not in p]
    known = [p["estimated_microdollars"] for p in counted if p["estimated_microdollars"] is not None]
    if slices and not counted:
        status, total = "estimated", 0
    else:
        status = "estimated" if counted and len(known) == len(counted) else "partial" if known else "unpriced"
        total = sum(known) if known else None
    version = next((v for v in sorted(versions) if "+litellm-" in v), pricing.pricing_version)
    return {
        "version": 1, "source": "client_reported", "observed_at": observed_at,
        "reconciliation": "unreconciled", "budget_eligible": False,
        "pricing_version": version, "cost_status": status, "estimated_microdollars": total,
        "slices": slices,
    }


def usage_evidence(report, coverage=None) -> dict:
    """No client-supplied costs, approval states, or billing claims are accepted."""
    return build_evidence([p.model_dump(mode="json") for p in report.usage or []],
                          report.observed_at.isoformat(), coverage)


def evidence_cost_usd(evidence: dict) -> float | None:
    """Audit-row cost: uncovered estimate in USD, 0 when the Gateway covers it all, NULL if unpriced."""
    micros = evidence.get("estimated_microdollars")
    return None if evidence.get("cost_status") == "unpriced" or micros is None else micros / 1_000_000
