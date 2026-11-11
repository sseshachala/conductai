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

    Also stamps decision='error' so a row surfaces as an error in any
    query that groups by decision (dashboards, spend rollups, trigger
    conditions). Without this stamp, orphaned rows kept the placeholder
    'accepted' decision from insert_accepted() and misled the analytics
    into treating them as normal allowed traffic.
    """
    sql = """
        SELECT id, workspace_id
        FROM guard_audit_events
        WHERE lifecycle_state = 'accepted'
          AND lease_expires_at IS NOT NULL
          AND lease_expires_at < now()
          {workspace_predicate}
        ORDER BY lease_expires_at ASC
        LIMIT :max_batch
    """
    params: dict = {"max_batch": max_batch}
    if workspace_id is not None:
        params["workspace_id"] = workspace_id
        sql = sql.format(workspace_predicate="AND workspace_id = CAST(:workspace_id AS uuid)")
    else:
        sql = sql.format(workspace_predicate="")

    try:
        candidates = [(str(r[0]), str(r[1])) for r in db.execute(text(sql), params).fetchall()]
        db.commit()  # end the read transaction; each row below is its own sealed transaction
        count = 0
        for row_id, row_ws in candidates:
            count += _orphan_and_seal(db, row_id, row_ws)
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


_ORPHAN_SQL = """
    UPDATE guard_audit_events
    SET lifecycle_state = 'orphaned',
        decision        = 'error',
        finalized_at    = COALESCE(finalized_at, :ts),
        ts              = :ts,
        previous_hash   = :prev_hash,
        hash_version    = :hash_version
    WHERE id = CAST(:row_id AS uuid)
      AND lifecycle_state = 'accepted'
      AND lease_expires_at < now()
"""


def _orphan_and_seal(db: Session, row_id: str, workspace_id: str) -> int:
    """Terminalize one expired row and seal it into the workspace chain.

    Lock order matches finalize(): chain lock first, then the row. The UPDATE
    re-checks lifecycle_state and the lease, so a row finalized or renewed since
    the candidate scan is left alone (rowcount 0, nothing sealed).
    """
    import uuid

    from app.core.workspace_context import set_workspace_rls
    from app.modules.guard.audit_chain import HASH_VERSION
    from app.modules.guard.models import chain_begin, chain_seal_stored_row

    set_workspace_rls(db, workspace_id)
    ts, prev_hash = chain_begin(db, uuid.UUID(workspace_id))
    result = db.execute(text(_ORPHAN_SQL), {
        "row_id": row_id, "ts": ts, "prev_hash": prev_hash, "hash_version": HASH_VERSION,
    })
    flipped = result.rowcount or 0
    if flipped:
        chain_seal_stored_row(db, row_id)
    db.commit()
    return 1 if flipped else 0
