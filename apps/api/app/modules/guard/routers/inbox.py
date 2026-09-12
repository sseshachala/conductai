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


# Enum enforcement is the whole reason for the rename to `unreachable_fallback`
# on the LiteLLM shim — same pattern here for resolve reasons so callers can't
# scribble arbitrary strings into a triage taxonomy.
ResolvedReason = Literal["expected", "escalated", "exception_added", "false_positive"]
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
    source: Literal["proxy", "mcp", "hook", "runtime"] | None = Query(default=None),
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
    return [_row_to_out(r) for r in rows]


@router.get("/{inbox_id}", response_model=InboxRowOut)
def get_inbox_row(
    inbox_id: str,
    workspace_id: str = Depends(get_workspace_id),
    _perm: str = Depends(require_permission("guard.activity.view_all")),
    db: Session = Depends(get_db),
) -> InboxRowOut:
    row = _load_row(db, workspace_id, inbox_id)
    return _row_to_out(row)


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
                   provider, model
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
        )
        for e in events
    ]


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


def _row_to_out(row: GuardInbox) -> InboxRowOut:
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
    )
