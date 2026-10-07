"""Guard projection queue — durable intent persistence for audit-event projections (intent + summary upserts).

Re-exported from ``projection_queue``."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.guard.models import GuardProjectionIntent, GuardProjectionSummary
from app.modules.guard.observability.metrics import (
    GUARD_PROJECTION_EVENTS,
)
from app.modules.guard.projection_contract import (
    ProjectionIntentStatus,
    ProjectionMessage,
    ProjectionSourceKind,
)
from app.modules.guard.projection_policy import (
    audit_event_projection_reason,
    audit_event_source_version,
    normalize_projection_decision,
    projection_expires_at,
    projection_is_expired,
)


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _summary_window(ts: datetime) -> tuple[datetime, datetime]:
    ts = _utc(ts)
    minutes = settings.guard_projection_allowed_summary_window_minutes
    epoch_minutes = int(ts.timestamp() // 60)
    start_minutes = epoch_minutes - (epoch_minutes % minutes)
    start = datetime.fromtimestamp(start_minutes * 60, tz=timezone.utc)
    return start, start + timedelta(minutes=minutes)


def _bounded_dimension(value: object, limit: int) -> str:
    text = str(value or "unknown").strip().lower()[:limit]
    return text if re.fullmatch(r"[a-z0-9_.:-]+", text) else "other"


def _message(intent: GuardProjectionIntent) -> ProjectionMessage:
    return ProjectionMessage(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        source_kind=ProjectionSourceKind(intent.source_kind),
        source_id=intent.source_id,
        source_version=intent.source_version,
    )


def _new_intent(
    db: Session,
    *,
    workspace_id,
    source_kind: ProjectionSourceKind,
    source_id: str,
    source_version: str,
    now: datetime,
    expires_at: datetime | None = None,
    available_at: datetime | None = None,
) -> ProjectionMessage:
    intent = GuardProjectionIntent(
        workspace_id=workspace_id,
        source_kind=source_kind.value,
        source_id=source_id,
        source_version=source_version,
        status=ProjectionIntentStatus.PENDING.value,
        attempts=0,
        max_attempts=settings.guard_projection_max_attempts,
        available_at=available_at or now,
        expires_at=expires_at,
    )
    db.add(intent)
    db.flush()
    return _message(intent)


def _upsert_summary_intent(
    db: Session,
    *,
    workspace_id,
    source_id: str,
    source_version: str,
    available_at: datetime,
    expires_at: datetime,
    now: datetime,
) -> ProjectionMessage:
    stmt = insert(GuardProjectionIntent).values(
        workspace_id=workspace_id,
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id=source_id,
        source_version=source_version,
        status=ProjectionIntentStatus.PENDING.value,
        attempts=0,
        max_attempts=settings.guard_projection_max_attempts,
        available_at=available_at,
        expires_at=expires_at,
        dispatched_at=None,
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            GuardProjectionIntent.workspace_id,
            GuardProjectionIntent.source_kind,
            GuardProjectionIntent.source_id,
        ],
        index_where=sa.text(
            "source_kind = 'audit_summary' AND status IN ('pending', 'retry')"
        ),
        set_={
            "source_version": source_version,
            "status": ProjectionIntentStatus.PENDING.value,
            "attempts": 0,
            "max_attempts": settings.guard_projection_max_attempts,
            "available_at": available_at,
            "expires_at": expires_at,
            "lease_expires_at": None,
            "last_error": None,
            "dispatched_at": None,
            "completed_at": None,
            "updated_at": now,
        },
    ).returning(
        GuardProjectionIntent.id,
        GuardProjectionIntent.workspace_id,
        GuardProjectionIntent.source_kind,
        GuardProjectionIntent.source_id,
        GuardProjectionIntent.source_version,
    )
    row = db.execute(stmt).one()
    return ProjectionMessage(
        intent_id=row.id,
        workspace_id=row.workspace_id,
        source_kind=ProjectionSourceKind(row.source_kind),
        source_id=row.source_id,
        source_version=row.source_version,
    )


def persist_audit_event_projection(
    db: Session,
    event,
    *,
    evaluated_rules: list[dict] | None = None,
    now: datetime | None = None,
) -> ProjectionMessage | None:
    """Persist an event or summary intent in the caller transaction."""
    current = _utc(now or datetime.now(timezone.utc))
    source_ts = _utc(event.ts)
    expires_at = projection_expires_at(
        ProjectionSourceKind.AUDIT_EVENT,
        source_ts,
        settings.guard_projection_retention_days,
    )
    if projection_is_expired(expires_at, current):
        GUARD_PROJECTION_EVENTS.labels(result="expired").inc()
        return None
    reason = audit_event_projection_reason(event.decision, evaluated_rules)
    if reason is not None:
        GUARD_PROJECTION_EVENTS.labels(result="eligible").inc()
        return _new_intent(
            db,
            workspace_id=event.workspace_id,
            source_kind=ProjectionSourceKind.AUDIT_EVENT,
            source_id=str(event.id),
            source_version=audit_event_source_version(event),
            now=current,
            expires_at=expires_at,
        )
    if normalize_projection_decision(event.decision) != "allowed":
        GUARD_PROJECTION_EVENTS.labels(result="skipped").inc()
        return None
    GUARD_PROJECTION_EVENTS.labels(result="skipped").inc()
    GUARD_PROJECTION_EVENTS.labels(result="summarized").inc()
    window_start, window_end = _summary_window(source_ts)
    ai_tool = _bounded_dimension(event.ai_tool, 50)
    tool_call = _bounded_dimension(event.tool_call, 255)
    raw_rule_id = str(event.rule_id or "none")
    rule_id = (
        "none"
        if raw_rule_id == "none"
        else hashlib.sha256(raw_rule_id.encode()).hexdigest()[:16]
    )
    dimension_key = hashlib.sha256(
        json.dumps([ai_tool, tool_call, rule_id], separators=(",", ":")).encode()
    ).hexdigest()
    summary_expiry = projection_expires_at(
        ProjectionSourceKind.AUDIT_SUMMARY,
        window_end,
        settings.guard_projection_retention_days,
    )
    facts = {
        "decision": "allowed",
        "ai_tool": ai_tool,
        "tool_call": tool_call,
        "rule_id": rule_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }
    stmt = insert(GuardProjectionSummary).values(
        workspace_id=event.workspace_id,
        window_start=window_start,
        window_end=window_end,
        dimension_key=dimension_key,
        ai_tool=ai_tool,
        tool_call=tool_call,
        rule_id=rule_id,
        event_count=1,
        version=1,
        canonical_facts=facts,
        source_timestamp=window_end,
        expires_at=summary_expiry,
        created_at=current,
        updated_at=current,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_guard_projection_summary_window_dimension",
        set_={
            "event_count": GuardProjectionSummary.event_count + 1,
            "version": GuardProjectionSummary.version + 1,
            "updated_at": current,
        },
    ).returning(GuardProjectionSummary.id, GuardProjectionSummary.version)
    summary_id, version = db.execute(stmt).one()
    _upsert_summary_intent(
        db,
        workspace_id=event.workspace_id,
        source_id=str(summary_id),
        source_version=str(version),
        available_at=window_end,
        expires_at=summary_expiry,
        now=current,
    )
    # Summary intents are deliberately not sent to Redis before the window
    # closes. Reconciliation dispatches the single coalesced durable row when
    # available_at is reached, avoiding one queue delivery per allowed event.
    return None
