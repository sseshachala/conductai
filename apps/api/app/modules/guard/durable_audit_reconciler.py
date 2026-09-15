"""Phase 4 of #1959 — durable-audit reconciler.

A crash / timeout / server restart between insert_accepted() and
finalize() leaves guard_audit_events rows stuck in lifecycle_state='
accepted' with no follow-up. This module flips those rows to 'orphaned'
once their lease has expired so:

- Flight Recorder UI stops rendering them as "in flight" indefinitely
- Downstream analytics can trust that 'accepted' means "genuinely
  waiting for finalize" rather than "abandoned mid-request"
- Phase 5's contract-test gate has a clean invariant to assert on

Runs cheaply via the partial index we shipped in Phase 1:

    ix_guard_audit_events_accepted_lease
    ON guard_audit_events (workspace_id, lease_expires_at)
    WHERE lifecycle_state = 'accepted'

...so the scan is O(orphans), never O(all rows).

The WHERE clause on the UPDATE mirrors finalize()'s invariant — we
NEVER touch a row whose lifecycle_state has already moved past
'accepted'. That's the property Phase 4's reconciler relies on being
able to prove.
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session


log = structlog.get_logger(__name__)


# Default cap per pass. Tuned so a single reconciler run finishes well
# under the poll interval even if a mass-orphan event occurs (e.g.
# API restart during a burst). Overridable per call.
DEFAULT_MAX_BATCH = 500


def reconcile_orphaned(
    db: Session,
    *,
    workspace_id: str | None = None,
    max_batch: int = DEFAULT_MAX_BATCH,
) -> int:
    """Flip expired 'accepted' rows to 'orphaned'. Returns rowcount.

    Scope:
    - `workspace_id` (optional): if set, scan only that workspace. If
      None, scan across every workspace — the intended use for the
      background daemon.
    - `max_batch`: cap on the number of rows updated per call. Any
      remainder gets picked up on the next pass. Prevents a runaway
      lock hold if the accepted-with-expired-lease set is huge.

    Idempotent: calling twice back-to-back is safe. The WHERE clause on
    `lifecycle_state='accepted'` means the second call sees zero rows
    (they've already been flipped to 'orphaned').

    Never regresses a finalized row — the same invariant finalize()
    established. Phase 5's contract tests assert this explicitly.
    """
    sql = """
        WITH candidates AS (
            SELECT id
            FROM guard_audit_events
            WHERE lifecycle_state = 'accepted'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < now()
              {workspace_predicate}
            ORDER BY lease_expires_at ASC
            LIMIT :max_batch
            FOR UPDATE SKIP LOCKED
        )
        UPDATE guard_audit_events e
        SET lifecycle_state = 'orphaned',
            finalized_at    = COALESCE(e.finalized_at, now())
        FROM candidates c
        WHERE e.id = c.id
          AND e.lifecycle_state = 'accepted'
    """
    params: dict = {"max_batch": max_batch}
    if workspace_id is not None:
        params["workspace_id"] = workspace_id
        sql = sql.format(workspace_predicate="AND workspace_id = CAST(:workspace_id AS uuid)")
    else:
        sql = sql.format(workspace_predicate="")

    try:
        result = db.execute(text(sql), params)
        db.commit()
        count = result.rowcount or 0
        if count:
            log.info(
                "guard.durable_audit.reconciled",
                count=count,
                workspace_id=workspace_id or "*",
            )
        return count
    except Exception:
        db.rollback()
        log.exception(
            "guard.durable_audit.reconcile_failed",
            workspace_id=workspace_id or "*",
        )
        # Re-raise so the caller (worker loop) treats it as a cycle
        # failure and doesn't silently pretend the pass succeeded.
        raise
