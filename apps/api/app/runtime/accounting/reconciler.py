"""Reconciliation writer (#2209 Session 6D + 6H).

Backfills missing shadow receipts by reading
``guard_audit_events.routing_meta.attempts[]`` and detecting gaps at
the ``(request_id, attempt_ordinal)`` grain — not just the request
grain. Session 6H closes the reviewer's #3-second-bullet gap: a
request with a real receipt at ordinal 0 and a missing placeholder at
ordinal 1 (fallback that never got a receipt) is now detected and
backfilled.

Reconciler writes go through ``shadow_write(source="reconciler")`` so:

- Normalization + pricing run over any per-attempt
  ``response_bytes_b64`` the coordinator captured (failed attempts
  with an httpx.HTTPStatusError.response.content payload get real
  usage on the placeholder).
- ``_persist_atomic`` idempotency + placeholder-vs-real supersession
  invariants are preserved on this path too.

Not wired to any scheduler in this session; invoked by ops or a future
background job. Fully idempotent thanks to
``ON CONFLICT DO NOTHING`` on reconciler-source writes.
"""

from __future__ import annotations

import base64
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import SessionLocal

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ReconciliationResult:
    """Summary of one reconciliation pass — for ops dashboards + Session 7 gate.

    ``next_cursor`` is the ``(ts, request_id)`` tuple to pass on the next
    call so the following pass skips rows this pass already saw. ``None``
    means the scan hit the end of the period (no more rows). Reviewer #2
    at bbcb5388 called out that a fixed-limit scan without a cursor kept
    re-processing the earliest rows and never reached later gaps.
    """

    workspace_id: str
    period_start: datetime
    period_end: datetime
    audit_rows_scanned: int
    attempts_expected: int  # sum over routing_meta.attempts (default 1 per request)
    receipts_written: int
    receipts_skipped: int  # unique-constraint hits (already reconciled) or upsert no-ops
    errors: int
    next_cursor: Optional[tuple[datetime, uuid.UUID]] = None


def reconcile_missing_receipts(
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    db: Optional[Session] = None,
    limit: int = 1000,
    since_cursor: Optional[tuple[datetime, uuid.UUID]] = None,
) -> ReconciliationResult:
    """Scan guard_audit_events for one workspace, backfill missing per-attempt
    shadow rows.

    Attempt granularity: for each audit row, expected ordinals come from
    ``routing_meta.attempts[]`` (or default to ``{0}`` for legacy rows).
    Missing ``(request_id, attempt_ordinal)`` tuples get placeholder
    receipts via ``shadow_write(source="reconciler")``. Failed attempts
    that captured a provider error envelope get their bytes decoded +
    normalized + priced — the placeholder is 'metadata-only' only when
    the coordinator had nothing to record.

    Keyset pagination (reviewer #2 at bbcb5388): callers pass
    ``since_cursor=(ts, request_id)`` from the previous pass's
    ``result.next_cursor`` to resume where the last call left off. When
    ``next_cursor`` is None the scan hit the end of the period.
    """
    owned = db is None
    _db = db if db is not None else SessionLocal()

    scanned = 0
    expected = 0
    written = 0
    skipped = 0
    errors = 0

    try:
        audit_rows = _fetch_audit_rows(
            _db,
            workspace_id,
            period_start,
            period_end,
            limit,
            since_cursor,
        )
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
            attempts_expected=0,
            receipts_written=0,
            receipts_skipped=0,
            errors=1,
        )

    if not audit_rows:
        if owned:
            _db.close()
        return ReconciliationResult(
            workspace_id=str(workspace_id),
            period_start=period_start,
            period_end=period_end,
            audit_rows_scanned=0,
            attempts_expected=0,
            receipts_written=0,
            receipts_skipped=0,
            errors=0,
            next_cursor=None,  # end of period
        )

    request_ids = [row.request_id for row in audit_rows]
    existing = _fetch_existing_ordinals(_db, request_ids)

    for row in audit_rows:
        scanned += 1
        total_attempts, attempts_by_ordinal = _extract_attempts_from_meta(
            row.routing_meta
        )
        original_operation = _extract_operation_from_meta(row.routing_meta)
        expected_ordinals = (
            set(range(total_attempts)) if total_attempts > 0 else {0}
        )
        expected += len(expected_ordinals)
        missing = expected_ordinals - existing.get(row.request_id, set())
        for ordinal in sorted(missing):
            # None for slots whose metadata was malformed; _write_placeholder
            # falls back to audit-row defaults for provider/model in that
            # case rather than borrowing another ordinal's identity.
            attempt_meta = attempts_by_ordinal.get(ordinal)
            try:
                wrote = _write_placeholder(
                    row, ordinal, attempt_meta, original_operation=original_operation
                )
                if wrote:
                    written += 1
                else:
                    skipped += 1
            except Exception:
                log.exception(
                    "accounting.reconciler.placeholder_write_failed",
                    request_id=str(row.request_id),
                    ordinal=ordinal,
                )
                errors += 1

    if owned:
        try:
            _db.close()
        except Exception:
            pass

    # Advance the cursor to the last (ts, request_id) we scanned. If we
    # fetched fewer rows than ``limit``, we're at the end — return None.
    next_cursor: Optional[tuple[datetime, uuid.UUID]] = None
    if len(audit_rows) >= limit:
        last = audit_rows[-1]
        next_cursor = (last.audit_ts, last.request_id)

    return ReconciliationResult(
        workspace_id=str(workspace_id),
        period_start=period_start,
        period_end=period_end,
        audit_rows_scanned=scanned,
        attempts_expected=expected,
        receipts_written=written,
        receipts_skipped=skipped,
        errors=errors,
        next_cursor=next_cursor,
    )


# ─── internal helpers ─────────────────────────────────────────────────────


def _fetch_audit_rows(
    db: Session,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    limit: int,
    since_cursor: Optional[tuple[datetime, uuid.UUID]] = None,
) -> list:
    """Fetch audit rows in the window, resuming from ``since_cursor``.

    Session 6H removed the LEFT JOIN against receipts (that was
    request-granular). Session 6J adds keyset pagination: reviewer #2
    at bbcb5388 pointed out that a fixed-limit ``ORDER BY ts LIMIT
    1000`` kept re-scanning the earliest rows and never reached later
    gaps. Cursor is ``(ts, request_id)`` — a stable pair thanks to the
    unique index on ``request_id``.
    """
    cursor_ts: Optional[datetime] = None
    cursor_rid: Optional[uuid.UUID] = None
    if since_cursor is not None:
        cursor_ts, cursor_rid = since_cursor

    if cursor_ts is None:
        sql = text(
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
                gae.ts AS audit_ts,
                gae.routing_meta
            FROM guard_audit_events gae
            WHERE gae.workspace_id = :workspace_id
              AND gae.ts >= :period_start
              AND gae.ts <  :period_end
              AND gae.request_id IS NOT NULL
            ORDER BY gae.ts ASC, gae.request_id ASC
            LIMIT :limit
            """
        )
        params = {
            "workspace_id": workspace_id,
            "period_start": period_start,
            "period_end": period_end,
            "limit": limit,
        }
    else:
        sql = text(
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
                gae.ts AS audit_ts,
                gae.routing_meta
            FROM guard_audit_events gae
            WHERE gae.workspace_id = :workspace_id
              AND gae.ts >= :period_start
              AND gae.ts <  :period_end
              AND gae.request_id IS NOT NULL
              AND (gae.ts, gae.request_id) > (:cursor_ts, :cursor_rid)
            ORDER BY gae.ts ASC, gae.request_id ASC
            LIMIT :limit
            """
        )
        params = {
            "workspace_id": workspace_id,
            "period_start": period_start,
            "period_end": period_end,
            "cursor_ts": cursor_ts,
            "cursor_rid": cursor_rid,
            "limit": limit,
        }
    return db.execute(sql, params).all()


def _fetch_existing_ordinals(db: Session, request_ids: list) -> dict:
    """Return ``{request_id: set(attempt_ordinal, ...)}`` for the scan batch.

    One query for the whole batch instead of N per-request queries.
    Includes BOTH real and placeholder receipts — a placeholder counts
    as 'present' so we don't re-insert it (avoids the Session 6G
    rescan-loop issue on the reconciler side too).
    """
    if not request_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT request_id, attempt_ordinal
            FROM llm_attempt_receipts
            WHERE request_id = ANY(:ids)
            """
        ),
        {"ids": request_ids},
    ).all()
    out: dict = defaultdict(set)
    for row in rows:
        out[row.request_id].add(int(row.attempt_ordinal))
    return dict(out)


def _extract_attempts_from_meta(routing_meta: Any) -> tuple[int, dict[int, dict]]:
    """Pull ``attempts[]`` off routing_meta.

    Returns ``(total_count, {index: attempt_dict})``. ``total_count`` is
    the ORIGINAL array length so the caller's expected ordinal set covers
    every position — including ones where the attempt metadata was
    malformed. Only dict entries are keyed into the returned map; the
    slot remains reserved but has no per-attempt metadata (caller falls
    back to audit-row defaults for that ordinal).

    Reviewer #6 (#2221 review at bbcb5388): the prior list-based return
    dropped non-dict entries entirely, compressing ordinals. Under
    ``[attempt0, null, attempt2]`` the reconciler used to write a
    placeholder for ordinal 1 with attempt2's metadata — wrong.
    """
    if not routing_meta:
        return 0, {}
    if isinstance(routing_meta, str):
        import json as _json
        try:
            routing_meta = _json.loads(routing_meta)
        except Exception:
            return 0, {}
    if not isinstance(routing_meta, Mapping):
        return 0, {}
    attempts = routing_meta.get("attempts")
    if not isinstance(attempts, list):
        return 0, {}
    total = len(attempts)
    keyed = {i: a for i, a in enumerate(attempts) if isinstance(a, Mapping)}
    return total, keyed


def _extract_operation_from_meta(routing_meta: Any) -> Optional[str]:
    """Session 6J reviewer #5: pull ``operation`` off routing_meta so the
    reconciler can pick the right normalizer family. Returns None for
    legacy audit rows written before Session 6J; the caller falls back
    to ``"reconciled"`` and the writer picks OPENAI_CHAT as default."""
    if not routing_meta:
        return None
    if isinstance(routing_meta, str):
        import json as _json
        try:
            routing_meta = _json.loads(routing_meta)
        except Exception:
            return None
    if not isinstance(routing_meta, Mapping):
        return None
    op = routing_meta.get("operation")
    return op if isinstance(op, str) and op else None


def _write_placeholder(
    row,
    ordinal: int,
    attempt_meta: Optional[Mapping],
    *,
    original_operation: Optional[str] = None,
) -> bool:
    """Write one reconciler-sourced placeholder for a missing attempt.

    Uses ``shadow_write(source="reconciler")`` so it goes through the
    same normalization + pricing + atomic upsert path as live writes.
    Returns True if the shadow_write returned a receipt id (row inserted),
    False if it was a no-op (unique constraint via ON CONFLICT DO NOTHING).
    """
    from app.runtime.accounting.contracts import ExecutionOutcome
    from app.runtime.accounting.shadow_writer import shadow_write

    attempt_meta = attempt_meta or {}
    succeeded = bool(attempt_meta.get("succeeded", True))
    is_winner = succeeded  # Any successful attempt in routing_meta IS the winner
    provider = attempt_meta.get("provider_or_integration") or row.provider or "unknown"
    model = attempt_meta.get("model") or row.model or "unknown"

    # Decode captured failed-attempt bytes when present. Winner bytes
    # aren't in routing_meta (they went to the client) — the winner
    # placeholder relies on audit tokens_after / cost_usd_after.
    response_bytes: Optional[bytes] = None
    b64 = attempt_meta.get("response_bytes_b64")
    if b64:
        try:
            response_bytes = base64.b64decode(b64)
        except Exception:
            response_bytes = None

    execution_outcome = (
        ExecutionOutcome.SUCCEEDED.value if succeeded else ExecutionOutcome.FAILED.value
    )
    # If we're reconciling a settled row, mark it late so Session 7
    # activation review can see this came from the backfill path.
    if execution_outcome == ExecutionOutcome.SUCCEEDED.value:
        execution_outcome = ExecutionOutcome.RECONCILED_LATE.value

    # Reviewer #5: preserve the original operation so the normalizer
    # picks the right family (OpenAI Chat vs Responses). Legacy audit
    # rows without ``routing_meta.operation`` fall back to "reconciled";
    # provenance below records that fact.
    operation = original_operation or "reconciled"

    result = shadow_write(
        workspace_id=row.workspace_id,
        request_id=row.request_id,
        provider=provider,
        model=model,
        operation=operation,
        dispatched=True,
        response_bytes=response_bytes,
        developer_external_id=(
            str(row.clerk_user_id) if row.clerk_user_id else None
        ),
        source="reconciler",
        client_tool=row.ai_tool,
        attempt_ordinal=ordinal,
        succeeded=succeeded,
        execution_outcome=execution_outcome,
    )
    return result is not None
