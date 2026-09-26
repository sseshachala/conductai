"""Receipt-only request evidence; no audit-cost fallback or repricing."""
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.contracts import CONTRACT_VERSION


@dataclass(frozen=True)
class RecordedTotal:
    # A partial value is a recorded subtotal, not a complete bill.
    value: int | None
    status: Literal["complete", "partial", "unavailable"]


@dataclass(frozen=True)
class AttemptEvidence:
    id: UUID
    request_id: UUID
    attempt_ordinal: int
    provider: str
    model: str
    contract_version: int
    pricing_version: str | None
    normalizer_version: str | None
    currency: str
    usage_origin: str
    usage_completeness: str
    pricing_completeness: str
    execution_outcome: str
    total_input_tokens: int | None
    total_output_tokens: int | None
    cache_read_tokens: int | None
    reasoning_output_tokens: int | None
    calculated_cost_microdollars: int | None


@dataclass(frozen=True)
class UsageTotals:
    input_tokens: RecordedTotal
    output_tokens: RecordedTotal
    calculated_cost_microdollars: RecordedTotal
    currency: Literal["USD"] = "USD"
    receipt_count: int = 0
    request_count: int = 0
    missing_request_count: int = 0
    usage_completeness: dict[str, int] = field(default_factory=dict)
    pricing_completeness: dict[str, int] = field(default_factory=dict)
    usage_origins: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RequestUsage:
    request_id: UUID
    attempts: list[AttemptEvidence]
    expected_attempt_count: int | None
    missing_attempt_count: int
    coverage_complete: bool
    totals: UsageTotals


@dataclass(frozen=True)
class RequestUsageBatch:
    requests: dict[UUID, RequestUsage]
    totals: UsageTotals


def _totals(attempts, *, request_count, missing_requests, coverage_complete):
    def measured(column, *, money=False):
        values = []
        complete = bool(attempts) and coverage_complete
        for attempt in attempts:
            value = getattr(attempt, column)
            supported = attempt.contract_version == CONTRACT_VERSION
            known = supported and value is not None and value >= 0
            settled = (
                attempt.usage_completeness == "complete"
                and attempt.pricing_completeness in ("priced", "override_applied")
                and attempt.currency == "USD"
            )
            usable = known and (not money or settled)
            if usable:
                values.append(value)
            complete = complete and usable and attempt.usage_completeness == "complete"
        return RecordedTotal(
            sum(values) if values else None,
            "complete" if complete else "partial" if values else "unavailable",
        )
    return UsageTotals(
        input_tokens=measured("total_input_tokens"),
        output_tokens=measured("total_output_tokens"),
        calculated_cost_microdollars=measured("calculated_cost_microdollars", money=True),
        receipt_count=len(attempts), request_count=request_count,
        missing_request_count=missing_requests,
        usage_completeness=dict(Counter(a.usage_completeness for a in attempts)),
        pricing_completeness=dict(Counter(a.pricing_completeness for a in attempts)),
        usage_origins=dict(Counter(a.usage_origin for a in attempts)),
    )


def read_request_evidence(db, *, workspace_id: UUID, requests: dict[UUID, UUID]):
    """Caller must authorize each request/identity pair before invoking.

    Bounded batch, one receipt query, and one audit coverage query. Joins are
    deliberately avoided: workflow links and audit rows cannot multiply costs.
    Unknown or unfinished attempt coverage prevents an exact-total claim.
    """
    from app.modules.guard.models import GuardAuditEvent
    from app.runtime.accounting.reconciler import _extract_attempts_from_meta

    if len(requests) > 100:
        raise ValueError("At most 100 authorized requests may be read")
    if not requests:
        return RequestUsageBatch({}, _totals([], request_count=0, missing_requests=0, coverage_complete=False))
    model = LlmAttemptReceipt
    fields = list(AttemptEvidence.__dataclass_fields__)
    rows = db.execute(select(*(getattr(model, key) for key in fields)).where(
        model.workspace_id == workspace_id,
        tuple_(model.request_id, model.agent_identity_id).in_(list(requests.items())),
    ).order_by(model.request_id, model.attempt_ordinal)).mappings().all()
    grouped = {request_id: [] for request_id in requests}
    for row in rows:
        attempt = AttemptEvidence(**row)
        grouped[attempt.request_id].append(attempt)
    event = GuardAuditEvent
    coverage = db.execute(select(event.request_id, event.routing_meta, event.lifecycle_state).where(
        event.workspace_id == workspace_id, event.request_id.in_(requests),
    )).all()
    expected = {}
    for row in coverage:
        count, _ = _extract_attempts_from_meta(row.routing_meta)
        expected[row.request_id] = (count or None, row.lifecycle_state)
    results = {}
    for request_id, attempts in grouped.items():
        count, lifecycle = expected.get(request_id, (None, None))
        ordinals = {a.attempt_ordinal for a in attempts}
        missing = len(set(range(count)) - ordinals) if count is not None else 0
        complete = (
            count is not None and ordinals == set(range(count))
            and lifecycle == "finalized"
        )
        results[request_id] = RequestUsage(
            request_id=request_id, attempts=attempts, expected_attempt_count=count,
            missing_attempt_count=missing, coverage_complete=complete,
            totals=_totals(attempts, request_count=1, missing_requests=int(not attempts), coverage_complete=complete),
        )
    totals = _totals(
        [a for value in results.values() for a in value.attempts],
        request_count=len(requests), missing_requests=sum(not v.attempts for v in results.values()),
        coverage_complete=all(v.coverage_complete for v in results.values()),
    )
    return RequestUsageBatch(results, totals)
