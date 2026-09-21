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
# ``guard_audit_events`` history for events within the last N days."
#
# Guarantees (reviewer P1 on the original inflate/re-open bug):
#
# 1. **Idempotent counts.** ``occurrences`` on each affected group is set
#    to the exact count of qualifying retained audit events (blocked /
#    warned / approved with rule_id set) in the reconciliation window.
#    Re-running the endpoint an arbitrary number of times converges the
#    row to the same value — no ``+ 1`` drift.
#
# 2. **Concurrent-safe.** ``SELECT ... FOR UPDATE`` on the target inbox
#    rows serializes the UPDATE with the trigger's ON CONFLICT DO UPDATE
#    path. A live audit-event insert whose trigger fires while backfill
#    holds the lock waits, then applies its ``+ 1`` on top of the
#    reconciled count — so live activity is never overwritten.
#
# 3. **Resolution metadata preserved.** ``status`` / ``resolved_reason``
#    / ``resolved_at`` / ``resolved_by`` / ``resolved_note`` are NEVER
#    touched on the UPDATE branch. The trigger's re-open behavior stays
#    the only path that flips a resolved row back to open — and only on
#    a genuinely-new audit event, not a repair pass over history.
#
# 4. **Newer live activity never regresses.** ``first_seen_at`` takes
#    the ``LEAST``; ``last_seen_at`` takes the ``GREATEST``;
#    ``latest_event_id`` is only replaced when the backfilled max
#    timestamp is strictly greater than what's already on the row.
#
# 5. **Severity escalates, never downgrades.** Ordinal max
#    (critical > medium > low) across the group's history AND the
#    current row's value.
#
# The ``:days`` window bounds the audit-event scan. Groups touched by
# the query are reconciled against their FULL history — not just the
# events within the window — so a wider re-run cannot undo the count of
# a group that was previously reconciled with a narrower window.
_BACKFILL_SQL = """
WITH window_dedups AS (
    -- All (workspace_id, dedup_key) pairs that have at least one
    -- qualifying audit event in the requested window. Anything outside
    -- the window is out of scope — a group with no events in the last
    -- N days doesn't get its lifetime count "re-verified" today.
    SELECT DISTINCT
        ae.workspace_id,
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
),
-- FULL history reconciliation for each in-scope group. Not bounded by
-- :days — see (2) above. If a group's oldest event is a year old and
-- has fired 500 times, occurrences here = 500.
authoritative AS (
    SELECT
        ae.workspace_id,
        encode(
            digest(
                ae.workspace_id::text
                || COALESCE(ae.rule_id, '')
                || COALESCE(ae.source, '')
                || LEFT(COALESCE(ae.rule_message, ''), 200),
                'sha256'
            ),
            'hex'
        ) AS dedup_key,
        COALESCE(ae.rule_id, '')     AS rule_id,
        COALESCE(ae.source, 'unknown') AS source,
        ae.rule_message AS description,
        ae.id           AS event_id,
        ae.ts           AS event_ts,
        CASE ae.decision
            WHEN 'blocked'  THEN 3
            WHEN 'warned'   THEN 2
            WHEN 'approved' THEN 1
        END AS sev_ord
    FROM guard_audit_events ae
    WHERE ae.workspace_id = :ws
      AND ae.decision IN ('blocked', 'warned', 'approved')
      AND ae.rule_id IS NOT NULL
),
grouped AS (
    SELECT
        a.workspace_id,
        a.dedup_key,
        (array_agg(a.rule_id     ORDER BY a.event_ts ASC))[1] AS rule_id,
        (array_agg(a.source      ORDER BY a.event_ts ASC))[1] AS source,
        (array_agg(a.description ORDER BY a.event_ts ASC))[1] AS description,
        MIN(a.event_ts)  AS first_seen_at,
        MAX(a.event_ts)  AS last_seen_at,
        (array_agg(a.event_id ORDER BY a.event_ts DESC))[1] AS latest_event_id,
        COUNT(*)         AS occurrences,
        MAX(a.sev_ord)   AS max_sev_ord
    FROM authoritative a
    JOIN window_dedups w
      ON w.workspace_id = a.workspace_id
     AND w.dedup_key    = a.dedup_key
    GROUP BY a.workspace_id, a.dedup_key
),
severity_map AS (
    SELECT g.*,
        CASE g.max_sev_ord
            WHEN 3 THEN 'critical'
            WHEN 2 THEN 'medium'
            WHEN 1 THEN 'low'
            ELSE 'medium'
        END AS severity
    FROM grouped g
),
-- Serialize with the trigger's ON CONFLICT DO UPDATE on any pre-existing
-- inbox row for these groups. Rows we're about to INSERT (new groups)
-- have nothing to lock; the INSERT's own ON CONFLICT below handles the
-- narrow window where a trigger fires for a brand-new group between
-- SELECT and INSERT.
_locked AS (
    SELECT gi.id
    FROM guard_inbox gi
    JOIN severity_map s
      ON gi.workspace_id = s.workspace_id
     AND gi.dedup_key    = s.dedup_key
    FOR UPDATE
),
upserted AS (
    INSERT INTO guard_inbox (
        id, workspace_id, dedup_key, rule_id, source, severity,
        description, occurrences, first_seen_at, last_seen_at, status,
        latest_event_id
    )
    SELECT
        gen_random_uuid(),
        s.workspace_id, s.dedup_key, s.rule_id, s.source, s.severity,
        s.description, s.occurrences, s.first_seen_at, s.last_seen_at,
        'open', s.latest_event_id
    FROM severity_map s
    ON CONFLICT (workspace_id, dedup_key) DO UPDATE
    SET
        -- Authoritative count of retained audit events.
        occurrences     = EXCLUDED.occurrences,
        -- Never regress timestamps against live activity.
        first_seen_at   = LEAST(guard_inbox.first_seen_at, EXCLUDED.first_seen_at),
        last_seen_at    = GREATEST(guard_inbox.last_seen_at, EXCLUDED.last_seen_at),
        -- Only replace latest_event_id when we actually have a newer event.
        latest_event_id = CASE
            WHEN EXCLUDED.last_seen_at > guard_inbox.last_seen_at
            THEN EXCLUDED.latest_event_id
            ELSE guard_inbox.latest_event_id
        END,
        -- Ordinal max across current row + authoritative history.
        severity = CASE
            WHEN (CASE EXCLUDED.severity
                    WHEN 'critical' THEN 3
                    WHEN 'medium'   THEN 2
                    WHEN 'low'      THEN 1
                    ELSE 0
                  END)
              > (CASE guard_inbox.severity
                    WHEN 'critical' THEN 3
                    WHEN 'medium'   THEN 2
                    WHEN 'low'      THEN 1
                    ELSE 0
                  END)
            THEN EXCLUDED.severity
            ELSE guard_inbox.severity
        END
        -- ``status`` / ``resolved_*`` intentionally untouched: only the
        -- trigger's genuine re-fire path is allowed to reopen a
        -- resolved finding. A history repair must not do that.
    RETURNING (xmax = 0) AS was_insert
)
SELECT
    COUNT(*) FILTER (WHERE was_insert)     AS inserted,
    COUNT(*) FILTER (WHERE NOT was_insert) AS reconciled
FROM upserted
"""


@router.post("/backfill", response_model=BackfillOut)
def backfill_inbox(
    days: int = Query(default=30, ge=1, le=90),
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.policies.edit")),
    db: Session = Depends(get_db),
) -> BackfillOut:
    """Reconcile guard_inbox against the last N days of audit events.

    Idempotent: re-running with the same (or wider) window converges each
    affected group to the exact count of its retained audit events. Never
    inflates counts; never reopens resolved findings; never regresses
    ``last_seen_at`` / ``latest_event_id``; escalates severity but never
    downgrades. See ``_BACKFILL_SQL`` module docstring for the full
    guarantees.
    """
    row = db.execute(
        text(_BACKFILL_SQL),
        {"ws": _uuid.UUID(workspace_id), "days": days},
    ).one()
    db.commit()
    inserted = int(row.inserted or 0)
    reconciled = int(row.reconciled or 0)
    log.info(
        "guard_inbox.backfill",
        workspace_id=workspace_id,
        days=days,
        inserted=inserted,
        reconciled=reconciled,
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
