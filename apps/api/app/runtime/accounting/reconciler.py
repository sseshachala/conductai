"""Reconciliation writer (#2209 Session 6D + 6H).

Backfills missing shadow receipts by reading
``guard_audit_events.routing_meta.attempts[]`` and detecting gaps at
the ``(request_id, attempt_ordinal)`` grain — not just the request
grain. Session 6H closes the reviewer's #3-second-bullet gap: a
request with a real receipt at ordinal 0 and a missing placeholder at
ordinal 1 (fallback that never got a receipt) is now detected and
backfilled.

Reconciler writes go through ``shadow_write(source="reconciler",
pinned_shadow_enabled=True)`` so:

- Normalization + pricing run over any per-attempt
  ``response_bytes_b64`` the coordinator captured (failed attempts
  with an httpx.HTTPStatusError.response.content payload get real
  usage on the placeholder).
- ``_persist_atomic`` idempotency + placeholder-vs-real supersession
  invariants are preserved on this path too.
- Canary flag is bypassed — reconciler is manual/opt-in already.

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
    """Summary of one reconciliation pass — for ops dashboards + Session 7 gate."""

    workspace_id: str
    period_start: datetime
    period_end: datetime
    audit_rows_scanned: int
    attempts_expected: int  # sum over routing_meta.attempts (default 1 per request)
    receipts_written: int
    receipts_skipped: int  # unique-constraint hits (already reconciled) or upsert no-ops
    errors: int


def reconcile_missing_receipts(
    *,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    db: Optional[Session] = None,
    limit: int = 1000,
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
    """
    owned = db is None
    _db = db if db is not None else SessionLocal()

    scanned = 0
    expected = 0
    written = 0
    skipped = 0
    errors = 0

    try:
        audit_rows = _fetch_audit_rows(_db, workspace_id, period_start, period_end, limit)
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
        )

    request_ids = [row.request_id for row in audit_rows]
    existing = _fetch_existing_ordinals(_db, request_ids)

    for row in audit_rows:
        scanned += 1
        attempts = _extract_attempts_from_meta(row.routing_meta)
        expected_ordinals = set(range(len(attempts))) if attempts else {0}
        expected += len(expected_ordinals)
        missing = expected_ordinals - existing.get(row.request_id, set())
        for ordinal in sorted(missing):
            attempt_meta = attempts[ordinal] if ordinal < len(attempts) else None
            try:
                wrote = _write_placeholder(row, ordinal, attempt_meta)
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

    return ReconciliationResult(
        workspace_id=str(workspace_id),
        period_start=period_start,
        period_end=period_end,
        audit_rows_scanned=scanned,
        attempts_expected=expected,
        receipts_written=written,
        receipts_skipped=skipped,
        errors=errors,
    )


# ─── internal helpers ─────────────────────────────────────────────────────


def _fetch_audit_rows(
    db: Session,
    workspace_id: str,
    period_start: datetime,
    period_end: datetime,
    limit: int,
) -> list:
    """Fetch every audit row in the window, INCLUDING routing_meta.

    Session 6H change: no LEFT JOIN against receipts — that was
    request-granular and hid missing fallback ordinals. Per-attempt
    filtering happens in Python via ``_fetch_existing_ordinals`` below.
    ``ORDER BY gae.ts ASC`` gives deterministic pagination.
    """
    return db.execute(
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
                gae.ts AS audit_ts,
                gae.routing_meta
            FROM guard_audit_events gae
            WHERE gae.workspace_id = :workspace_id
              AND gae.ts >= :period_start
              AND gae.ts <  :period_end
              AND gae.request_id IS NOT NULL
            ORDER BY gae.ts ASC
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


def _extract_attempts_from_meta(routing_meta: Any) -> list[dict]:
    """Pull ``attempts[]`` off routing_meta. Handles JSONB dict form,
    string form (some DB drivers stringify JSONB), and missing/None.
    Returns [] when nothing usable is present (caller defaults to
    ``{0}`` as the expected ordinal set)."""
    if not routing_meta:
        return []
    if isinstance(routing_meta, str):
        import json as _json
        try:
            routing_meta = _json.loads(routing_meta)
        except Exception:
            return []
    if not isinstance(routing_meta, Mapping):
        return []
    attempts = routing_meta.get("attempts")
    if not isinstance(attempts, list):
        return []
    return [a for a in attempts if isinstance(a, Mapping)]


def _write_placeholder(row, ordinal: int, attempt_meta: Optional[Mapping]) -> bool:
    """Write one reconciler-sourced placeholder for a missing attempt.

    Uses ``shadow_write(source="reconciler", pinned_shadow_enabled=True)``
    so it goes through the same normalization + pricing + atomic upsert
    path as live writes. Returns True if the shadow_write returned a
    receipt id (row inserted), False if it was a no-op (unique
    constraint via ON CONFLICT DO NOTHING, or shadow disabled).
    """
    from app.runtime.accounting.contracts import (
        CONTRACT_VERSION,
        ExecutionOutcome,
    )
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

    # Legacy tokens + cost only apply to the winning attempt (audit
    # tokens_after are per-request and reflect the winning path).
    legacy_input: Optional[int] = None
    legacy_output: Optional[int] = None
    legacy_cost_usd: Optional[float] = None
    if is_winner:
        legacy_output = (
            int(row.tokens_after) if row.tokens_after is not None else None
        )
        legacy_cost_usd = (
            float(row.cost_usd_after) if row.cost_usd_after is not None else None
        )

    execution_outcome = (
        ExecutionOutcome.SUCCEEDED.value if succeeded else ExecutionOutcome.FAILED.value
    )
    # If we're reconciling a settled row, mark it late so Session 7
    # activation review can see this came from the backfill path.
    if execution_outcome == ExecutionOutcome.SUCCEEDED.value:
        execution_outcome = ExecutionOutcome.RECONCILED_LATE.value

    result = shadow_write(
        workspace_id=row.workspace_id,
        request_id=row.request_id,
        provider=provider,
        model=model,
        operation="reconciled",
        dispatched=True,
        response_bytes=response_bytes,
        legacy_input_tokens=legacy_input,
        legacy_output_tokens=legacy_output,
        legacy_cost_usd=legacy_cost_usd,
        developer_external_id=(
            str(row.clerk_user_id) if row.clerk_user_id else None
        ),
        source="reconciler",
        client_tool=row.ai_tool,
        attempt_ordinal=ordinal,
        succeeded=succeeded,
        execution_outcome=execution_outcome,
        # Bypass the canary — reconciliation is manual/opt-in already.
        pinned_shadow_enabled=True,
        pinned_contract_version=CONTRACT_VERSION,
    )
    return result is not None
