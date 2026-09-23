"""Shadow writer for LlmAttemptReceipt (#2209 Session 4).

Runs alongside the legacy settlement path. Old ``GuardAuditEvent`` remains
authoritative — this writer only PERSISTS the shadow calculation for later
comparison. Session 6 metrics quantify the delta; Session 7 activates.

Design invariants:

1. **Never fails the request.** Every exception is caught and logged. A
   corrupt shadow row is preferable to a broken settlement path.
2. **Additive only.** Legacy audit rows are untouched; shadow rows are a
   parallel append.
3. **Kill-switch.** Off by default (``settings.guard_accounting_shadow_enabled``).
   Ops flips it on per environment during Session 6 canary.
4. **Contract-versioned rows.** Each row records the writer version + the
   pricing snapshot version + the normalizer version so historical rows can
   be reinterpreted after schema evolution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.contracts import (
    CONTRACT_VERSION,
    ExecutionOutcome,
    PricingCompleteness,
    UsageCompleteness,
    UsageOrigin,
)
from app.runtime.accounting.normalizers import (
    NORMALIZER_VERSION,
    ProviderFamily,
    normalize_json,
    normalize_sse,
)
from app.runtime.accounting.pricing import default_pricing_service

log = structlog.get_logger(__name__)


_FAMILY_BY_PROVIDER: dict[str, ProviderFamily] = {
    "anthropic": ProviderFamily.ANTHROPIC_MESSAGES,
    "openai": ProviderFamily.OPENAI_CHAT,
    "perplexity": ProviderFamily.OPENAI_CHAT,  # OpenAI-shape
    "litellm": ProviderFamily.LITELLM,
}


def _family_for(provider: str, operation: str) -> ProviderFamily:
    """Pick the normalizer family. Responses API operation overrides provider."""
    if operation and "responses" in operation.lower():
        return ProviderFamily.OPENAI_RESPONSES
    return _FAMILY_BY_PROVIDER.get((provider or "").lower(), ProviderFamily.OPENAI_CHAT)


def _looks_like_sse(response_bytes: bytes) -> bool:
    """Rough heuristic — SSE always begins with an event or data line."""
    if not response_bytes:
        return False
    head = response_bytes[:64].lstrip()
    return head.startswith((b"event:", b"data:", b":"))


def shadow_write(
    *,
    workspace_id: uuid.UUID | str,
    request_id: uuid.UUID | str,
    provider: str,
    model: str,
    operation: str,
    dispatched: bool,
    response_bytes: Optional[bytes],
    legacy_input_tokens: Optional[int],
    legacy_output_tokens: Optional[int],
    legacy_cost_usd: Optional[float],
    reserved_microdollars: Optional[int] = None,
    estimated_input_tokens: Optional[int] = None,
    developer_user_id: Optional[uuid.UUID | str] = None,
    agent_identity_id: Optional[uuid.UUID | str] = None,
    source: Optional[str] = None,
    client_tool: Optional[str] = None,
    transport: Optional[str] = None,
    model_alias: Optional[str] = None,
    attempts_meta: Optional[list[dict]] = None,
    started_at: Optional[datetime] = None,
    attempt_ordinal: int = 0,
    parent_receipt_id: Optional[uuid.UUID] = None,
    receipt_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    """Persist one shadow receipt for a gateway attempt.

    Returns the receipt_id when written, None when disabled or on any error.
    Never raises.
    """
    if not getattr(settings, "guard_accounting_shadow_enabled", False):
        return None

    try:
        return _shadow_write_impl(
            workspace_id=workspace_id,
            request_id=request_id,
            provider=provider,
            model=model,
            operation=operation,
            dispatched=dispatched,
            response_bytes=response_bytes,
            legacy_input_tokens=legacy_input_tokens,
            legacy_output_tokens=legacy_output_tokens,
            legacy_cost_usd=legacy_cost_usd,
            reserved_microdollars=reserved_microdollars,
            estimated_input_tokens=estimated_input_tokens,
            developer_user_id=developer_user_id,
            agent_identity_id=agent_identity_id,
            source=source,
            client_tool=client_tool,
            transport=transport,
            model_alias=model_alias,
            attempts_meta=attempts_meta or [],
            started_at=started_at,
            attempt_ordinal=attempt_ordinal,
            parent_receipt_id=parent_receipt_id,
            receipt_id=receipt_id,
        )
    except Exception:
        log.exception(
            "accounting.shadow_writer.failed",
            request_id=str(request_id),
            provider=provider,
            model=model,
        )
        return None


def _shadow_write_impl(**kw: Any) -> uuid.UUID:
    """Non-swallowing inner impl. All exception handling lives in the wrapper."""
    provider = kw["provider"]
    model = kw["model"]
    operation = kw["operation"] or "unknown"
    dispatched = bool(kw["dispatched"])
    response_bytes = kw.get("response_bytes")

    family = _family_for(provider, operation)

    if not dispatched:
        normalized_tokens = None
        usage_origin = UsageOrigin.MISSING
        usage_completeness = UsageCompleteness.UNAVAILABLE
        execution_outcome = ExecutionOutcome.REJECTED_PREFLIGHT
        normalizer_version = NORMALIZER_VERSION
        provenance: dict[str, Any] = {"reason": "not_dispatched"}
    elif response_bytes:
        if _looks_like_sse(response_bytes):
            norm = normalize_sse(family, response_bytes)
        else:
            norm = normalize_json(family, response_bytes)
        normalized_tokens = norm.tokens
        usage_origin = norm.origin
        usage_completeness = norm.completeness
        normalizer_version = norm.normalizer_version
        provenance = {"family": family.value, "raw_usage": dict(norm.raw_usage)}
        # Outcome: PARTIAL usually means client dropped mid-stream; still
        # possibly billed by provider.
        if usage_completeness is UsageCompleteness.PARTIAL:
            execution_outcome = ExecutionOutcome.DISCONNECTED
        elif usage_completeness is UsageCompleteness.UNAVAILABLE:
            execution_outcome = ExecutionOutcome.FAILED
        else:
            execution_outcome = ExecutionOutcome.SUCCEEDED
    else:
        normalized_tokens = None
        usage_origin = UsageOrigin.MISSING
        usage_completeness = UsageCompleteness.UNAVAILABLE
        execution_outcome = ExecutionOutcome.FAILED
        normalizer_version = NORMALIZER_VERSION
        provenance = {"reason": "no_response_bytes"}

    # Price via new engine — strict=False preserves legacy silent fallback so
    # shadow rows can be compared against legacy audit rows on the same
    # attempts. Session 6 flips strict=True and measures the UNPRICED delta.
    priced_microdollars = None
    pricing_version = None
    pricing_completeness_val = PricingCompleteness.UNPRICED.value
    if normalized_tokens is not None:
        price = default_pricing_service().price_tokens(
            provider,
            model,
            input_tokens=normalized_tokens.uncached_input_tokens
            or normalized_tokens.total_input_tokens,
            output_tokens=normalized_tokens.total_output_tokens,
            cache_read_tokens=normalized_tokens.cache_read_tokens,
            cache_write_tokens=sum(normalized_tokens.cache_write_tokens_by_tier.values())
            if normalized_tokens.cache_write_tokens_by_tier
            else 0,
            strict=False,
        )
        priced_microdollars = price.microdollars
        pricing_version = price.pricing_version
        pricing_completeness_val = price.completeness.value
        provenance["pricing"] = dict(price.provenance)

    if kw.get("attempts_meta"):
        provenance["attempts"] = kw["attempts_meta"]

    legacy_cost_micros = None
    if kw.get("legacy_cost_usd") is not None:
        legacy_cost_micros = int(round(float(kw["legacy_cost_usd"]) * 1_000_000))

    receipt_id = kw.get("receipt_id") or uuid.uuid4()
    now = datetime.now(timezone.utc)

    row = LlmAttemptReceipt(
        id=receipt_id,
        workspace_id=kw["workspace_id"],
        request_id=kw["request_id"],
        attempt_ordinal=int(kw.get("attempt_ordinal") or 0),
        parent_receipt_id=kw.get("parent_receipt_id"),
        contract_version=CONTRACT_VERSION,
        developer_user_id=kw.get("developer_user_id"),
        agent_identity_id=kw.get("agent_identity_id"),
        source=kw.get("source"),
        client_tool=kw.get("client_tool"),
        transport=kw.get("transport"),
        provider=provider,
        model=model,
        model_alias=kw.get("model_alias"),
        operation=operation,
        execution_outcome=execution_outcome.value,
        total_input_tokens=normalized_tokens.total_input_tokens if normalized_tokens else None,
        total_output_tokens=normalized_tokens.total_output_tokens if normalized_tokens else None,
        uncached_input_tokens=(
            normalized_tokens.uncached_input_tokens if normalized_tokens else None
        ),
        cache_read_tokens=normalized_tokens.cache_read_tokens if normalized_tokens else None,
        cache_write_tokens_by_tier=(
            dict(normalized_tokens.cache_write_tokens_by_tier) if normalized_tokens else {}
        ),
        reasoning_output_tokens=(
            normalized_tokens.reasoning_output_tokens if normalized_tokens else None
        ),
        modality_units=(dict(normalized_tokens.modality_units) if normalized_tokens else {}),
        usage_origin=usage_origin.value,
        usage_completeness=usage_completeness.value,
        estimated_input_tokens=kw.get("estimated_input_tokens"),
        reserved_microdollars=kw.get("reserved_microdollars"),
        calculated_cost_microdollars=priced_microdollars,
        pricing_version=pricing_version,
        pricing_completeness=pricing_completeness_val,
        legacy_input_tokens=kw.get("legacy_input_tokens"),
        legacy_output_tokens=kw.get("legacy_output_tokens"),
        legacy_cost_microdollars=legacy_cost_micros,
        normalizer_version=normalizer_version,
        calculation_provenance=provenance,
        started_at=kw.get("started_at"),
        finalized_at=now,
    )

    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
    finally:
        db.close()

    return receipt_id
