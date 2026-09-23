"""Reconciliation writer (#2209 Session 6D).

Backfills missing shadow receipts. A settled ``guard_audit_events`` row
with no matching ``llm_attempt_receipts`` row means one of:

- The shadow writer's kill-switch was off when the request settled and
  ops has since enabled it (backfill closes the historical gap).
- shadow_write raised an unexpected exception at settlement time.
- A worker crash truncated the settle path after audit-write but before
  shadow-write.

This module scans for the gap and writes placeholder receipts derived
from the audit row's known-good columns (workspace_id, request_id,
provider, model, tokens_after, cost_usd_after). The receipts carry
``usage_origin=RECONCILED`` and ``execution_outcome=RECONCILED_LATE`` so
Session 7's activation review can see they were not settled through the
normal writer path.

Not wired to any scheduler in this session — invoked manually by ops or
from a future background job. The function itself is idempotent (the
unique constraint on ``(request_id, attempt_ordinal)`` guarantees a
duplicate run inserts nothing).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.contracts import (
    CONTRACT_VERSION,
    ExecutionOutcome,
    PricingCompleteness,
    UsageCompleteness,
    UsageOrigin,
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ReconciliationResult:
    """Summary of one reconciliation pass — for ops dashboards + Session 7 gate."""

    workspace_id: str
    period_start: datetime
    period_end: datetime
    audit_rows_scanned: int
    receipts_written: int
    receipts_skipped: int  # unique-constraint hits (already reconciled)
    errors: int


def reconcile_missing_receipts(
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    db: Optional[Session] = None,
    limit: int = 1000,
) -> ReconciliationResult:
    """Scan guard_audit_events for one workspace, backfill missing shadow rows.

    Idempotent: the ``(request_id, attempt_ordinal)`` unique constraint on
    ``llm_attempt_receipts`` guarantees a second run of the same period
    inserts nothing new. Returns counts so a caller can log +
    aggregate them (Session 7 gate criterion 5: reconciler clean).
    """
    owned = db is None
    _db = db if db is not None else SessionLocal()

    scanned = 0
    written = 0
    skipped = 0
    errors = 0

    try:
        # Pull unmatched audit rows. Same LEFT JOIN as the Session 6
        # ``settled_requests_missing_shadow_count`` metric, but selecting
        # the fields we need to synthesize the receipt.
        #
        # #2209 reviewer #1 (#2221 review at 1219d734): the column in
        # ``guard_audit_events`` is ``ts``, not ``timestamp``. Prior code
        # queried the wrong name; the metric caught the resulting SQL
        # error and returned zero, hiding the failure. Fixed here + in
        # metrics._count_settled_missing_shadow.
        #
        # Reviewer #4: also filter out reconciled placeholders so a
        # real receipt written later can supersede them (see
        # write_receipts_for_attempts placeholder-promotion logic).
        rows = _db.execute(
            text(
                """
                SELECT
                    gae.workspace_id,
                    gae.request_id,
                    gae.provider,
                    gae.model,
                    gae.clerk_user_id,
                    gae.ai_tool,
                    gae.tokens_after,
                    gae.cost_usd_after,
                    gae.ts AS audit_ts
                FROM guard_audit_events gae
                LEFT JOIN llm_attempt_receipts r
                  ON r.request_id = gae.request_id
                 AND r.source IS DISTINCT FROM 'reconciler'
                WHERE gae.workspace_id = :workspace_id
                  AND gae.ts >= :period_start
                  AND gae.ts <  :period_end
                  AND gae.request_id IS NOT NULL
                  AND r.id IS NULL
                LIMIT :limit
                """
            ),
            {
                "workspace_id": workspace_id,
                "period_start": period_start,
                "period_end": period_end,
                "limit": limit,
            },
        ).all()
    except Exception:
        log.exception(
            "accounting.reconciler.scan_failed",
            workspace_id=workspace_id,
        )
        if owned:
            try:
                _db.close()
            except Exception:
                pass
        return ReconciliationResult(
            workspace_id=str(workspace_id),
            period_start=period_start,
            period_end=period_end,
            audit_rows_scanned=0,
            receipts_written=0,
            receipts_skipped=0,
            errors=1,
        )

    for row in rows:
        scanned += 1
        try:
            legacy_cost_micros = None
            if row.cost_usd_after is not None:
                legacy_cost_micros = int(
                    (Decimal(str(row.cost_usd_after)) * Decimal(1_000_000))
                    .to_integral_value()
                )
            receipt = LlmAttemptReceipt(
                id=uuid.uuid4(),
                workspace_id=row.workspace_id,
                request_id=row.request_id,
                attempt_ordinal=0,
                contract_version=CONTRACT_VERSION,
                developer_external_id=(
                    str(row.clerk_user_id) if row.clerk_user_id else None
                ),
                source="reconciler",
                client_tool=row.ai_tool,
                provider=row.provider or "unknown",
                model=row.model or "unknown",
                operation="reconciled",
                execution_outcome=ExecutionOutcome.RECONCILED_LATE.value,
                total_input_tokens=None,
                total_output_tokens=(
                    int(row.tokens_after) if row.tokens_after is not None else None
                ),
                usage_origin=UsageOrigin.RECONCILED.value,
                usage_completeness=UsageCompleteness.PENDING.value,
                pricing_completeness=PricingCompleteness.UNPRICED.value,
                legacy_cost_microdollars=legacy_cost_micros,
                normalizer_version=None,
                calculation_provenance={
                    "reconciled_from": "guard_audit_events",
                    "audit_timestamp": (
                        row.audit_ts.isoformat() if row.audit_ts else None
                    ),
                },
                finalized_at=datetime.now(timezone.utc),
            )
            _db.add(receipt)
            _db.commit()
            written += 1
        except Exception:
            # Unique-constraint violation (another writer got there first)
            # or malformed audit row. Either is fine — roll back and count.
            try:
                _db.rollback()
            except Exception:
                pass
            skipped += 1
            log.debug(
                "accounting.reconciler.receipt_skipped",
                request_id=str(row.request_id),
            )

    if owned:
        try:
            _db.close()
        except Exception:
            pass

    return ReconciliationResult(
        workspace_id=str(workspace_id),
        period_start=period_start,
        period_end=period_end,
        audit_rows_scanned=scanned,
        receipts_written=written,
        receipts_skipped=skipped,
        errors=errors,
    )
