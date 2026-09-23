"""Accounting → Lens read API (#2209 Session 5).

This module is the CONTRACT the Lens conversational surface consumes. All
usage / cost / attribution numbers Lens surfaces to a user must come from
here — Lens's LLM never invents math and never runs its own aggregation.

Separation of concerns (per Sudhi 2026-09-23):

- **Accounting** (this module) — trustworthy usage, cost, attribution +
  queryable aggregates. Distinguishes reported vs estimated vs incomplete.
- **Lens** (separate epic) — turns evidence into conversational answers
  such as "which developer drove yesterday's spend increase?" or "how much
  did caching save?". Delegates every number to this API.
- **Flight Recorder (#2069)** — provides evidence links (requests,
  attempts, policy decisions) that Lens can hyperlink to.

Invariants surfaced through the aggregate shape:

1. Known-zero, missing, partial and pending remain distinguishable
   (invariant #4). Aggregates report counts by ``UsageCompleteness``.
2. Unpriced attempts (unknown model, strict pricing rejection) surface
   through ``pricing_completeness_breakdown`` — never silently folded into
   the priced total (invariant #9).
3. Reasoning tokens are a subset of output_tokens, not additive
   (invariant #5). ``reasoning_output_tokens`` is available but does NOT
   add to ``total_cost_microdollars``.
4. Cache savings are computed from the ledger, not the LLM: cache reads
   priced at the cache-read rate vs. the uncached-input rate.

Session 5 ships the shape + one minimal implementation
(``summarize_by_scope``). Session 6 metrics + a future Lens epic add more
query methods. Everything is versioned via ``contract_version`` on the
underlying rows so historical answers remain interpretable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.contracts import (
    MICRODOLLARS_PER_USD,
    PricingCompleteness,
    UsageCompleteness,
)


class AggregateScope(str, Enum):
    """How to group the aggregate query."""

    WORKSPACE = "workspace"
    DEVELOPER = "developer_user_id"
    AGENT_IDENTITY = "agent_identity_id"
    MODEL = "model"
    PROVIDER = "provider"
    CLIENT_TOOL = "client_tool"
    WORKFLOW_RUN = "workflow_run_id"
    HOOK_SESSION = "hook_session_id"


@dataclass(frozen=True)
class SpendAggregate:
    """One aggregated slice of accounting evidence.

    Every field is a fact derived from ``llm_attempt_receipts`` rows.
    Callers (Lens, dashboards, exports) MUST preserve the completeness
    breakdown when displaying numbers so users can tell "$5.00 reported"
    apart from "$5.00 partially reported, actual may be higher".
    """

    scope: Mapping[str, Optional[str]]
    period_start: datetime
    period_end: datetime

    # Row counts
    receipt_count: int
    request_count: int  # distinct request_ids

    # Money (integer microdollars, per contract)
    total_cost_microdollars: int
    total_reserved_microdollars: int

    # Legacy comparison (Session 6 metrics)
    legacy_cost_microdollars: int

    # Token totals — nullable? No, aggregate treats NULL as 0 for sums.
    # The distinction lives in `completeness_breakdown` below.
    total_input_tokens: int
    total_output_tokens: int
    total_uncached_input_tokens: int
    total_cache_read_tokens: int
    total_reasoning_output_tokens: int

    # Provenance breakdowns
    completeness_breakdown: Mapping[str, int] = field(default_factory=dict)
    pricing_completeness_breakdown: Mapping[str, int] = field(default_factory=dict)
    execution_outcome_breakdown: Mapping[str, int] = field(default_factory=dict)

    @property
    def total_cost_usd(self) -> Decimal:
        """Convenience for display. Ledger arithmetic stays in microdollars."""
        return Decimal(self.total_cost_microdollars) / Decimal(MICRODOLLARS_PER_USD)

    @property
    def has_partial_or_missing(self) -> bool:
        """True if any receipts in this aggregate have incomplete usage.

        Lens should surface a caveat next to any number derived from an
        aggregate where this is True.
        """
        return any(
            key != UsageCompleteness.COMPLETE.value and count > 0
            for key, count in self.completeness_breakdown.items()
        )

    @property
    def has_unpriced_attempts(self) -> bool:
        """True if any attempts could not be priced (unknown model, strict
        rejection). Lens must NOT report ``total_cost_microdollars`` as the
        exact spend when this is True; the true cost is at least the
        reported figure."""
        unpriced = self.pricing_completeness_breakdown.get(
            PricingCompleteness.UNPRICED.value, 0
        )
        return unpriced > 0


@dataclass(frozen=True)
class CacheSavings:
    """Cache-savings derivation for one aggregate.

    The Lens epic asks 'how much did caching save?'. That answer is a
    counterfactual (what would have been paid without cache), so it
    depends on both the receipt totals AND the rate card the receipts
    were priced under. This helper does the math so Lens's LLM never
    invents it.
    """

    cache_read_tokens: int
    uncached_input_tokens: int
    cache_write_tokens: int
    # (uncached_rate - cache_read_rate) × cache_read_tokens, in microdollars.
    savings_microdollars: int
    # If cache_read was priced at uncached_rate, this is what it would have cost.
    counterfactual_cost_microdollars: int


class AccountingReader:
    """Query surface for the shared accounting engine.

    All numbers Lens surfaces come from here. Session 5 shipped
    ``summarize_by_scope``; Session 6E adds session/request drilldown and
    the cache-savings helper Lens will need most.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def summarize_by_scope(
        self,
        *,
        workspace_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        scope: AggregateScope,
    ) -> list[SpendAggregate]:
        """Aggregate accounting evidence for one workspace over a period,
        grouped by ``scope``.

        Returns one ``SpendAggregate`` per distinct scope value. Rows with a
        NULL scope value are grouped under ``scope == {scope.value: None}``.
        """
        group_col = _scope_column(scope)
        model = LlmAttemptReceipt

        rows = self._db.execute(
            select(
                group_col,
                func.count(model.id).label("receipt_count"),
                func.count(func.distinct(model.request_id)).label("request_count"),
                func.coalesce(func.sum(model.calculated_cost_microdollars), 0).label(
                    "total_cost"
                ),
                func.coalesce(func.sum(model.reserved_microdollars), 0).label(
                    "total_reserved"
                ),
                func.coalesce(func.sum(model.legacy_cost_microdollars), 0).label(
                    "legacy_cost"
                ),
                func.coalesce(func.sum(model.total_input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(model.total_output_tokens), 0).label(
                    "output_tokens"
                ),
                func.coalesce(func.sum(model.uncached_input_tokens), 0).label(
                    "uncached_input"
                ),
                func.coalesce(func.sum(model.cache_read_tokens), 0).label("cache_read"),
                func.coalesce(func.sum(model.reasoning_output_tokens), 0).label(
                    "reasoning"
                ),
            )
            .where(model.workspace_id == workspace_id)
            .where(model.finalized_at >= period_start)
            .where(model.finalized_at < period_end)
            .group_by(group_col)
        ).all()

        results: list[SpendAggregate] = []
        for row in rows:
            group_val = row[0]
            completeness = _breakdown(
                self._db,
                model.usage_completeness,
                workspace_id=workspace_id,
                period_start=period_start,
                period_end=period_end,
                group_col=group_col,
                group_val=group_val,
            )
            pricing = _breakdown(
                self._db,
                model.pricing_completeness,
                workspace_id=workspace_id,
                period_start=period_start,
                period_end=period_end,
                group_col=group_col,
                group_val=group_val,
            )
            outcome = _breakdown(
                self._db,
                model.execution_outcome,
                workspace_id=workspace_id,
                period_start=period_start,
                period_end=period_end,
                group_col=group_col,
                group_val=group_val,
            )
            results.append(
                SpendAggregate(
                    scope={scope.value: str(group_val) if group_val is not None else None},
                    period_start=period_start,
                    period_end=period_end,
                    receipt_count=int(row.receipt_count),
                    request_count=int(row.request_count),
                    total_cost_microdollars=int(row.total_cost),
                    total_reserved_microdollars=int(row.total_reserved),
                    legacy_cost_microdollars=int(row.legacy_cost),
                    total_input_tokens=int(row.input_tokens),
                    total_output_tokens=int(row.output_tokens),
                    total_uncached_input_tokens=int(row.uncached_input),
                    total_cache_read_tokens=int(row.cache_read),
                    total_reasoning_output_tokens=int(row.reasoning),
                    completeness_breakdown=completeness,
                    pricing_completeness_breakdown=pricing,
                    execution_outcome_breakdown=outcome,
                )
            )
        return results

    def receipts_for_session(
        self,
        *,
        workspace_id: uuid.UUID,
        hook_session_id: uuid.UUID,
        limit: int = 500,
    ) -> list[LlmAttemptReceipt]:
        """Return every receipt for one Lens session, most recent first.

        Session 6E — Lens's session-drilldown UI consumes this to answer
        "what did this conversation cost, and where did the tokens go?".
        Lens must render `usage_completeness` + `pricing_completeness` on
        every row; the aggregate helper collapses those into flags.
        """
        m = LlmAttemptReceipt
        return list(
            self._db.execute(
                select(m)
                .where(m.workspace_id == workspace_id)
                .where(m.hook_session_id == hook_session_id)
                .order_by(m.finalized_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def receipts_for_request(
        self,
        *,
        workspace_id: uuid.UUID,
        request_id: uuid.UUID,
    ) -> list[LlmAttemptReceipt]:
        """Return every attempt receipt for one Gateway request, in order.

        Session 6E — Lens's per-request drilldown ("why did this attempt
        get 429'd, then succeed on the fallback?"). Ordered by
        ``attempt_ordinal`` so failed attempts appear before the winner.
        """
        m = LlmAttemptReceipt
        return list(
            self._db.execute(
                select(m)
                .where(m.workspace_id == workspace_id)
                .where(m.request_id == request_id)
                .order_by(m.attempt_ordinal.asc())
            )
            .scalars()
            .all()
        )


def compute_cache_savings(
    aggregate: SpendAggregate,
    *,
    uncached_rate_per_1m_usd: Decimal,
    cache_read_rate_per_1m_usd: Decimal,
    cache_write_rate_per_1m_usd: Decimal = Decimal(0),
) -> CacheSavings:
    """Compute how much caching saved for one aggregate slice.

    Session 6E — Lens must not invent this arithmetic. Formula:

        savings = (uncached_rate - cache_read_rate) × cache_read_tokens

    ``counterfactual_cost`` is what the input side would have cost if
    every cache read had been billed at the uncached rate. Comparing
    that against ``aggregate.total_cost_microdollars`` gives Lens the
    "you saved $X" answer honestly.

    Rates are per-1M tokens as ``Decimal``, matching ``RateCard``.
    Callers pass them in explicitly so Lens's UI can also render the
    pricing version + snapshot that produced the number.
    """
    delta_per_1m = uncached_rate_per_1m_usd - cache_read_rate_per_1m_usd
    savings_usd = (
        Decimal(aggregate.total_cache_read_tokens) * delta_per_1m
    ) / Decimal(1_000_000)
    counterfactual_input_usd = (
        Decimal(aggregate.total_cache_read_tokens + aggregate.total_uncached_input_tokens)
        * uncached_rate_per_1m_usd
    ) / Decimal(1_000_000)
    savings_micros = int(
        (savings_usd * Decimal(1_000_000)).to_integral_value()
    )
    counterfactual_micros = int(
        (counterfactual_input_usd * Decimal(1_000_000)).to_integral_value()
    )
    return CacheSavings(
        cache_read_tokens=aggregate.total_cache_read_tokens,
        uncached_input_tokens=aggregate.total_uncached_input_tokens,
        cache_write_tokens=0,  # aggregate doesn't split writes by tier today
        savings_microdollars=savings_micros,
        counterfactual_cost_microdollars=counterfactual_micros,
    )


def aggregate_from_rows(
    rows: Iterable[Any],
    *,
    scope: AggregateScope,
    period_start: datetime,
    period_end: datetime,
    scope_value: Optional[str] = None,
) -> SpendAggregate:
    """Aggregate a Python-side collection of receipt-like objects into one
    ``SpendAggregate``. Useful for tests + reconciliation harnesses without
    needing a live database round-trip.

    Any object exposing the receipt column names as attributes works
    (SQLAlchemy models, dataclasses, namedtuples).
    """
    receipt_count = 0
    request_ids: set[str] = set()
    total_cost = 0
    total_reserved = 0
    legacy_cost = 0
    input_tokens = 0
    output_tokens = 0
    uncached_input = 0
    cache_read = 0
    reasoning = 0
    completeness: dict[str, int] = {}
    pricing: dict[str, int] = {}
    outcome: dict[str, int] = {}

    for r in rows:
        receipt_count += 1
        request_ids.add(str(getattr(r, "request_id", "")))
        total_cost += int(getattr(r, "calculated_cost_microdollars", 0) or 0)
        total_reserved += int(getattr(r, "reserved_microdollars", 0) or 0)
        legacy_cost += int(getattr(r, "legacy_cost_microdollars", 0) or 0)
        input_tokens += int(getattr(r, "total_input_tokens", 0) or 0)
        output_tokens += int(getattr(r, "total_output_tokens", 0) or 0)
        uncached_input += int(getattr(r, "uncached_input_tokens", 0) or 0)
        cache_read += int(getattr(r, "cache_read_tokens", 0) or 0)
        reasoning += int(getattr(r, "reasoning_output_tokens", 0) or 0)
        completeness[str(getattr(r, "usage_completeness", ""))] = (
            completeness.get(str(getattr(r, "usage_completeness", "")), 0) + 1
        )
        pricing[str(getattr(r, "pricing_completeness", ""))] = (
            pricing.get(str(getattr(r, "pricing_completeness", "")), 0) + 1
        )
        outcome[str(getattr(r, "execution_outcome", ""))] = (
            outcome.get(str(getattr(r, "execution_outcome", "")), 0) + 1
        )

    return SpendAggregate(
        scope={scope.value: scope_value},
        period_start=period_start,
        period_end=period_end,
        receipt_count=receipt_count,
        request_count=len(request_ids - {""}),
        total_cost_microdollars=total_cost,
        total_reserved_microdollars=total_reserved,
        legacy_cost_microdollars=legacy_cost,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_uncached_input_tokens=uncached_input,
        total_cache_read_tokens=cache_read,
        total_reasoning_output_tokens=reasoning,
        completeness_breakdown=completeness,
        pricing_completeness_breakdown=pricing,
        execution_outcome_breakdown=outcome,
    )


# ─── internal helpers ─────────────────────────────────────────────────────────


def _scope_column(scope: AggregateScope):
    m = LlmAttemptReceipt
    return {
        AggregateScope.WORKSPACE: m.workspace_id,
        AggregateScope.DEVELOPER: m.developer_user_id,
        AggregateScope.AGENT_IDENTITY: m.agent_identity_id,
        AggregateScope.MODEL: m.model,
        AggregateScope.PROVIDER: m.provider,
        AggregateScope.CLIENT_TOOL: m.client_tool,
        AggregateScope.WORKFLOW_RUN: m.workflow_run_id,
        AggregateScope.HOOK_SESSION: m.hook_session_id,
    }[scope]


def _breakdown(
    db: Session,
    col,
    *,
    workspace_id,
    period_start,
    period_end,
    group_col,
    group_val,
) -> dict[str, int]:
    """Return a dict of {col_value: count} for one scope value."""
    model = LlmAttemptReceipt
    where_scope = group_col.is_(None) if group_val is None else (group_col == group_val)
    rows = db.execute(
        select(col, func.count(model.id))
        .where(model.workspace_id == workspace_id)
        .where(model.finalized_at >= period_start)
        .where(model.finalized_at < period_end)
        .where(where_scope)
        .group_by(col)
    ).all()
    return {str(k): int(v) for k, v in rows}
