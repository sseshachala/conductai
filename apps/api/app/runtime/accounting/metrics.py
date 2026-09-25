"""Shadow-mode metrics (#2209 Session 6).

Computes the deltas Session 7's activation gate uses to decide whether the
new accounting engine can retire the legacy path. Nothing here mutates
receipts; it only reads.

Session 7 exit criteria (documented; enforced by ops review):

1. **Cost delta small and explained.** Sum of |new - legacy| per provider/
   model within a documented tolerance (or the delta explained by known
   cache/reasoning correctness fixes).
2. **No unpriced surprises.** ``PricingCompleteness.UNPRICED`` count is
   zero or the unpriced models are on a known-and-approved list.
3. **Missing-usage bounded.** ``UsageCompleteness.UNAVAILABLE`` count is
   below a documented rate (e.g. <1% of dispatched attempts).
4. **No duplicate settlements.** The unique constraint on (request_id,
   attempt_ordinal) guarantees this at the DB layer, but the metric
   verifies IntegrityError rate is zero.
5. **Reconciliation clean.** Requests settled to guard_audit_events but
   missing an llm_attempt_receipts row are below a documented rate and
   trending down.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Optional

from sqlalchemy import and_, func, literal_column, select
from sqlalchemy.orm import Session

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.contracts import (
    PricingCompleteness,
    UsageCompleteness,
)


@dataclass(frozen=True)
class DeltaBucket:
    """One row of the delta report — per provider/model breakdown."""

    provider: str
    model: str
    receipt_count: int
    new_cost_microdollars: int
    legacy_cost_microdollars: int
    abs_delta_microdollars: int  # sum of |new - legacy| per row
    max_delta_microdollars: int  # max |new - legacy| single row
    unpriced_count: int
    incomplete_pricing_count: int


@dataclass(frozen=True)
class ShadowDeltaReport:
    """Session 7 gate view. All numbers from llm_attempt_receipts.

    Computed for one workspace + period. Aggregates across all providers,
    with a per-provider/model breakdown for drilldown. Session 7 activation
    reviews this per canary workspace before deleting legacy paths.
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime

    receipt_count: int
    dispatched_count: int

    # Cost deltas
    new_cost_microdollars: int
    legacy_cost_microdollars: int
    sum_abs_delta_microdollars: int
    max_abs_delta_microdollars: int

    # Provenance counts (from breakdowns)
    missing_usage_count: int
    partial_usage_count: int
    pending_usage_count: int
    unpriced_count: int
    incomplete_pricing_count: int

    # Reconciliation
    settled_requests_missing_shadow_count: int  # requires the legacy audit table
    # Session 6G reviewer #3: requests whose only receipts are
    # reconciler-source placeholders. Session 7 gate criterion 5 now
    # covers both counts trending down.
    settled_requests_placeholder_only_count: int = 0

    # Per-(provider, model) drilldown
    buckets: list[DeltaBucket] = field(default_factory=list)

    @property
    def relative_delta_pct(self) -> Optional[float]:
        """|Σ(new - legacy)| / legacy × 100, or None if legacy is 0."""
        if not self.legacy_cost_microdollars:
            return None
        signed = self.new_cost_microdollars - self.legacy_cost_microdollars
        return abs(signed) / self.legacy_cost_microdollars * 100.0

    @property
    def missing_usage_rate(self) -> float:
        """Fraction of dispatched attempts with UNAVAILABLE usage."""
        if not self.dispatched_count:
            return 0.0
        return self.missing_usage_count / self.dispatched_count

    @property
    def unpriced_rate(self) -> float:
        """Fraction of receipts that could not be priced."""
        if not self.receipt_count:
            return 0.0
        return self.unpriced_count / self.receipt_count


def compute_shadow_delta_report(
    db: Session,
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
) -> ShadowDeltaReport:
    """One-shot query against llm_attempt_receipts.

    Session 7 activation reviews the returned report per canary workspace
    against the documented exit criteria. Not called in the request path.
    """
    m = LlmAttemptReceipt
    period_where = and_(
        m.workspace_id == workspace_id,
        m.finalized_at >= period_start,
        m.finalized_at < period_end,
    )

    # #2209 Tier 1: legacy_cost_microdollars column dropped. Delta
    # arithmetic is trivially zero post-cutover — the new engine IS the
    # source of truth. Report zeros for backward-compat with the
    # ShadowDeltaReport dataclass shape (callers just render "no delta").
    totals_row = db.execute(
        select(
            func.count(m.id).label("receipt_count"),
            func.coalesce(func.sum(m.calculated_cost_microdollars), 0).label("new_cost"),
        ).where(period_where)
    ).one()

    dispatched_count = db.execute(
        select(func.count(m.id))
        .where(period_where)
        .where(m.execution_outcome != "rejected_preflight")
    ).scalar_one()

    def _count_where(col, value) -> int:
        return db.execute(
            select(func.count(m.id)).where(period_where).where(col == value)
        ).scalar_one()

    missing_usage = _count_where(m.usage_completeness, UsageCompleteness.UNAVAILABLE.value)
    partial_usage = _count_where(m.usage_completeness, UsageCompleteness.PARTIAL.value)
    pending_usage = _count_where(m.usage_completeness, UsageCompleteness.PENDING.value)
    unpriced = _count_where(m.pricing_completeness, PricingCompleteness.UNPRICED.value)
    incomplete_pricing = _count_where(
        m.pricing_completeness, PricingCompleteness.INCOMPLETE.value
    )

    # Per-provider/model buckets for drilldown.
    bucket_rows = db.execute(
        select(
            m.provider,
            m.model,
            func.count(m.id).label("cnt"),
            func.coalesce(func.sum(m.calculated_cost_microdollars), 0).label("new_c"),
        )
        .where(period_where)
        .group_by(m.provider, m.model)
    ).all()

    buckets: list[DeltaBucket] = []
    for row in bucket_rows:
        buckets.append(
            DeltaBucket(
                provider=row.provider,
                model=row.model,
                receipt_count=int(row.cnt),
                new_cost_microdollars=int(row.new_c),
                legacy_cost_microdollars=0,
                abs_delta_microdollars=0,
                max_delta_microdollars=0,
                unpriced_count=_count_within_bucket(
                    db, period_where, m, row.provider, row.model,
                    m.pricing_completeness, PricingCompleteness.UNPRICED.value,
                ),
                incomplete_pricing_count=_count_within_bucket(
                    db, period_where, m, row.provider, row.model,
                    m.pricing_completeness, PricingCompleteness.INCOMPLETE.value,
                ),
            )
        )

    missing_shadow = _count_settled_missing_shadow(
        db,
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
    )
    placeholder_only = _count_settled_placeholder_only(
        db,
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
    )

    return ShadowDeltaReport(
        workspace_id=str(workspace_id),
        period_start=period_start,
        period_end=period_end,
        receipt_count=int(totals_row.receipt_count),
        dispatched_count=int(dispatched_count),
        new_cost_microdollars=int(totals_row.new_cost),
        legacy_cost_microdollars=0,
        sum_abs_delta_microdollars=0,
        max_abs_delta_microdollars=0,
        missing_usage_count=missing_usage,
        partial_usage_count=partial_usage,
        pending_usage_count=pending_usage,
        unpriced_count=unpriced,
        incomplete_pricing_count=incomplete_pricing,
        settled_requests_missing_shadow_count=missing_shadow,
        settled_requests_placeholder_only_count=placeholder_only,
        buckets=buckets,
    )


def _count_within_bucket(
    db: Session, period_where, m, provider, model, col, value
) -> int:
    return db.execute(
        select(func.count(m.id))
        .where(period_where)
        .where(m.provider == provider)
        .where(m.model == model)
        .where(col == value)
    ).scalar_one()


def _count_settled_missing_shadow(
    db: Session,
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
) -> int:
    """Count guard_audit_events rows that don't have a matching
    llm_attempt_receipts row. Reconciliation signal.

    Uses raw SQL against guard_audit_events without importing the model
    (audit is a Guard module concern; we only need request_id).
    """
    from sqlalchemy import text

    # #2209 Session 6G reviewer #3 (#2221 review at 42d89898): this
    # metric now counts requests with NO receipt at all (real or
    # placeholder). Placeholder-only requests are tracked separately by
    # ``_count_settled_placeholder_only`` so ops sees the gap without
    # driving the reconciler into a placeholder-rescan loop.
    #
    # Column is ``gae.ts`` (fixed in Session 6F — see reviewer #1).
    # Exception is re-raised, not swallowed — a broken query previously
    # hid the column-name bug for a whole review cycle.
    sql = text(
        """
        SELECT COUNT(*)
        FROM guard_audit_events gae
        LEFT JOIN llm_attempt_receipts r
          ON r.request_id = gae.request_id
        WHERE gae.workspace_id = :workspace_id
          AND gae.ts >= :period_start
          AND gae.ts <  :period_end
          AND gae.request_id IS NOT NULL
          AND r.id IS NULL
        """
    )
    try:
        return int(
            db.execute(
                sql,
                {
                    "workspace_id": workspace_id,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            ).scalar_one()
        )
    except Exception:
        import structlog as _structlog
        _structlog.get_logger(__name__).exception(
            "accounting.metrics.settled_missing_shadow_query_failed",
            workspace_id=str(workspace_id),
        )
        raise


def _count_settled_placeholder_only(
    db: Session,
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
) -> int:
    """Session 6G reviewer #3: count requests whose ONLY receipt(s) are
    reconciler-source placeholders. These are 'reconciled but never
    resolved' — ops watches this trend down as real writes arrive and
    the atomic upsert promotes placeholders into real receipts.

    A NOT EXISTS clause guarantees we do not count a request that has
    any real receipt at any attempt_ordinal, even if a stale placeholder
    also happens to exist.
    """
    from sqlalchemy import text

    sql = text(
        """
        SELECT COUNT(DISTINCT gae.request_id)
        FROM guard_audit_events gae
        JOIN llm_attempt_receipts placeholder
          ON placeholder.request_id = gae.request_id
         AND placeholder.source = 'reconciler'
        WHERE gae.workspace_id = :workspace_id
          AND gae.ts >= :period_start
          AND gae.ts <  :period_end
          AND gae.request_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM llm_attempt_receipts real
              WHERE real.request_id = gae.request_id
                AND real.source IS DISTINCT FROM 'reconciler'
          )
        """
    )
    try:
        return int(
            db.execute(
                sql,
                {
                    "workspace_id": workspace_id,
                    "period_start": period_start,
                    "period_end": period_end,
                },
            ).scalar_one()
        )
    except Exception:
        import structlog as _structlog
        _structlog.get_logger(__name__).exception(
            "accounting.metrics.settled_placeholder_only_query_failed",
            workspace_id=str(workspace_id),
        )
        raise


def compute_deltas_from_rows(rows) -> Mapping[str, int]:
    """In-process delta computation for tests + reconciliation harnesses.

    Takes a collection of receipt-like objects and returns:
        {
          "new_cost": int,
          "legacy_cost": int,
          "sum_abs_delta": int,
          "max_abs_delta": int,
        }
    """
    new_cost = 0
    legacy_cost = 0
    sum_abs = 0
    max_abs = 0
    for r in rows:
        new = int(getattr(r, "calculated_cost_microdollars", 0) or 0)
        legacy = int(getattr(r, "legacy_cost_microdollars", 0) or 0)
        delta = abs(new - legacy)
        new_cost += new
        legacy_cost += legacy
        sum_abs += delta
        if delta > max_abs:
            max_abs = delta
    return {
        "new_cost": new_cost,
        "legacy_cost": legacy_cost,
        "sum_abs_delta": sum_abs,
        "max_abs_delta": max_abs,
    }
