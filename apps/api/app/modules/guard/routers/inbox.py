"""Guard Inbox — dedup'd triage view over guard_audit_events.

Design and rationale in #1840. The AFTER INSERT trigger on
guard_audit_events (migration 0122) populates guard_inbox with
one row per (workspace, rule_id, source, description-prefix)
dedup key. This router exposes the read + resolve surface.

Endpoints:
  GET   /guard/inbox                 list (filters + pagination)
  GET   /guard/inbox/{id}            detail
  GET   /guard/inbox/{id}/events     drill-in to raw audit events
  PATCH /guard/inbox/{id}            update status + resolve reason

Auth:
  - Read paths require guard.activity.view_all (existing seeded permission)
  - PATCH requires guard.policies.edit
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_user_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardInbox

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/inbox", tags=["guard-inbox"])


# ── Response / request models ─────────────────────────────────────────────

class InboxRowOut(BaseModel):
    id: str
    rule_id: str
    source: str
    severity: str
    description: str | None
    occurrences: int
    first_seen_at: datetime
    last_seen_at: datetime
    status: str
    resolved_reason: str | None
    resolved_note: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    latest_event_id: str | None
    agent_identity_id: str | None


class InboxEventOut(BaseModel):
    """Slim projection of a guard_audit_events row for the detail-drill view."""
    id: str
    ts: datetime
    decision: str
    ai_tool: str | None
    user_email: str | None
    input_summary: str | None
    provider: str | None
    model: str | None
    agent_identity_id: str | None


# Enum enforcement is the whole reason for the rename to `unreachable_fallback`
# on the LiteLLM shim — same pattern here for resolve reasons so callers can't
# scribble arbitrary strings into a triage taxonomy.
# `auto` is set by the guard_inbox_auto_close background worker when a
# row's dedup key hasn't fired in guard_config.inbox_auto_close_days days.
# Human triagers can also pick it manually via the API (e.g. batch triage
# scripts), but the UI doesn't offer it as a resolution reason — the
# admin should pick a real reason if they're closing a row by hand.
ResolvedReason = Literal["expected", "escalated", "exception_added", "false_positive", "auto"]
InboxStatus = Literal["open", "triaging", "resolved"]


class InboxPatchIn(BaseModel):
    status: InboxStatus
    resolved_reason: ResolvedReason | None = None
    resolved_note: str | None = Field(default=None, max_length=500)


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[InboxRowOut])
def list_inbox(
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.activity.view_all")),
    status_filter: InboxStatus | None = Query(default=None, alias="status"),
    severity: Literal["critical", "medium", "low"] | None = Query(default=None),
    source: Literal["gateway", "proxy", "mcp", "hook", "runtime"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[InboxRowOut]:
    """List inbox rows for the caller's workspace, newest-activity first."""
    q = db.query(GuardInbox).filter(GuardInbox.workspace_id == _uuid.UUID(workspace_id))

    if status_filter:
        q = q.filter(GuardInbox.status == status_filter)
    if severity:
        q = q.filter(GuardInbox.severity == severity)
    if source:
        q = q.filter(GuardInbox.source == source)

    rows = (
        q.order_by(GuardInbox.last_seen_at.desc())
         .offset(offset)
         .limit(limit)
         .all()
    )
    latest_ids = [r.latest_event_id for r in rows if r.latest_event_id]
    identity_by_event = {}
    if latest_ids:
        identity_by_event = {
            str(event_id): identity_id
            for event_id, identity_id in db.query(
                GuardAuditEvent.id, GuardAuditEvent.agent_identity_id,
            ).filter(
                GuardAuditEvent.workspace_id == _uuid.UUID(workspace_id),
                GuardAuditEvent.id.in_(latest_ids),
            ).all()
        }
    return [_row_to_out(r, identity_by_event.get(str(r.latest_event_id))) for r in rows]


@router.get("/{inbox_id}", response_model=InboxRowOut)
def get_inbox_row(
    inbox_id: str,
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.activity.view_all")),
    db: Session = Depends(get_db),
) -> InboxRowOut:
    row = _load_row(db, workspace_id, inbox_id)
    agent_identity_id = None
    if row.latest_event_id:
        event = db.query(GuardAuditEvent.agent_identity_id).filter(
            GuardAuditEvent.id == row.latest_event_id,
            GuardAuditEvent.workspace_id == _uuid.UUID(workspace_id),
        ).first()
        agent_identity_id = event[0] if event else None
    return _row_to_out(row, agent_identity_id)


@router.get("/{inbox_id}/events", response_model=list[InboxEventOut])
def list_events_for_row(
    inbox_id: str,
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.activity.view_all")),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[InboxEventOut]:
    """Drill-in: last N guard_audit_events rows sharing this inbox row's dedup key.

    Reconstructs the dedup filter from the row's rule_id + source +
    description prefix. Same shape the trigger uses to bucket rows.
    """
    row = _load_row(db, workspace_id, inbox_id)

    # Match the trigger's dedup-key inputs. Description prefix uses the
    # first 200 chars of rule_message on the event side.
    desc_prefix = (row.description or "")[:200]
    events = db.execute(
        text("""
            SELECT id, ts, decision, ai_tool, user_email, input_summary,
                   provider, model, agent_identity_id
            FROM guard_audit_events
            WHERE workspace_id = :ws
              AND rule_id = :rule
              AND source = :src
              AND LEFT(COALESCE(rule_message, ''), 200) = :desc
              AND decision IN ('blocked', 'warned', 'approved')
            ORDER BY ts DESC
            LIMIT :lim
        """),
        {
            "ws": _uuid.UUID(workspace_id),
            "rule": row.rule_id,
            "src": row.source,
            "desc": desc_prefix,
            "lim": limit,
        },
    ).fetchall()

    return [
        InboxEventOut(
            id=str(e.id),
            ts=e.ts,
            decision=e.decision,
            ai_tool=e.ai_tool,
            user_email=e.user_email,
            input_summary=e.input_summary,
            provider=e.provider,
            model=e.model,
            agent_identity_id=e.agent_identity_id,
        )
        for e in events
    ]


class BackfillOut(BaseModel):
    """Result of a manual backfill run.

    ``inserted`` — new inbox rows created for dedup groups that didn't
    exist yet.
    ``reconciled`` — existing inbox rows whose occurrences / first_seen /
    latest_event / severity were repaired against the authoritative
    audit-event history.
    """
    days: int
    inserted: int
    reconciled: int


# Backfill = "reconcile ``guard_inbox`` against the authoritative
# ``guard_audit_events`` history for groups that had activity in the last
# N days."
#
# Reviewer P1 (round 2): the previous single-statement SQL couldn't
# guarantee serialization with concurrent trigger inserts. Unreferenced
# CTEs with FOR UPDATE are frequently optimized out by Postgres, and
# even when they aren't, the ``authoritative`` snapshot ran BEFORE the
# lock was held — so a trigger's ``+ 1`` between snapshot and UPDATE
# would be overwritten by the stale count.
#
# New protocol (per group, per transaction):
#
# 1. **Discover** in-window dedup keys with a plain read.
# 2. For each key, in a single SQLAlchemy transaction:
#    a. **Lock** the target row via ``INSERT ... ON CONFLICT DO UPDATE``
#       (the DO UPDATE payload is intentionally a no-op — its only job
#       is to grab the row-level lock so subsequent trigger
#       ``ON CONFLICT DO UPDATE``s wait on us).
#    b. **Snapshot under the lock** — a fresh COUNT / MIN / MAX / severity
#       read of the audit history, executed AFTER (a) has taken the
#       lock so any concurrent trigger insert has either committed
#       before us (visible) or is waiting for our lock (excluded).
#    c. **Apply** the reconciliation UPDATE.
#    d. **Commit** — releases the lock. Any waiting trigger now
#       applies its ``+ 1`` on top of the reconciled count.
#
# Guarantees:
#
# - **Idempotent counts.** occurrences = exact count of qualifying
#   retained audit events. Re-runs converge.
# - **Concurrent-safe.** Deterministic lock ordering prevents the
#   overwrite the reviewer flagged.
# - **New groups included.** Step (a) INSERTs when the row is missing,
#   still holding the lock, so a brand-new group discovered by backfill
#   is reconciled the same way as a pre-existing one.
# - **Resolution metadata preserved.** UPDATE never touches
#   ``status`` / ``resolved_*``.
# - **Timestamps never regress.** ``LEAST(first_seen_at)``,
#   ``GREATEST(last_seen_at)``, ``latest_event_id`` only replaced when
#   the backfill's max ts strictly exceeds the row's.
# - **Severity escalates, never downgrades.** Ordinal max across
#   current row + authoritative history.
#
# Cost: two round trips per affected group. guard_inbox cardinality is
# bounded (dedup collapses far more than it fans out), so this scales
# fine for admin-triggered runs — orders of magnitude cheaper than the
# audit events they aggregate over.

_DEDUP_HASH_SQL = """
encode(
    digest(
        :ws::text
        || COALESCE(rule_id, '')
        || COALESCE(source, '')
        || LEFT(COALESCE(rule_message, ''), 200),
        'sha256'
    ),
    'hex'
)
"""


_DISCOVER_DEDUPS_SQL = """
SELECT DISTINCT
    encode(
        digest(
            ae.workspace_id::text
            || COALESCE(ae.rule_id, '')
            || COALESCE(ae.source, '')
            || LEFT(COALESCE(ae.rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    ) AS dedup_key
FROM guard_audit_events ae
WHERE ae.workspace_id = :ws
  AND ae.decision IN ('blocked', 'warned', 'approved')
  AND ae.rule_id IS NOT NULL
  AND ae.ts > NOW() - (:days || ' days')::interval
"""


# Step (a): lock (or create) the guard_inbox row for a single dedup_key.
# The DO UPDATE payload is a self-assignment — no state change, its
# only purpose is to take the row lock. RETURNING (xmax = 0) tells us
# whether we created a fresh row (xmax = 0 → INSERT path) or locked an
# existing one (xmax != 0 → UPDATE path).
#
# For fresh rows we seed with sentinel values — the follow-up UPDATE in
# step (c) rewrites them from the actual history under the lock.
_LOCK_OR_CREATE_SQL = """
INSERT INTO guard_inbox (
    workspace_id, dedup_key, rule_id, source, severity,
    description, occurrences, first_seen_at, last_seen_at, status,
    latest_event_id
)
VALUES (
    :ws, :dedup_key,
    '', 'unknown', 'medium',
    NULL, 0, NOW(), NOW(), 'open',
    NULL
)
ON CONFLICT (workspace_id, dedup_key) DO UPDATE
SET occurrences = guard_inbox.occurrences  -- no-op, just to lock
RETURNING id, (xmax = 0) AS was_insert
"""


# Step (b) + (c) combined: recompute authoritative snapshot under the
# lock we hold from step (a), then apply. ``:dedup_key`` is passed so
# we can filter without recomputing the hash on both sides.
_RECONCILE_APPLY_SQL = """
WITH authoritative AS (
    SELECT
        (array_agg(ae.rule_id ORDER BY ae.ts ASC))[1] AS rule_id,
        (array_agg(COALESCE(ae.source, 'unknown') ORDER BY ae.ts ASC))[1] AS source,
        (array_agg(ae.rule_message ORDER BY ae.ts ASC))[1] AS description,
        MIN(ae.ts) AS first_seen_at,
        MAX(ae.ts) AS last_seen_at,
        (array_agg(ae.id ORDER BY ae.ts DESC))[1] AS latest_event_id,
        COUNT(*)   AS occurrences,
        MAX(CASE ae.decision
                WHEN 'blocked'  THEN 3
                WHEN 'warned'   THEN 2
                WHEN 'approved' THEN 1
            END) AS max_sev_ord
    FROM guard_audit_events ae
    WHERE ae.workspace_id = :ws
      AND ae.decision IN ('blocked', 'warned', 'approved')
      AND ae.rule_id IS NOT NULL
      AND encode(
              digest(
                  ae.workspace_id::text
                  || COALESCE(ae.rule_id, '')
                  || COALESCE(ae.source, '')
                  || LEFT(COALESCE(ae.rule_message, ''), 200),
                  'sha256'
              ),
              'hex'
          ) = :dedup_key
)
UPDATE guard_inbox gi
SET
    -- rule_id / source / description only populated meaningfully for
    -- freshly-inserted rows where step (a) seeded blanks. For rows
    -- that already carried real values we keep the existing ones
    -- (COALESCE(gi.x, a.x)) since the trigger's initial values are
    -- the ones the UI/API have been reading.
    rule_id     = COALESCE(NULLIF(gi.rule_id, ''), a.rule_id, ''),
    source      = COALESCE(NULLIF(gi.source,  ''), a.source, 'unknown'),
    description = COALESCE(gi.description, a.description),
    occurrences = COALESCE(a.occurrences, 0),
    first_seen_at = LEAST(gi.first_seen_at, a.first_seen_at),
    last_seen_at  = GREATEST(gi.last_seen_at, a.last_seen_at),
    latest_event_id = CASE
        WHEN a.last_seen_at IS NOT NULL AND a.last_seen_at > gi.last_seen_at
        THEN a.latest_event_id
        ELSE gi.latest_event_id
    END,
    severity = CASE
        WHEN COALESCE(a.max_sev_ord, 0)
           > (CASE gi.severity
                WHEN 'critical' THEN 3
                WHEN 'medium'   THEN 2
                WHEN 'low'      THEN 1
                ELSE 0
              END)
        THEN (CASE a.max_sev_ord
                WHEN 3 THEN 'critical'
                WHEN 2 THEN 'medium'
                WHEN 1 THEN 'low'
                ELSE gi.severity
              END)
        ELSE gi.severity
    END
    -- status / resolved_* intentionally untouched.
FROM authoritative a
WHERE gi.workspace_id = :ws
  AND gi.dedup_key    = :dedup_key
"""


def _reconcile_one(db: Session, ws_uuid: _uuid.UUID, dedup_key: str) -> bool:
    """Lock, snapshot-under-lock, apply, commit — for a single dedup_key.

    Returns True if the row was newly inserted, False if reconciled.
    """
    seed = db.execute(
        text(_LOCK_OR_CREATE_SQL),
        {"ws": ws_uuid, "dedup_key": dedup_key},
    ).one()
    # Second statement runs in the same session-managed transaction, so
    # the row lock from _LOCK_OR_CREATE_SQL is still held. Snapshot
    # inside the UPDATE therefore sees a state where any concurrent
    # trigger's ON CONFLICT DO UPDATE is BLOCKED — so we never race
    # against a live ``+ 1`` between snapshot and apply.
    db.execute(
        text(_RECONCILE_APPLY_SQL),
        {"ws": ws_uuid, "dedup_key": dedup_key},
    )
    db.commit()  # release the row lock; any waiting trigger now applies.
    return bool(seed.was_insert)


@router.post("/backfill", response_model=BackfillOut)
def backfill_inbox(
    days: int = Query(default=30, ge=1, le=90),
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.policies.edit")),
    db: Session = Depends(get_db),
) -> BackfillOut:
    """Reconcile guard_inbox against the last N days of audit events.

    Per-group locking + snapshot-under-lock protocol — see
    ``_LOCK_OR_CREATE_SQL`` / ``_RECONCILE_APPLY_SQL`` module docstring
    for the full guarantees. Idempotent, concurrent-safe, preserves
    resolution metadata, escalates severity but never downgrades.
    """
    ws_uuid = _uuid.UUID(workspace_id)
    rows = db.execute(
        text(_DISCOVER_DEDUPS_SQL),
        {"ws": ws_uuid, "days": days},
    ).fetchall()
    # Commit the discovery read before we start the per-group loop so
    # each _reconcile_one() runs in its own tight transaction. Long
    # transactions holding many row locks would starve concurrent
    # triggers.
    db.commit()
    inserted = 0
    reconciled = 0
    for row in rows:
        was_insert = _reconcile_one(db, ws_uuid, row.dedup_key)
        if was_insert:
            inserted += 1
        else:
            reconciled += 1
    log.info(
        "guard_inbox.backfill",
        workspace_id=workspace_id,
        days=days,
        inserted=inserted,
        reconciled=reconciled,
        groups=len(rows),
    )
    return BackfillOut(days=days, inserted=inserted, reconciled=reconciled)


@router.patch("/{inbox_id}", response_model=InboxRowOut)
def update_inbox_row(
    inbox_id: str,
    body: InboxPatchIn,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _perm: str = Depends(require_permission("guard.policies.edit")),
    db: Session = Depends(get_db),
) -> InboxRowOut:
    """Update the status + resolve reason. `resolved_at` and `resolved_by`
    are set server-side; callers can't spoof them. Reason is required
    when moving to `resolved`."""
    row = _load_row(db, workspace_id, inbox_id)

    if body.status == "resolved" and body.resolved_reason is None:
        raise HTTPException(
            status_code=422,
            detail="resolved_reason is required when status is 'resolved'",
        )

    row.status = body.status
    if body.status == "resolved":
        row.resolved_reason = body.resolved_reason
        row.resolved_note = body.resolved_note
        row.resolved_at = datetime.now(timezone.utc)
        row.resolved_by = user_id
    else:
        # Moving off 'resolved' back to open/triaging clears the resolution
        # metadata. Same shape the trigger uses on auto-reopen.
        row.resolved_reason = None
        row.resolved_note = None
        row.resolved_at = None
        row.resolved_by = None

    db.commit()
    db.refresh(row)
    return _row_to_out(row)


# ── Helpers ───────────────────────────────────────────────────────────────

def _load_row(db: Session, workspace_id: str, inbox_id: str) -> GuardInbox:
    try:
        row = (
            db.query(GuardInbox)
            .filter(GuardInbox.id == _uuid.UUID(inbox_id))
            .filter(GuardInbox.workspace_id == _uuid.UUID(workspace_id))
            .first()
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid inbox_id")
    if not row:
        raise HTTPException(status_code=404, detail="Inbox row not found")
    return row


def _row_to_out(row: GuardInbox, agent_identity_id: str | None = None) -> InboxRowOut:
    return InboxRowOut(
        id=str(row.id),
        rule_id=row.rule_id,
        source=row.source,
        severity=row.severity,
        description=row.description,
        occurrences=row.occurrences,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        status=row.status,
        resolved_reason=row.resolved_reason,
        resolved_note=row.resolved_note,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
        latest_event_id=str(row.latest_event_id) if row.latest_event_id else None,
        agent_identity_id=agent_identity_id,
    )
