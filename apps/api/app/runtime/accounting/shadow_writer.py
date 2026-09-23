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


def _to_uuid_or_none(value: Any) -> Optional[uuid.UUID]:
    """Coerce a str/UUID/None to a UUID, returning None on any failure.

    Reviewer finding #1 (#2221): callers pass Clerk IDs, emails, and
    ``"system:lens"`` sentinel strings into UUID columns. Silent DBAPI
    errors previously dropped the whole receipt. Parse defensively.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


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
    developer_external_id: Optional[str] = None,
    developer_user_id: Optional[uuid.UUID | str] = None,
    agent_identity_id: Optional[uuid.UUID | str] = None,
    workflow_run_id: Optional[uuid.UUID | str] = None,
    workflow_step_id: Optional[uuid.UUID | str] = None,
    hook_session_id: Optional[uuid.UUID | str] = None,
    source: Optional[str] = None,
    client_tool: Optional[str] = None,
    transport: Optional[str] = None,
    model_alias: Optional[str] = None,
    attempts_meta: Optional[list[dict]] = None,
    started_at: Optional[datetime] = None,
    attempt_ordinal: int = 0,
    parent_receipt_id: Optional[uuid.UUID] = None,
    receipt_id: Optional[uuid.UUID] = None,
    execution_outcome: Optional[str] = None,
    succeeded: Optional[bool] = None,
    pinned_shadow_enabled: Optional[bool] = None,
    pinned_contract_version: Optional[int] = None,
) -> Optional[uuid.UUID]:
    """Persist one shadow receipt for a gateway attempt.

    Returns the receipt_id when written, None when disabled or on any error.
    Never raises.
    """
    # Session 6D: accounting-version pin. Handlers snapshot the
    # shadow-enabled decision at request entry so a mid-flight flag flip
    # cannot re-attribute an in-progress attempt to the new engine. If
    # the caller pinned False, we drop the write; if pinned True, we
    # skip the settings re-check. Absent pin → fall through to the
    # Session 6 per-workspace canary check.
    if pinned_shadow_enabled is False:
        return None
    if pinned_shadow_enabled is None:
        _check = getattr(settings, "accounting_shadow_enabled_for", None)
        if _check is not None:
            try:
                if not _check(str(workspace_id)):
                    return None
            except Exception:
                return None
        elif not getattr(settings, "guard_accounting_shadow_enabled", False):
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
            developer_external_id=developer_external_id,
            developer_user_id=developer_user_id,
            agent_identity_id=agent_identity_id,
            workflow_run_id=workflow_run_id,
            workflow_step_id=workflow_step_id,
            hook_session_id=hook_session_id,
            source=source,
            client_tool=client_tool,
            transport=transport,
            model_alias=model_alias,
            execution_outcome=execution_outcome,
            succeeded=succeeded,
            pinned_contract_version=pinned_contract_version,
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

    # Fixes from #2221 review:
    #  - #7: strict=True so unknown models surface as UNPRICED (not silently
    #    substituted). Legacy comparison stays clean.
    #  - #8: usage completeness derived from normalizer output only.
    #    Execution outcome is a separate concept and comes from the caller
    #    (dispatched + succeeded flags) — a failed call can still have
    #    partial usage, and a successful call can have missing usage.
    if not dispatched:
        normalized_tokens = None
        usage_origin = UsageOrigin.MISSING
        usage_completeness = UsageCompleteness.UNAVAILABLE
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
    else:
        normalized_tokens = None
        usage_origin = UsageOrigin.MISSING
        usage_completeness = UsageCompleteness.UNAVAILABLE
        normalizer_version = NORMALIZER_VERSION
        provenance = {"reason": "no_response_bytes"}

    # Execution outcome: caller wins. If not provided, infer conservatively.
    if kw.get("execution_outcome"):
        outcome_val = str(kw["execution_outcome"])
    else:
        if not dispatched:
            outcome_val = ExecutionOutcome.REJECTED_PREFLIGHT.value
        else:
            succeeded = kw.get("succeeded")
            if succeeded is True:
                outcome_val = ExecutionOutcome.SUCCEEDED.value
            elif succeeded is False:
                outcome_val = ExecutionOutcome.FAILED.value
            elif usage_completeness is UsageCompleteness.PARTIAL:
                outcome_val = ExecutionOutcome.DISCONNECTED.value
            elif usage_completeness is UsageCompleteness.UNAVAILABLE:
                outcome_val = ExecutionOutcome.FAILED.value
            else:
                outcome_val = ExecutionOutcome.SUCCEEDED.value

    # Price via new engine.
    # Reviewer #7 (#2221): strict=True so unknown models are UNPRICED, not
    # silently substituted. Preserves the honesty of the shadow-vs-legacy
    # comparison.
    priced_microdollars = None
    pricing_version = None
    pricing_completeness_val = PricingCompleteness.UNPRICED.value
    if normalized_tokens is not None:
        # Reviewer #4 (#2221): explicit-per-bucket, no subtraction.
        _cache_write_total = (
            sum(normalized_tokens.cache_write_tokens_by_tier.values())
            if normalized_tokens.cache_write_tokens_by_tier
            else 0
        )
        price = default_pricing_service().price_tokens(
            provider,
            model,
            uncached_input_tokens=normalized_tokens.uncached_input_tokens,
            output_tokens=normalized_tokens.total_output_tokens,
            cache_read_tokens=normalized_tokens.cache_read_tokens,
            cache_write_tokens=_cache_write_total,
            strict=True,
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

    # Reviewer #1 (#2221): developer_user_id is a UUID column. Clerk IDs /
    # emails / "system:*" are NOT UUIDs and would previously cause the
    # write to silently drop. Convert to UUID when possible; otherwise
    # fall back to developer_external_id (Text). Accept a caller-supplied
    # developer_external_id override.
    dev_user_uuid = _to_uuid_or_none(kw.get("developer_user_id"))
    dev_external_id = kw.get("developer_external_id")
    if dev_external_id is None and dev_user_uuid is None and kw.get("developer_user_id"):
        dev_external_id = str(kw["developer_user_id"])

    row = LlmAttemptReceipt(
        id=receipt_id,
        workspace_id=kw["workspace_id"],
        request_id=kw["request_id"],
        attempt_ordinal=int(kw.get("attempt_ordinal") or 0),
        parent_receipt_id=kw.get("parent_receipt_id"),
        contract_version=(
            kw.get("pinned_contract_version") or CONTRACT_VERSION
        ),
        developer_user_id=dev_user_uuid,
        developer_external_id=dev_external_id,
        agent_identity_id=_to_uuid_or_none(kw.get("agent_identity_id")),
        workflow_run_id=_to_uuid_or_none(kw.get("workflow_run_id")),
        workflow_step_id=_to_uuid_or_none(kw.get("workflow_step_id")),
        hook_session_id=_to_uuid_or_none(kw.get("hook_session_id")),
        source=kw.get("source"),
        client_tool=kw.get("client_tool"),
        transport=kw.get("transport"),
        provider=provider,
        model=model,
        model_alias=kw.get("model_alias"),
        operation=operation,
        execution_outcome=outcome_val,
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
        # #2209 Session 6F reviewer #4 (#2221 review at 1219d734):
        # placeholder promotion. If a reconciler-sourced placeholder
        # already exists at (request_id, attempt_ordinal), delete it in
        # the same transaction so the real receipt can take its slot.
        # Skip when we ARE the reconciler (a second reconciler pass
        # should be a no-op via the unique constraint, not a cascade).
        if kw.get("source") != "reconciler":
            try:
                from sqlalchemy import text as _sa_text
                db.execute(
                    _sa_text(
                        "DELETE FROM llm_attempt_receipts "
                        "WHERE request_id = :rid "
                        "AND attempt_ordinal = :ord "
                        "AND source = 'reconciler'"
                    ),
                    {
                        "rid": kw["request_id"],
                        "ord": int(kw.get("attempt_ordinal") or 0),
                    },
                )
            except Exception:
                # If the promotion delete fails, fall through — the
                # INSERT will just collide on the unique constraint and
                # the outer wrapper will swallow the IntegrityError. We
                # never want promotion to fail the request path.
                pass
        db.add(row)
        db.commit()
    finally:
        db.close()

    return receipt_id


def write_receipts_for_attempts(
    *,
    workspace_id,
    request_id,
    provider: str,
    model: str,
    operation: str,
    dispatched: bool,
    response_bytes: Optional[bytes],
    legacy_input_tokens: Optional[int],
    legacy_output_tokens: Optional[int],
    legacy_cost_usd: Optional[float],
    reserved_microdollars: Optional[int] = None,
    developer_external_id: Optional[str] = None,
    developer_user_id=None,
    agent_identity_id=None,
    workflow_run_id=None,
    workflow_step_id=None,
    hook_session_id=None,
    source: Optional[str] = None,
    client_tool: Optional[str] = None,
    transport: Optional[str] = None,
    attempts_meta: Optional[list[dict]] = None,
    pinned_shadow_enabled: Optional[bool] = None,
    pinned_contract_version: Optional[int] = None,
) -> list[uuid.UUID]:
    """Reviewer #3 (#2221): write one receipt per actual upstream attempt.

    ``attempts_meta`` is the ``routing_meta["attempts"]`` list from the
    coordinator (target_id, transport, provider_or_integration, succeeded,
    error_class). If absent, writes a single receipt at ``attempt_ordinal=0``
    matching the pre-Session-6c behavior (legacy v1 path with no coordinator).

    Failed attempts before the winner write receipts with
    ``response_bytes=None`` and ``execution_outcome=FAILED``; they are
    attributed but not priced (invariant #7). Per-attempt usage capture at
    each dispatch boundary lands in Session 6D — this helper is scaffolding
    that ingests whatever the coordinator gives us today.
    """
    receipts: list[uuid.UUID] = []
    attempts = attempts_meta or []

    # NOTE: ``model`` deliberately excluded from ``common`` — reviewer #3
    # (#2221 review at 1219d734) called out that every attempt received
    # the same request-level model, mispricing mixed-target profiles.
    # The per-attempt branch below reads ``attempt.get("model")`` first.
    common = dict(
        workspace_id=workspace_id,
        request_id=request_id,
        operation=operation,
        dispatched=dispatched,
        reserved_microdollars=reserved_microdollars,
        developer_external_id=developer_external_id,
        developer_user_id=developer_user_id,
        agent_identity_id=agent_identity_id,
        workflow_run_id=workflow_run_id,
        workflow_step_id=workflow_step_id,
        hook_session_id=hook_session_id,
        source=source,
        client_tool=client_tool,
        pinned_shadow_enabled=pinned_shadow_enabled,
        pinned_contract_version=pinned_contract_version,
    )

    if not attempts:
        rid = shadow_write(
            **common,
            provider=provider,
            model=model,
            transport=transport,
            response_bytes=response_bytes,
            legacy_input_tokens=legacy_input_tokens,
            legacy_output_tokens=legacy_output_tokens,
            legacy_cost_usd=legacy_cost_usd,
            attempt_ordinal=0,
        )
        if rid is not None:
            receipts.append(rid)
        return receipts

    parent: Optional[uuid.UUID] = None
    for idx, attempt in enumerate(attempts):
        succeeded = bool(attempt.get("succeeded"))
        attempt_provider = attempt.get("provider_or_integration") or provider
        # Reviewer #3 (#2221 review at 1219d734): per-attempt model.
        # Falls back to request-level ``model`` only if the coordinator
        # didn't record one for this attempt (legacy pre-Session-6F path).
        attempt_model = attempt.get("model") or model
        attempt_transport = attempt.get("transport") or transport
        outcome = (
            ExecutionOutcome.SUCCEEDED.value
            if succeeded
            else ExecutionOutcome.FAILED.value
        )
        # #2209 Session 6D: for failed attempts, the coordinator captured
        # the provider response body (base64) so we can normalize + price
        # it. Decode when present; fall back to the winner-only response_bytes
        # for the successful attempt.
        attempt_bytes: Optional[bytes] = None
        if succeeded:
            attempt_bytes = response_bytes
        else:
            b64 = attempt.get("response_bytes_b64")
            if b64:
                try:
                    import base64 as _b64
                    attempt_bytes = _b64.b64decode(b64)
                except Exception:
                    attempt_bytes = None
        rid = shadow_write(
            **common,
            provider=attempt_provider,
            model=attempt_model,
            transport=attempt_transport,
            response_bytes=attempt_bytes,
            legacy_input_tokens=legacy_input_tokens if succeeded else None,
            legacy_output_tokens=legacy_output_tokens if succeeded else None,
            legacy_cost_usd=legacy_cost_usd if succeeded else None,
            attempts_meta=[
                # Drop the base64 payload from the stored provenance —
                # it's already been normalized into the row's own columns.
                {k: v for k, v in attempt.items() if k != "response_bytes_b64"}
            ],
            attempt_ordinal=idx,
            parent_receipt_id=parent,
            execution_outcome=outcome,
            succeeded=succeeded,
        )
        if rid is not None:
            receipts.append(rid)
            if parent is None:
                parent = rid
    return receipts
