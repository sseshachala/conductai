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

from sqlalchemy import case, func, select
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
class SessionSpend:
    """Per-session accounting rollup for the Lens Sessions list.

    Post-#2221 PR 1 (consumer wiring): AccountingReader
    ``spend_by_hook_session_ids()`` returns one of these per session so
    Lens's UI can render both the number AND the caveats (partial /
    unpriced) — invariants #4 and #9 preserved end-to-end.
    """

    hook_session_id: uuid.UUID
    receipt_count: int
    request_count: int
    total_cost_microdollars: int
    has_partial_or_missing: bool
    has_unpriced_attempts: bool

    @property
    def total_cost_usd(self) -> Decimal:
        return Decimal(self.total_cost_microdollars) / Decimal(1_000_000)


@dataclass(frozen=True)
class CacheReadSavings:
    """Gross cache-READ savings for one (model, pricing_version) slice.

    Reviewer #6 (#2221 review at 1219d734) narrowed the scope: the
    previous ``CacheSavings`` dataclass mixed one rate pair against an
    aggregate that could span multiple models. It also hardcoded
    ``cache_write_tokens=0`` and ignored its ``cache_write_rate``
    argument, producing an answer that looked authoritative but wasn't.

    What this IS:
      Gross cache-read savings — how much less the cache_read tokens
      cost vs. if the same bytes had been billed at the uncached input
      rate. Only meaningful for one (model, pricing_version) slice.

    What this is NOT:
      - A net "cache saved you $X" figure. Cache writes usually cost
        MORE than uncached input to pay for later reads; that premium
        is a separate arithmetic and lives in
        ``compute_cache_write_premium_for_receipt``.
      - A workspace-wide savings summary. Aggregating across models
        with different rate cards requires per-receipt calculation;
        use ``sum_cache_read_savings_over_receipts``.
    """

    cache_read_tokens: int
    uncached_input_tokens: int
    savings_microdollars: int
    counterfactual_read_cost_microdollars: int


# Kept as an alias for one release so external importers do not break.
# Session 7 removal deletes it.
CacheSavings = CacheReadSavings


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

    def spend_by_hook_session_ids(
        self,
        *,
        workspace_id: uuid.UUID,
        hook_session_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, "SessionSpend"]:
        """Batched spend rollup keyed by hook_session_id.

        Post-#2221 PR 1 (consumer wiring): replaces Lens's direct
        ``SUM(GuardAuditEvent.cost_usd_after)`` query. One aggregate per
        session, with the completeness + unpriced flags Lens must render
        alongside the number. Sessions with no receipts are absent from
        the returned dict — caller renders those as $0 with no caveat.
        """
        if not hook_session_ids:
            return {}
        m = LlmAttemptReceipt
        rows = self._db.execute(
            select(
                m.hook_session_id,
                func.count(m.id).label("receipt_count"),
                func.count(func.distinct(m.request_id)).label("request_count"),
                func.coalesce(func.sum(m.calculated_cost_microdollars), 0).label(
                    "total_cost"
                ),
                func.sum(
                    case(
                        (
                            m.usage_completeness != UsageCompleteness.COMPLETE.value,
                            1,
                        ),
                        else_=0,
                    )
                ).label("incomplete_count"),
                func.sum(
                    case(
                        (
                            m.pricing_completeness == PricingCompleteness.UNPRICED.value,
                            1,
                        ),
                        else_=0,
                    )
                ).label("unpriced_count"),
            )
            .where(m.workspace_id == workspace_id)
            .where(m.hook_session_id.in_(hook_session_ids))
            .group_by(m.hook_session_id)
        ).all()
        return {
            row.hook_session_id: SessionSpend(
                hook_session_id=row.hook_session_id,
                receipt_count=int(row.receipt_count),
                request_count=int(row.request_count),
                total_cost_microdollars=int(row.total_cost),
                has_partial_or_missing=bool(int(row.incomplete_count or 0) > 0),
                has_unpriced_attempts=bool(int(row.unpriced_count or 0) > 0),
            )
            for row in rows
            if row.hook_session_id is not None
        }

    def spend_micros_by_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        since: datetime,
        group_by_clerk: bool = False,
        ai_tool: Optional[str] = None,
        clerk_user_id: Optional[str] = None,
    ) -> dict[Optional[str], int]:
        """Workspace-scoped spend rollup post-cutover.

        Returns ``{None: total_micros}`` when ``group_by_clerk`` is False,
        or ``{clerk_user_id: micros_per_user}`` when True. Rows for users
        with no spend are absent (caller renders zero).

        Sums two sources under a SINGLE aggregate statement so both see
        the same snapshot (Postgres MVCC guarantees intra-statement
        snapshot consistency — a receipt inserted between two separate
        queries under READ COMMITTED can be absent from the receipts
        sum AND simultaneously suppress its audit row, temporarily
        losing that request's spend):

        1. ``LlmAttemptReceipt.calculated_cost_microdollars`` gated on
           ``usage_completeness='complete'`` AND ``pricing_completeness
           IN ('priced','override_applied')``. PARTIAL / UNPRICED
           receipts are NOT counted — they are not defensible numbers.
        2. ``GuardAuditEvent.cost_usd_after`` for requests with **no
           receipt at all** (post-review P1: was ``no settleable
           receipt`` which reintroduced audit cost for post-cutover
           partial-receipt requests → same request contributed the
           excluded partial receipt AND the audit row). Requests with a
           non-settleable receipt are shown as unresolved via the
           companion ``unresolved_request_count_by_workspace`` helper.

        Filters:

        - ``ai_tool`` — transport-scoped ("gateway", "mcp", "workflow",
          "runtime") filters by ``source``; anything else filters by
          ``client_tool`` on receipts and ``ai_tool`` on audit rows.
        - ``clerk_user_id`` — exact-match scope (receipts use
          ``developer_external_id``, audit uses ``clerk_user_id``).
        - ``group_by_clerk=True`` — one row per user; skips
          NULL identities (system callers, guard-mt-* tokens).
        """
        from sqlalchemy import text
        from app.core.budget_ledger import _is_transport

        # Build the ai_tool / clerk filters once for each side.
        params: dict[str, Any] = {
            "ws": str(workspace_id),
            "since": since,
        }
        receipt_where = []
        audit_where = []
        if ai_tool is not None:
            params["ai_tool"] = ai_tool
            if _is_transport(ai_tool):
                receipt_where.append("r.source = :ai_tool")
                audit_where.append("a.source = :ai_tool")
            else:
                receipt_where.append("r.client_tool = :ai_tool")
                audit_where.append("a.ai_tool = :ai_tool")
        if clerk_user_id is not None:
            params["clerk"] = clerk_user_id
            receipt_where.append("r.developer_external_id = :clerk")
            audit_where.append("a.clerk_user_id = :clerk")
        receipt_extra = ("AND " + " AND ".join(receipt_where)) if receipt_where else ""
        audit_extra = ("AND " + " AND ".join(audit_where)) if audit_where else ""

        if group_by_clerk:
            # Exclude NULL scopes from BOTH sides. UNION ALL + outer
            # GROUP BY so the same clerk in receipts + audit adds.
            sql = text(
                f"""
                SELECT scope, SUM(micros)::BIGINT AS total FROM (
                  SELECT
                    r.developer_external_id AS scope,
                    COALESCE(r.calculated_cost_microdollars, 0) AS micros
                  FROM llm_attempt_receipts r
                  WHERE r.workspace_id = CAST(:ws AS uuid)
                    AND r.finalized_at >= :since
                    AND r.calculated_cost_microdollars IS NOT NULL
                    AND r.usage_completeness = 'complete'
                    AND r.pricing_completeness IN ('priced', 'override_applied')
                    AND r.developer_external_id IS NOT NULL
                    {receipt_extra}
                  UNION ALL
                  SELECT
                    a.clerk_user_id AS scope,
                    CAST(ROUND(a.cost_usd_after * 1000000) AS BIGINT) AS micros
                  FROM guard_audit_events a
                  WHERE a.workspace_id = CAST(:ws AS uuid)
                    AND a.ts >= :since
                    AND a.cost_usd_after IS NOT NULL
                    AND a.clerk_user_id IS NOT NULL
                    AND NOT EXISTS (
                      SELECT 1 FROM llm_attempt_receipts rr
                      WHERE rr.request_id = a.request_id
                    )
                    {audit_extra}
                ) combined
                GROUP BY scope
                """
            )
            rows = self._db.execute(sql, params).all()
            return {row.scope: int(row.total or 0) for row in rows}

        # Scalar total. Same UNION ALL, no outer grouping.
        sql = text(
            f"""
            SELECT COALESCE(SUM(micros), 0)::BIGINT AS total FROM (
              SELECT
                COALESCE(r.calculated_cost_microdollars, 0) AS micros
              FROM llm_attempt_receipts r
              WHERE r.workspace_id = CAST(:ws AS uuid)
                AND r.finalized_at >= :since
                AND r.calculated_cost_microdollars IS NOT NULL
                AND r.usage_completeness = 'complete'
                AND r.pricing_completeness IN ('priced', 'override_applied')
                {receipt_extra}
              UNION ALL
              SELECT
                CAST(ROUND(a.cost_usd_after * 1000000) AS BIGINT) AS micros
              FROM guard_audit_events a
              WHERE a.workspace_id = CAST(:ws AS uuid)
                AND a.ts >= :since
                AND a.cost_usd_after IS NOT NULL
                AND NOT EXISTS (
                  SELECT 1 FROM llm_attempt_receipts rr
                  WHERE rr.request_id = a.request_id
                )
                {audit_extra}
            ) combined
            """
        )
        row = self._db.execute(sql, params).scalar()
        return {None: int(row or 0)}

    def unresolved_request_count_by_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        since: datetime,
        group_by_clerk: bool = False,
        ai_tool: Optional[str] = None,
        clerk_user_id: Optional[str] = None,
    ) -> dict[Optional[str], int]:
        """Companion to ``spend_micros_by_workspace``.

        Counts distinct request_ids whose ONLY receipts are non-settleable
        (PARTIAL usage or UNPRICED / INCOMPLETE pricing). These are
        real requests the enforcement counter will eventually charge
        for once the reconciler backfills a definitive receipt — but
        they're intentionally excluded from ``spend_micros_by_workspace``
        so the reported number is a defensible amount.

        Consumers can surface "$X, N in-progress" tags without inflating
        the priced total.
        """
        from sqlalchemy import text
        from app.core.budget_ledger import _is_transport

        params: dict[str, Any] = {
            "ws": str(workspace_id),
            "since": since,
        }
        where = []
        if ai_tool is not None:
            params["ai_tool"] = ai_tool
            if _is_transport(ai_tool):
                where.append("r.source = :ai_tool")
            else:
                where.append("r.client_tool = :ai_tool")
        if clerk_user_id is not None:
            params["clerk"] = clerk_user_id
            where.append("r.developer_external_id = :clerk")
        extra = ("AND " + " AND ".join(where)) if where else ""

        if group_by_clerk:
            sql = text(
                f"""
                SELECT r.developer_external_id AS scope,
                       COUNT(DISTINCT r.request_id) AS n
                FROM llm_attempt_receipts r
                WHERE r.workspace_id = CAST(:ws AS uuid)
                  AND r.finalized_at >= :since
                  AND r.developer_external_id IS NOT NULL
                  AND (
                    r.usage_completeness <> 'complete'
                    OR r.pricing_completeness NOT IN ('priced', 'override_applied')
                    OR r.calculated_cost_microdollars IS NULL
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM llm_attempt_receipts s
                    WHERE s.request_id = r.request_id
                      AND s.calculated_cost_microdollars IS NOT NULL
                      AND s.usage_completeness = 'complete'
                      AND s.pricing_completeness IN ('priced', 'override_applied')
                  )
                  {extra}
                GROUP BY scope
                """
            )
            rows = self._db.execute(sql, params).all()
            return {row.scope: int(row.n or 0) for row in rows}

        sql = text(
            f"""
            SELECT COUNT(DISTINCT r.request_id) AS n
            FROM llm_attempt_receipts r
            WHERE r.workspace_id = CAST(:ws AS uuid)
              AND r.finalized_at >= :since
              AND (
                r.usage_completeness <> 'complete'
                OR r.pricing_completeness NOT IN ('priced', 'override_applied')
                OR r.calculated_cost_microdollars IS NULL
              )
              AND NOT EXISTS (
                SELECT 1 FROM llm_attempt_receipts s
                WHERE s.request_id = r.request_id
                  AND s.calculated_cost_microdollars IS NOT NULL
                  AND s.usage_completeness = 'complete'
                  AND s.pricing_completeness IN ('priced', 'override_applied')
              )
              {extra}
            """
        )
        row = self._db.execute(sql, params).scalar()
        return {None: int(row or 0)}

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


def compute_cache_read_savings_for_receipt(
    receipt: LlmAttemptReceipt,
    *,
    uncached_rate_per_1m_usd: Decimal,
    cache_read_rate_per_1m_usd: Decimal,
) -> CacheReadSavings:
    """Gross cache-read savings for ONE receipt.

    Preferred entry point — callers should look up the rate card that
    matches ``receipt.pricing_version`` and ``receipt.model`` via
    ``PricingService.get_rate_card()``. That keeps the answer honest
    when a workspace's rate card changes mid-period or spans models.

    Formula: ``savings = (uncached_rate - cache_read_rate) × cache_read_tokens``.
    """
    read_tokens = int(receipt.cache_read_tokens or 0)
    uncached_tokens = int(receipt.uncached_input_tokens or 0)
    if read_tokens <= 0:
        return CacheReadSavings(
            cache_read_tokens=0,
            uncached_input_tokens=uncached_tokens,
            savings_microdollars=0,
            counterfactual_read_cost_microdollars=0,
        )
    delta_per_1m = uncached_rate_per_1m_usd - cache_read_rate_per_1m_usd
    savings_usd = Decimal(read_tokens) * delta_per_1m / Decimal(1_000_000)
    counterfactual_usd = (
        Decimal(read_tokens) * uncached_rate_per_1m_usd / Decimal(1_000_000)
    )
    return CacheReadSavings(
        cache_read_tokens=read_tokens,
        uncached_input_tokens=uncached_tokens,
        savings_microdollars=int((savings_usd * Decimal(1_000_000)).to_integral_value()),
        counterfactual_read_cost_microdollars=int(
            (counterfactual_usd * Decimal(1_000_000)).to_integral_value()
        ),
    )


def compute_cache_read_savings(
    total_cache_read_tokens: int,
    total_uncached_input_tokens: int,
    *,
    uncached_rate_per_1m_usd: Decimal,
    cache_read_rate_per_1m_usd: Decimal,
) -> CacheReadSavings:
    """Single-rate-pair helper for callers that already hold a
    single-model aggregate.

    Reviewer #6: caller MUST guarantee the token counts belong to one
    (model, pricing_version) slice. Aggregating across rate cards makes
    the answer nonsense. For multi-model queries, iterate receipts and
    sum ``compute_cache_read_savings_for_receipt`` results instead.
    """
    if total_cache_read_tokens <= 0:
        return CacheReadSavings(
            cache_read_tokens=0,
            uncached_input_tokens=int(total_uncached_input_tokens),
            savings_microdollars=0,
            counterfactual_read_cost_microdollars=0,
        )
    delta_per_1m = uncached_rate_per_1m_usd - cache_read_rate_per_1m_usd
    savings_usd = (
        Decimal(total_cache_read_tokens) * delta_per_1m / Decimal(1_000_000)
    )
    counterfactual_usd = (
        Decimal(total_cache_read_tokens) * uncached_rate_per_1m_usd / Decimal(1_000_000)
    )
    return CacheReadSavings(
        cache_read_tokens=int(total_cache_read_tokens),
        uncached_input_tokens=int(total_uncached_input_tokens),
        savings_microdollars=int(
            (savings_usd * Decimal(1_000_000)).to_integral_value()
        ),
        counterfactual_read_cost_microdollars=int(
            (counterfactual_usd * Decimal(1_000_000)).to_integral_value()
        ),
    )


# Back-compat alias. Session 6E docs pointed at this name.
compute_cache_savings = compute_cache_read_savings


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
    from sqlalchemy import cast, func
    from sqlalchemy import Text as _SqlText

    m = LlmAttemptReceipt
    if scope is AggregateScope.DEVELOPER:
        # Reviewer #4 (#2221 review at bbcb5388): most callers pass a
        # Clerk ID / email / "system:*" sentinel into
        # ``developer_external_id`` (Session 6c) — they do not have a
        # resolved internal user UUID. Grouping by
        # ``developer_user_id`` alone collapses every one of them into
        # the NULL bucket. COALESCE the two columns so per-developer
        # reporting stays intact regardless of which identity kind the
        # writer had.
        return func.coalesce(
            cast(m.developer_user_id, _SqlText),
            m.developer_external_id,
        )
    return {
        AggregateScope.WORKSPACE: m.workspace_id,
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
