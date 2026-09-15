"""Ops surface for the Phase 4 durable-audit reconciler.

One endpoint. Lets a workspace admin force a reconciler pass without
waiting for the next 120s poll — useful when investigating a stuck
'in flight' counter on the Flight Recorder UI. The daemon in worker.py
runs the same code on its interval; this is a manual override.

Not a security boundary — the scoping to the caller's workspace happens
because guard_use_durable_audit rows are per-workspace, and the
require_permission gate stops non-admins from spamming reconciles.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.durable_audit_reconciler import (
    DEFAULT_MAX_BATCH,
    reconcile_orphaned,
)


router = APIRouter(prefix="/guard/durable-audit", tags=["guard"])


@router.post("/reconcile-now")
def reconcile_now(
    max_batch: int = DEFAULT_MAX_BATCH,
    _: str = Depends(require_permission("platform.workspace.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict:
    """Force one reconciler pass for the caller's workspace.

    Returns {"reconciled": <int>} — the number of 'accepted' rows
    flipped to 'orphaned'. A count of 0 means no expired-lease
    accepted rows were found, which is the healthy state.
    """
    count = reconcile_orphaned(db, workspace_id=workspace_id, max_batch=max_batch)
    return {"reconciled": count}


@router.get("/in-flight-count")
def in_flight_count(
    _: str = Depends(require_permission("platform.runs.view")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict:
    """How many durable-audit rows are still 'accepted' AND within
    their lease? Powers the ⏳ N in flight badge on the Flight Recorder
    tab — the frontend's client-side derivation is capped at the
    LIVE_EVENT_CAP row window, this endpoint isn't.

    Cheap: partial index ix_guard_audit_events_accepted_lease covers
    the WHERE clause exactly, so the count is one index scan.
    """
    from sqlalchemy import text as _text
    row = db.execute(
        _text("""
            SELECT count(*)::int AS n
            FROM guard_audit_events
            WHERE workspace_id = CAST(:ws AS uuid)
              AND lifecycle_state = 'accepted'
              AND lease_expires_at > now()
        """),
        {"ws": workspace_id},
    ).fetchone()
    return {"in_flight": int(row.n if row else 0)}
